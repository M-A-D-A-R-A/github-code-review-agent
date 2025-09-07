from __future__ import annotations
from typing import List, Dict
import json
import logging
import time
import re
from agno.agent import Agent
from agno.models.ollama import Ollama  # ⬅️ use Ollama
from ..config import get_settings

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = (
    """
You are a senior staff engineer doing code review on a GitHub Pull Request.
Follow this plan:
1) Understand the PR context and patch.
2) Use any provided static check findings as seed hints.
3) Identify issues in five categories: style, bug, performance, best_practice, security.
4) Provide concise suggestions that are actionable.
5) Produce STRICT JSON following the provided schema; do not include any extra text.

CRITICAL: Return ONLY valid JSON. Do not include markdown code blocks, explanations, or any text before/after the JSON.

JSON schema:
{
  "files": [
    {
      "name": "string",
      "issues": [
        {
          "type": "style|bug|performance|best_practice|security",
          "line": 123,
          "description": "string",
          "suggestion": "string",
          "severity": "low|medium|high"
        }
      ]
    }
  ],
  "summary": {
    "total_files": 0,
    "total_issues": 0,
    "critical_issues": 0
  }
}
"""
).strip()

def build_agent(model_id: str | None = None) -> Agent:
    model = Ollama(
        id=model_id or get_settings().AGNO_MODEL,        # e.g., "llama3.1", "qwen2.5:14b", "deepseek-r1"
        host=get_settings().OLLAMA_HOST,                 # e.g., "http://localhost:11434" or "http://ollama:11434"
        temperature=0.1,  # Lower temperature for more consistent JSON output
    )
    agent = Agent(
        name="PR Code Reviewer",
        model=model,
        instructions=[REVIEW_SYSTEM_PROMPT],
        markdown=False,
        add_history_to_messages=False,
    )
    return agent

def extract_json_from_response(text: str) -> dict:
    """
    Robustly extract JSON from model response, handling various formats.
    """
    # Remove markdown code blocks if present
    text = re.sub(r'```json\s*\n?', '', text)
    text = re.sub(r'```\s*$', '', text)
    
    # Try to find JSON boundaries
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    
    if first_brace == -1 or last_brace == -1:
        raise ValueError("No JSON braces found in response")
    
    json_text = text[first_brace:last_brace + 1]
    
    # Try parsing the extracted JSON
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        # Try to fix common JSON issues
        json_text = fix_common_json_issues(json_text)
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse JSON after fixes. Original error: {e}")

def fix_common_json_issues(json_text: str) -> str:
    """
    Attempt to fix common JSON formatting issues.
    """
    # Fix unescaped quotes in strings
    # This is a simple approach - for production you might want a more robust solution
    json_text = re.sub(r'(?<!\\)"(?=[^,}\]:]*[,}\]:}])', '\\"', json_text)
    
    # Remove trailing commas before closing braces/brackets
    json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
    
    # Fix unescaped newlines in strings
    json_text = json_text.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    
    return json_text

def validate_response_schema(payload: dict) -> dict:
    """
    Validate and sanitize the response to ensure it matches expected schema.
    """
    # Ensure required top-level keys exist
    if "files" not in payload:
        payload["files"] = []
    if "summary" not in payload:
        payload["summary"] = {
            "total_files": 0,
            "total_issues": 0,
            "critical_issues": 0
        }
    
    # Valid enum values
    VALID_TYPES = ["style", "bug", "performance", "best_practice", "security"]
    VALID_SEVERITIES = ["low", "medium", "high"]
    
    # Validate files structure
    validated_files = []
    for file_data in payload.get("files", []):
        if not isinstance(file_data, dict) or "name" not in file_data:
            continue
            
        validated_file = {
            "name": str(file_data["name"]),
            "issues": []
        }
        
        # Validate issues
        for issue in file_data.get("issues", []):
            if not isinstance(issue, dict):
                continue
            
            # Clean and validate issue type
            issue_type = str(issue.get("type", "style")).lower().strip()
            
            # Handle common variations and fix malformed types
            if issue_type == "best practice" or issue_type == "bestpractice":
                issue_type = "best_practice"
            elif issue_type in ["perf", "performance"]:
                issue_type = "performance"
            elif issue_type in ["sec", "security"]:
                issue_type = "security"
            elif issue_type not in VALID_TYPES:
                # If it contains pipe symbols or looks like schema definition
                if "|" in issue_type or "style" in issue_type.lower():
                    issue_type = "style"  # Default fallback
                else:
                    issue_type = "style"
            
            # Clean and validate severity
            severity = str(issue.get("severity", "medium")).lower().strip()
            if severity not in VALID_SEVERITIES:
                if "high" in severity or "critical" in severity:
                    severity = "high"
                elif "low" in severity or "minor" in severity:
                    severity = "low"
                else:
                    severity = "medium"
            
            # Handle line number
            line = issue.get("line")
            if line is not None:
                try:
                    line = int(line) if line else None
                except (ValueError, TypeError):
                    line = None
            
            validated_issue = {
                "type": issue_type,
                "line": line,
                "description": str(issue.get("description", "")).strip(),
                "suggestion": str(issue.get("suggestion", "")).strip() if issue.get("suggestion") else None,
                "severity": severity
            }
            
            # Skip empty issues
            if not validated_issue["description"]:
                continue
                
            validated_file["issues"].append(validated_issue)
        
        validated_files.append(validated_file)
    
    # Update summary to match actual data
    total_issues = sum(len(f["issues"]) for f in validated_files)
    critical_issues = sum(
        len([i for i in f["issues"] if i["severity"] == "high"]) 
        for f in validated_files
    )
    
    payload["files"] = validated_files
    payload["summary"] = {
        "total_files": len(validated_files),
        "total_issues": total_issues,
        "critical_issues": critical_issues
    }
    
    return payload

