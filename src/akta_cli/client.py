"""Standalone synchronous HTTP client for the Akta REST API.

Deliberately self-contained (no dependency on `akta_mcp.*`): the server's
`AktaClient` reads its key from a request-scoped ContextVar set by the OAuth
middleware and transitively imports the Redis/Postgres token stores, none of
which a CLI wants. This mirrors the server's error handling and redirect
behaviour but takes the API key explicitly and runs synchronously.
"""

from __future__ import annotations

import httpx

DEFAULT_BASE_URL = "https://api.akta.pro/api/v1"


class AktaAPIError(RuntimeError):
    """An HTTP error from the Akta API, preserving the status code and body."""

    def __init__(self, message: str, *, status_code: int, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


_ERROR_MESSAGES = {
    400: "Bad request — check the parameters.",
    401: "Authentication failed. Check your API key (`akta login`).",
    403: (
        "Access denied — your plan or credit balance does not cover this data "
        "(alternative signals require Subscription/Enterprise; Funding and M&A "
        "sections are enterprise-only)."
    ),
    404: "Not found.",
    429: "Rate limit exceeded. Retry with backoff.",
    500: "Akta server error. Please try again later.",
    502: "Akta service unavailable. Please retry.",
    503: "Akta service unavailable. Please retry.",
}


def _sanitize_http_error(exc: httpx.HTTPStatusError) -> AktaAPIError:
    status = exc.response.status_code
    msg = _ERROR_MESSAGES.get(status, f"Request failed with status {status}.")
    try:
        body = exc.response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("message") or body.get("error")
        if detail:
            msg = f"{msg} ({detail})"
    return AktaAPIError(msg, status_code=status, body=body if isinstance(body, dict) else None)


def _clean(params: dict | None) -> dict:
    # Drop unset optional params so they aren't serialized onto the query string.
    return {k: v for k, v in (params or {}).items() if v is not None}


class AktaClient:
    """Thin synchronous httpx wrapper that sends `x-api-key` on every GET."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self._api_key = api_key
        # follow_redirects: several Akta routes are declared with a trailing slash,
        # so a slashless path 307-redirects to the canonical one. The redirect is
        # same-origin, so x-api-key is re-sent.
        self._http = httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=True)

    def _headers(self) -> dict:
        return {"x-api-key": self._api_key, "X-Client-Source": "AKTA-CLI"}

    def get(self, path: str, params: dict | None = None):
        """GET, returning parsed JSON when the response is JSON, else raw text.

        Text is returned for Akta's server-rendered Markdown endpoints (e.g.
        `/company/enrichment/markdown`).
        """
        resp = self._http.get(path, params=_clean(params), headers=self._headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _sanitize_http_error(exc) from None
        if "json" in resp.headers.get("content-type", "").lower():
            return resp.json()
        return resp.text

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AktaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
