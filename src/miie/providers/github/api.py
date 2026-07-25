"""
GitHub REST API client for the observation provider.

Handles HTTP requests, pagination, rate-limit back-off, and
structured error handling.  No third-party dependencies — uses
only ``urllib`` from the standard library.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple

from miie.providers.github.authentication import GitHubAuth
from miie.providers.github.models import RateLimitInfo

logger = logging.getLogger(__name__)

_BASE_URL: str = "https://api.github.com"
_USER_AGENT: str = "MIIE-Provider/1.6"
_DEFAULT_TIMEOUT: float = 30.0


class GitHubAPIError(Exception):
    """Structured error from the GitHub API."""

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        response_body: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GitHubClient:
    """Lightweight GitHub REST API client.

    Supports:
      - Authenticated and anonymous access
      - Automatic pagination
      - Rate-limit awareness with back-off
      - Deterministic ordering (newest first)
    """

    def __init__(
        self,
        auth: Optional[GitHubAuth] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._auth = auth or GitHubAuth()
        self._timeout = timeout
        self._rate_limit: Optional[RateLimitInfo] = None

    def _open(self, req: urllib.request.Request):
        """Open a URL with SSRF-safe redirect handling.

        Redirects outside the GitHub API base URL are blocked.
        Tests can mock this method to avoid network calls.
        """

        class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self2, req, fp, code, msg, headers, newurl):
                if not newurl.startswith(_BASE_URL):
                    raise urllib.error.HTTPError(newurl, 403, "Redirect outside GitHub API not allowed", headers, None)
                return urllib.request.redirect_request(req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(_SafeRedirectHandler)
        return opener.open(req, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def rate_limit(self) -> Optional[RateLimitInfo]:
        """Most recently observed rate-limit info."""
        return self._rate_limit

    def get_rate_limit(self) -> RateLimitInfo:
        """Fetch the current rate-limit status."""
        _, headers, _ = self._request("GET", "/rate_limit")
        info = RateLimitInfo.from_headers(headers)
        self._rate_limit = info
        return info

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch repository metadata."""
        data, _, _ = self._request("GET", f"/repos/{owner}/{repo}")
        return data

    def get_default_branch(self, owner: str, repo: str) -> str:
        """Return the default branch name."""
        data = self.get_repository(owner, repo)
        return data.get("default_branch", "main")

    # ------------------------------------------------------------------
    # Pull Requests
    # ------------------------------------------------------------------

    def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        sort: str = "created",
        direction: str = "desc",
        per_page: int = 100,
        since: Optional[datetime] = None,
        max_prs: int = 0,
    ) -> List[Dict[str, Any]]:
        """List pull requests with automatic pagination.

        Args:
            owner: Repository owner.
            repo: Repository name.
            state: ``open``, ``closed``, or ``all``.
            sort: Sort field (``created``, ``updated``, ``popularity``).
            direction: ``asc`` or ``desc``.
            per_page: Results per page (max 100).
            since: Only PRs updated after this time.
            max_prs: Stop after this many PRs (0 = no limit).

        Returns:
            Full list of PR dicts from the API.
        """
        params: Dict[str, str] = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": str(min(per_page, 100)),
        }
        if since is not None:
            params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        if max_prs > 0:
            result: List[Dict[str, Any]] = []
            for item in self._paginate(f"/repos/{owner}/{repo}/pulls", params):
                result.append(item)
                if len(result) >= max_prs:
                    break
            return result
        return list(self._paginate(f"/repos/{owner}/{repo}/pulls", params))

    def get_pull_request(self, owner: str, repo: str, number: int) -> Dict[str, Any]:
        """Fetch a single pull request."""
        data, _, _ = self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        return data

    def list_pull_request_reviews(
        self,
        owner: str,
        repo: str,
        number: int,
        per_page: int = 100,
    ) -> List[Dict[str, Any]]:
        """List reviews on a pull request."""
        params: Dict[str, str] = {"per_page": str(min(per_page, 100))}
        return list(self._paginate(f"/repos/{owner}/{repo}/pulls/{number}/reviews", params))

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str], int]:
        """Execute an HTTP request and return (data, headers, status).

        Handles rate-limit back-off automatically.
        """
        if path.startswith("/"):
            url = f"{_BASE_URL}{path}"
        else:
            # Only allow absolute URLs that stay on the GitHub API
            if not path.startswith(_BASE_URL):
                raise GitHubAPIError(f"Refused to fetch URL outside GitHub API: {path}")
            url = path

        # Enforce HTTPS only
        if not url.startswith("https://"):
            raise GitHubAPIError(f"Refused non-HTTPS URL: {url}")

        headers = self._auth.to_header_dict()
        # Redact token from logs (issue 25)
        safe_headers = {k: ("***" if k.lower() == "authorization" else v) for k, v in headers.items()}
        logger.debug("GitHub API %s %s headers=%s", method, path, safe_headers)
        headers["User-Agent"] = _USER_AGENT

        data_bytes = None
        if body is not None:
            data_bytes = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with self._open(req) as resp:
                raw = resp.read().decode("utf-8")
                resp_headers = dict(resp.headers)
                status = resp.status
                self._rate_limit = RateLimitInfo.from_headers(resp_headers)
                parsed = json.loads(raw) if raw else {}
                return parsed, resp_headers, status

        except urllib.error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8")
            except Exception:
                pass
            if exc.code == 403 and self._is_rate_limited(body_text):
                self._backoff()
                return self._request(method, path, body)
            raise GitHubAPIError(
                f"GitHub API error {exc.code}: {exc.reason}",
                status_code=exc.code,
                response_body=body_text,
            ) from exc

        except urllib.error.URLError as exc:
            raise GitHubAPIError(
                f"GitHub API connection failed: {exc.reason}",
                status_code=0,
            ) from exc

    def _paginate(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Paginate through a GitHub API list endpoint.

        Yields individual items from all pages.
        """
        page = 1
        while True:
            query = dict(params or {})
            query["page"] = str(page)
            qs = "&".join(f"{k}={v}" for k, v in query.items())
            full_path = f"{path}?{qs}" if qs else path

            data, _, _ = self._request("GET", full_path)
            if not isinstance(data, list) or len(data) == 0:
                break
            yield from data
            if len(data) < int(query.get("per_page", "100")):
                break
            page += 1

    @staticmethod
    def _is_rate_limited(body: str) -> bool:
        """Check if a 403 response is a rate-limit error."""
        try:
            parsed = json.loads(body)
            msg = parsed.get("message", "").lower()
            return "rate limit" in msg
        except (json.JSONDecodeError, AttributeError):
            return False

    @staticmethod
    def _backoff(seconds: float = 60.0) -> None:
        """Sleep for back-off duration on rate-limit hit."""
        logger.warning("GitHub API rate-limited, backing off %.1fs", seconds)
        time.sleep(seconds)
