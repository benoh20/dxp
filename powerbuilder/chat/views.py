# chat/views.py
"""
Powerbuilder — demo auth + pipeline views.

Demo authentication uses a single shared password stored in the environment.
Add to your .env file:
    DEMO_PASSWORD=your_secure_password_here

Session keys
------------
    authenticated       bool  — set to True on successful login
    conversations       list  — [{id, title, timestamp, messages: [...]}]
    current_conv_id     str   — UUID of the active conversation
    org_namespace       str   — Pinecone namespace (default "general")
"""

import logging
import os
import time
import uuid

import markdown as md_lib
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from functools import wraps

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Set DEMO_PASSWORD=<value> in .env
DEMO_PASSWORD    = os.environ.get("DEMO_PASSWORD", "")
UPLOAD_DIR       = "data/uploads"
EXPORTS_DIR      = "exports"
MAX_CONVERSATIONS = 20

_ALLOWED_DOWNLOAD_EXTS = {".docx", ".csv", ".xlsx"}

_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br"]


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def demo_login_required(view_func):
    """Redirect to /login/ if the session is not authenticated."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("authenticated"):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return _wrapped


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

def login_view(request):
    """
    GET  → render login form.
    POST → check DEMO_PASSWORD, set session, redirect to chat.
    """
    if request.session.get("authenticated"):
        return redirect("chat")

    if request.method == "GET":
        return render(request, "login.html")

    password = request.POST.get("password", "")

    if DEMO_PASSWORD and password == DEMO_PASSWORD:
        request.session["authenticated"] = True
        request.session["org_namespace"] = "general"
        return redirect("chat")

    error = (
        "Incorrect password."
        if DEMO_PASSWORD
        else "DEMO_PASSWORD is not configured — set it in your .env file."
    )
    return render(request, "login.html", {"error": error})


def logout_view(request):
    request.session.flush()
    return redirect("login")


# ---------------------------------------------------------------------------
# Chat page
# ---------------------------------------------------------------------------

@demo_login_required
def chat_view(request):
    """
    Renders the chat UI.

    Query parameters (GET):
        ?new=1       — start a new conversation (clears current_conv_id)
        ?conv=<id>   — switch to an existing conversation by ID
    """
    if request.GET.get("new"):
        request.session["current_conv_id"] = None
        request.session.modified = True
        return redirect("chat")

    if conv_id := request.GET.get("conv"):
        request.session["current_conv_id"] = conv_id
        request.session.modified = True
        return redirect("chat")

    conversations  = request.session.get("conversations", [])
    current_id     = request.session.get("current_conv_id")
    current_messages: list = []

    if current_id:
        conv = next((c for c in conversations if c["id"] == current_id), None)
        if conv:
            current_messages = conv.get("messages", [])

    return render(request, "chat.html", {
        "conversations":    conversations,
        "current_messages": current_messages,
        "current_conv_id":  current_id,
    })


# ---------------------------------------------------------------------------
# Send message (HTMX endpoint)
# ---------------------------------------------------------------------------

@demo_login_required
@require_POST
def send_message_view(request):
    """
    Accepts a query (and optional file upload), runs it through the pipeline,
    stores the result in the session, and returns a rendered HTMX partial
    (templates/partials/message.html) containing the assistant message bubble.
    """
    query = request.POST.get("query", "").strip()
    if not query:
        return render(request, "partials/message.html", {"error": "Query cannot be empty."})

    # ── File upload ──────────────────────────────────────────────────────────
    uploaded_file_path = None
    uploaded_file = request.FILES.get("file")
    if uploaded_file:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        # Sanitise filename: keep alphanumerics + safe punctuation, collapse the rest
        raw_name  = uploaded_file.name or "upload"
        safe_name = "".join(c if (c.isalnum() or c in "._-") else "_" for c in raw_name)
        filename  = f"{int(time.time())}_{safe_name}"
        dest      = os.path.join(UPLOAD_DIR, filename)
        with open(dest, "wb") as fh:
            for chunk in uploaded_file.chunks():
                fh.write(chunk)
        uploaded_file_path = dest

    # ── Pipeline ─────────────────────────────────────────────────────────────
    try:
        from .agents.manager import run_query  # deferred import to avoid circular

        result = run_query(
            query            = query,
            org_namespace    = request.session.get("org_namespace", "general"),
            uploaded_file_path = uploaded_file_path,
        )
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        return render(request, "partials/message.html", {"error": f"Pipeline error: {exc}"})

    print(f"[DEBUG] run_query keys={list(result.keys())} | generated_file_path={result.get('generated_file_path')}", flush=True)

    final_answer        = result.get("final_answer", "")
    active_agents       = result.get("active_agents", [])
    generated_file_path = result.get("generated_file_path")
    errors              = result.get("errors", [])

    # ── Markdown → HTML ───────────────────────────────────────────────────────
    answer_html = md_lib.markdown(final_answer, extensions=_MD_EXTENSIONS)

    # ── Download metadata ─────────────────────────────────────────────────────
    generated_filename = None
    download_label     = None
    if generated_file_path:
        generated_filename = os.path.basename(generated_file_path)
        ext = os.path.splitext(generated_filename)[1].lower()
        if ext == ".docx":
            download_label = "Download Word Doc"
        elif ext == ".csv":
            download_label = "Download CSV"
        elif ext == ".xlsx":
            download_label = "Download Excel"
        else:
            generated_file_path = None
            generated_filename  = None

    # ── Session history ───────────────────────────────────────────────────────
    conversations = request.session.get("conversations", [])
    current_id    = request.session.get("current_conv_id")

    # Find the active conversation, or create a new one
    conv = next((c for c in conversations if c["id"] == current_id), None) if current_id else None
    if conv is None:
        current_id = str(uuid.uuid4())
        conv = {
            "id":        current_id,
            "title":     query[:40],
            "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            "messages":  [],
        }
        conversations.insert(0, conv)
        conversations = conversations[:MAX_CONVERSATIONS]
        request.session["current_conv_id"] = current_id

    conv["messages"].append({"role": "user", "content": query})
    conv["messages"].append({
        "role":                "assistant",
        "content":             final_answer,
        "answer_html":         answer_html,
        "active_agents":       active_agents,
        "generated_file_path": generated_file_path,
        "generated_filename":  generated_filename,
        "download_label":      download_label,
        "errors":              errors,
    })

    request.session["conversations"] = conversations
    request.session.modified = True

    return render(request, "partials/message.html", {
        "answer_html":         answer_html,
        "active_agents":       active_agents,
        "generated_file_path": generated_file_path,
        "generated_filename":  generated_filename,
        "download_label":      download_label,
        "errors":              errors,
    })


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------

@demo_login_required
def download_view(request, filename: str):
    """
    Serves a file from the exports/ directory as an attachment.
    Only .docx and .csv extensions are permitted; path traversal is rejected.
    """
    # Security checks
    if "/" in filename or "\\" in filename or ".." in filename:
        raise Http404

    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_DOWNLOAD_EXTS:
        raise Http404

    filepath = os.path.join(EXPORTS_DIR, filename)
    if not os.path.isfile(filepath):
        raise Http404

    with open(filepath, "rb") as fh:
        content = fh.read()

    content_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".csv":  "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    response = HttpResponse(content, content_type=content_types[ext])
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
