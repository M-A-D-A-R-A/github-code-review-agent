from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Literal
from uuid import UUID


class AnalyzePRRequest(BaseModel):
    repo_url: HttpUrl
    pr_number: int
    github_token: Optional[str] = None


class Issue(BaseModel):
    type: Literal["style", "bug", "performance", "best_practice", "security","best practice"]
    line: Optional[int]
    description: str
    suggestion: Optional[str]
    severity: Literal["low", "medium", "high"] = "medium"


class FileIssues(BaseModel):
    name: str
    issues: List[Issue]


class Summary(BaseModel):
    total_files: int
    total_issues: int
    critical_issues: int


class ReviewResults(BaseModel):
    files: List[FileIssues]
    summary: Summary


class AnalyzePRResponse(BaseModel):
    task_id: UUID
    status: str


class StatusResponse(BaseModel):
    task_id: UUID
    status: str
    error: Optional[str] = None


class ResultsResponse(BaseModel):
    task_id: UUID
    status: str
    results: Optional[ReviewResults] = None