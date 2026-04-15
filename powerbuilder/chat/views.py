"""
chat/views.py

Auth views for Powerbuilder.

Flow
----
Registration:
  1. User submits email + password.
  2. Extract email domain → look up or create Organization.
  3. Create Django User + UserProfile linked to that org.
  4. Log the user in and store org_namespace in the session.
  # TODO: add email-verification step here before activating the account.
  #       Use Django's PasswordResetForm token machinery or a third-party
  #       package (django-allauth, dj-rest-auth) to send a confirmation link.
  #       Until verified, set user.is_active = False and activate on click.

Login:
  1. Authenticate with Django's built-in auth.
  2. Refresh org_namespace in the session (catches domain changes by admin).
  3. Redirect to the chat interface.

Logout:
  1. Flush the session and redirect to login.

Query submission (chat_view):
  1. Blocked by QueryAuthMiddleware if the user is anonymous.
  2. Reads org_namespace from the session.
  3. Passes it into manager_app.invoke() via AgentState.
"""

import json
import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Organization, UserProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session key constant — single source of truth used here and in middleware
# ---------------------------------------------------------------------------

SESSION_ORG_NAMESPACE = "org_namespace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain_from_email(email: str) -> str:
    """Extract the domain part of an email address."""
    return email.strip().lower().split("@")[-1]


def _set_org_session(request, user: User) -> str:
    """
    Resolve the user's Pinecone namespace and write it to the session.
    Returns the namespace string.
    """
    try:
        profile = user.profile
        namespace = profile.pinecone_namespace
    except UserProfile.DoesNotExist:
        namespace = "general"

    request.session[SESSION_ORG_NAMESPACE] = namespace
    return namespace


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_view(request):
    """
    GET  → render registration form.
    POST → create User + UserProfile + Organization, log in, redirect.
    """
    if request.user.is_authenticated:
        return redirect("chat")

    if request.method == "GET":
        return render(request, "chat/register.html")

    # -- POST ----------------------------------------------------------------
    email    = request.POST.get("email", "").strip().lower()
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    confirm  = request.POST.get("password_confirm", "")

    errors = []

    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    if not username:
        errors.append("Username is required.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != confirm:
        errors.append("Passwords do not match.")
    if User.objects.filter(username=username).exists():
        errors.append("That username is already taken.")
    if User.objects.filter(email=email).exists():
        errors.append("An account with that email already exists.")

    if errors:
        return render(request, "chat/register.html", {"errors": errors})

    # Create the Django user
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
    )

    # Resolve org from email domain
    domain = _domain_from_email(email)
    org    = Organization.get_or_create_for_domain(domain)

    # Create the profile linking user to org
    UserProfile.objects.create(user=user, organization=org)

    # TODO: email-verification gate — set user.is_active = False here,
    #       send confirmation link, and only activate on token redemption.
    #       For the prototype we activate immediately.

    # Log the user in
    login(request, user)
    _set_org_session(request, user)

    logger.info(
        "New user registered: %s | org: %s | namespace: %s",
        username, org.name, org.pinecone_namespace,
    )

    return redirect("chat")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_view(request):
    """
    GET  → render login form.
    POST → authenticate, refresh session namespace, redirect.
    """
    if request.user.is_authenticated:
        return redirect("chat")

    if request.method == "GET":
        return render(request, "chat/login.html")

    # -- POST ----------------------------------------------------------------
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")

    user = authenticate(request, username=username, password=password)

    if user is None:
        return render(
            request,
            "chat/login.html",
            {"error": "Invalid username or password."},
        )

    if not user.is_active:
        # TODO: redirect to a "check your email" page once email verification
        #       is implemented (see register_view TODO above).
        return render(
            request,
            "chat/login.html",
            {"error": "This account is not yet active."},
        )

    login(request, user)
    namespace = _set_org_session(request, user)

    logger.info(
        "User logged in: %s | namespace: %s", username, namespace
    )

    next_url = request.GET.get("next", "chat")
    return redirect(next_url)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------------------------------------------------------------------
# Chat / query view
# ---------------------------------------------------------------------------

@login_required(login_url="login")
def chat_view(request):
    """
    GET  → render the chat UI.
    POST → run a query through the manager pipeline and return JSON.

    org_namespace is read from the session (set at login/registration).
    It is never trusted from the POST body to prevent namespace spoofing.
    """
    if request.method == "GET":
        return render(request, "chat/chat.html")

    return _handle_query(request)


@login_required(login_url="login")
@require_POST
def query_view(request):
    """
    Dedicated JSON endpoint for AJAX query submission.
    Separated from chat_view so the UI can POST without a full page reload.
    """
    return _handle_query(request)


def _handle_query(request):
    """
    Shared query execution logic.

    Reads org_namespace from the session — never from the request body.
    Injects it into AgentState so all downstream Pinecone calls are scoped
    to the correct namespace automatically.
    """
    try:
        body      = json.loads(request.body)
        query     = body.get("query", "").strip()
        out_fmt   = body.get("output_format", "markdown")
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    if not query:
        return JsonResponse({"error": "Query cannot be empty."}, status=400)

    # Pull namespace from session — set at login, never from untrusted input
    org_namespace = request.session.get(SESSION_ORG_NAMESPACE, "general")

    # Enforce read-only for 'general' namespace: ingestor will refuse to write
    # (ingestor_node checks state["org_namespace"] == "general" and early-returns)
    is_readonly = (org_namespace == "general")

    try:
        # Import here to avoid circular imports at module load time
        from .agents.manager import run_query

        result = run_query(
            query=query,
            org_namespace=org_namespace,
            output_format=out_fmt,
        )

        return JsonResponse({
            "final_answer":        result.get("final_answer", ""),
            "active_agents":       result.get("active_agents", []),
            "errors":              result.get("errors", []),
            "generated_file_path": result.get("generated_file_path"),
            "org_namespace":       org_namespace,
            "readonly":            is_readonly,
        })

    except Exception as e:
        logger.exception("Pipeline error for user %s: %s", request.user.username, e)
        return JsonResponse({"error": f"Pipeline error: {e}"}, status=500)
