"""
chat/middleware.py

QueryAuthMiddleware — blocks unauthenticated users from submitting queries.

This is a defence-in-depth layer on top of the @login_required decorators
in views.py.  It intercepts any POST to /chat/query/ (or the chat endpoint)
before it reaches the view, so unauthenticated API calls get a clean 401
rather than a Django redirect loop when the client expects JSON.

For browser navigation (GET requests) and the auth routes themselves, the
middleware is a transparent pass-through.  Django's existing
AuthenticationMiddleware and @login_required handle those cases.
"""

import json
import logging

from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)

# URL path prefixes that require authentication for POST requests.
# Adjust if the URL structure changes.
_PROTECTED_POST_PATHS = (
    "/chat/query",
    "/chat/",          # catches the main chat view POST
)

# Paths that are always allowed through regardless of auth state.
_ALWAYS_ALLOW = (
    "/auth/login",
    "/auth/register",
    "/auth/logout",
    "/admin/",
)


class QueryAuthMiddleware:
    """
    WSGI-compatible middleware that returns HTTP 401 for unauthenticated
    POST requests to protected query endpoints.

    Browser GET requests and auth routes are passed through unchanged.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if self._should_block(request):
            logger.warning(
                "Blocked unauthenticated POST to %s from %s",
                request.path,
                request.META.get("REMOTE_ADDR", "unknown"),
            )
            return JsonResponse(
                {"error": "Authentication required. Please log in to submit queries."},
                status=401,
            )

        return self.get_response(request)

    @staticmethod
    def _should_block(request: HttpRequest) -> bool:
        """
        Return True only when ALL of the following are true:
        - The request is a POST
        - The path matches a protected endpoint
        - The path is NOT an always-allowed auth route
        - The user is not authenticated
        """
        if request.method != "POST":
            return False

        path = request.path

        # Never block auth routes
        if any(path.startswith(p) for p in _ALWAYS_ALLOW):
            return False

        # Only enforce on the protected query paths
        if not any(path.startswith(p) for p in _PROTECTED_POST_PATHS):
            return False

        # Pass through if authenticated
        user = getattr(request, "user", None)
        return user is None or not user.is_authenticated
