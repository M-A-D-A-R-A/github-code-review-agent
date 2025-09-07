from __future__ import annotations
import base64
import re
from typing import Dict, List, Tuple
from urllib.parse import urlparse
import httpx


from ..config import get_settings


GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str | None):
        self._token = token or get_settings().DEFAULT_GITHUB_TOKEN
        self._headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": get_settings().GITHUB_API_VERSION,
        }
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"


    @staticmethod
    def _parse_repo_url(repo_url: str) -> Tuple[str, str]:
        """Return (owner, repo) from a https://github.com/owner/repo URL."""
        path = urlparse(repo_url).path.strip("/")
        owner, repo = path.split("/", 1)
        return owner, repo


    async def list_pr_files(self, repo_url: str, pr_number: int) -> List[dict]:
        owner, repo = self._parse_repo_url(repo_url)
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        files: List[dict] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                r = await client.get(url, headers=self._headers, params={"per_page": 100, "page": page})
                r.raise_for_status()
                chunk = r.json()
                files.extend(chunk)
                if len(chunk) < 100:
                    break
                page += 1
        return files


    async def get_pr_patch(self, repo_url: str, pr_number: int) -> str:
        owner, repo = self._parse_repo_url(repo_url)
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {**self._headers, "Accept": "application/vnd.github.v3.patch"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.text