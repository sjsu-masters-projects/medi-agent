"""Response headers that constrain what a browser will do with an API response.

The API served none of these. They are cheap, and each one closes a class of
browser-side attack that no amount of server-side authorization can reach.

The values suit a JSON API: it renders nothing, embeds nothing, and is never framed, so
the policy can be far stricter than a web page's. The portals need their own headers,
set in each Next config.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# A JSON API needs no scripts, styles, images or frames of its own. Denying everything
# means a response coaxed into rendering as HTML has nothing to execute.
_API_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

_STATIC_HEADERS: dict[str, str] = {
    # Stop browsers from second-guessing the declared type, which is how a JSON response
    # gets treated as HTML and executed.
    "X-Content-Type-Options": "nosniff",
    # Legacy companion to frame-ancestors, for browsers that predate CSP level 2.
    "X-Frame-Options": "DENY",
    # Never leak an authenticated API path to a third-party site.
    "Referrer-Policy": "no-referrer",
    # The API has no use for device APIs; deny them rather than inherit a default.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": _API_CONTENT_SECURITY_POLICY,
}

# Two years, matching the portals. Only sent over HTTPS: pinning HSTS from a local
# http:// dev server would poison the developer's browser for localhost.
_HSTS_VALUE = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the response headers above to every API response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        for header, value in _STATIC_HEADERS.items():
            # Never clobber a route that deliberately set its own policy.
            response.headers.setdefault(header, value)

        if request.url.scheme == "https" or settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", _HSTS_VALUE)

        return response
