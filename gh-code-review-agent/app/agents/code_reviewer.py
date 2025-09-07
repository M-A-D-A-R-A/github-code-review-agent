from __future__ import annotations
from typing import List, Dict
import json
import logging
import time
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
JSON schema keys: files[].name, files[].issues[{type,line,description,suggestion,severity}], summary{total_files,total_issues,critical_issues}.
"""
).strip()

def build_agent(model_id: str | None = None) -> Agent:
    model = Ollama(
        id=model_id or get_settings().AGNO_MODEL,        # e.g., "llama3.1", "qwen2.5:14b", "deepseek-r1"
        host=get_settings().OLLAMA_HOST,                 # e.g., "http://localhost:11434" or "http://ollama:11434"
    )
    agent = Agent(
        name="PR Code Reviewer",
        model=model,
        instructions=[REVIEW_SYSTEM_PROMPT],
        markdown=False,
        add_history_to_messages=False,
    )
    return agent
def run_agent_review(
    agent: Agent,
    pr_patch: str,
    files_payload: List[dict],
    static_hints: Dict[str, List[dict]],
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
        "task": "Analyze PR and return JSON in target schema only.",
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
        "output_schema": {
            "files": [{
                "name": "string",
                "issues": [{
                    "type": "style|bug|performance|best_practice|security",
                    "line": "int?",
                    "description": "string",
                    "suggestion": "string?",
                    "severity": "low|medium|high"
                }]
            }],
            "summary": {"total_files": "int", "total_issues": "int", "critical_issues": "int"}
        }
    }

    t0 = time.perf_counter()
    response = agent.run(json.dumps(prompt),format ="json")
    dt_ms = int((time.perf_counter() - t0) * 1000)
    
    if hasattr(response, "content"):         # Agno RunResponse
        text = response.content
    elif isinstance(response, (str, bytes)): # just in case a model returns raw text
        text = response.decode() if isinstance(response, bytes) else response
    else:
        text = str(response)                 # last-resort fallback

    # (optional) your log line — remove exc_info=True since there’s no exception
    logger.info("agent_review.model_output_preview %s", text[:600])

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    
    if first_brace == -1 or last_brace == -1:
        logger.error(
            "agent_review.non_json_response",
            extra={"response_preview": text[:300], "duration_ms": dt_ms},
        )
        raise ValueError("Agent did not return JSON")
    
    try:
        payload = json.loads(text[first_brace:last_brace + 1])
    except Exception as e:
        logger.exception(
            "agent_review.json_parse_error",
            extra={"duration_ms": dt_ms, "response_preview": text[:300]},
        )
        raise

    # Optional: log summary if present
    summary = payload.get("summary", {})
    logger.info(
        "agent_review.success",
        extra={
            "duration_ms": dt_ms,
            "total_files": summary.get("total_files"),
            "total_issues": summary.get("total_issues"),
            "critical_issues": summary.get("critical_issues"),
        },
    )
    return payload