def run_agent_review(
    agent: Agent,
    pr_patch: str,
    files_payload: List[dict],
    static_hints: Dict[str, List[dict]],
    max_retries: int = 3,
) -> dict:
    MAX_PATCH_CHARS = 60_000
    patch = pr_patch[:MAX_PATCH_CHARS]

    # Metrics / debug
    logger.info(
        "agent_review.start",
        extra={
            "files_count": len(files_payload),
            "patch_len": len(pr_patch),
            "patch_truncated": len(pr_patch) > MAX_PATCH_CHARS,
            "static_hint_files": len(static_hints),
            "static_hint_total": sum(len(v) for v in static_hints.values()),
        },
    )

    prompt = {
        "task": "Analyze PR and return JSON in target schema only. NO EXTRA TEXT.",
        "files": [
            {
                "name": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
            }
            for f in files_payload
        ],
        "static_hints": static_hints,
        "patch": patch,
        "instructions": [
            "Return ONLY valid JSON matching the schema",
            "Do not include markdown code blocks",
            "Do not include explanations or extra text",
            "Ensure all strings are properly escaped",
            "Do not use trailing commas"
        ]
    }

    last_error = None
    
    for attempt in range(max_retries):
        try:
            t0 = time.perf_counter()
            response = agent.run(json.dumps(prompt), format="json")
            dt_ms = int((time.perf_counter() - t0) * 1000)
            
            # Extract text from response
            if hasattr(response, "content"):
                text = response.content
            elif isinstance(response, (str, bytes)):
                text = response.decode() if isinstance(response, bytes) else response
            else:
                text = str(response)
            
            # Log the full response for debugging (truncated for safety)
            logger.info(
                "agent_review.raw_response",
                extra={
                    "attempt": attempt + 1,
                    "response_length": len(text),
                    "response_preview": text[:500] + "..." if len(text) > 500 else text
                }
            )
            
            # Extract and parse JSON
            payload = extract_json_from_response(text)
            
            # Validate and sanitize the response
            payload = validate_response_schema(payload)
            
            # Log success
            summary = payload.get("summary", {})
            logger.info(
                "agent_review.success",
                extra={
                    "attempt": attempt + 1,
                    "duration_ms": dt_ms,
                    "total_files": summary.get("total_files"),
                    "total_issues": summary.get("total_issues"),
                    "critical_issues": summary.get("critical_issues"),
                },
            )
            
            return payload
            
        except Exception as e:
            last_error = e
            logger.warning(
                "agent_review.attempt_failed",
                extra={
                    "attempt": attempt + 1,
                    "error": str(e),
                    "max_retries": max_retries
                }
            )
            
            if attempt < max_retries - 1:
                # Wait a bit before retrying
                time.sleep(1)
                continue
    
    # All attempts failed
    logger.error(
        "agent_review.all_attempts_failed",
        extra={"max_retries": max_retries, "last_error": str(last_error)}
    )
    
    # Return a fallback response instead of raising an exception
    return {
        "files": [],
        "summary": {
            "total_files": 0,
            "total_issues": 0,
            "critical_issues": 0
        },
        "error": f"Failed to parse agent response after {max_retries} attempts: {str(last_error)}"
    }