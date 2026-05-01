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

import json
import logging
import os
import threading
import time
import uuid

import markdown as md_lib
from django.conf import settings
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from functools import wraps

from . import progress
from .render_helpers import (
    extract_sources,
    friendly_error,
    is_plan_run,
    c3_footer_text,
    agent_pill_label,
    auto_title,
    enrich_downloads,
    plan_outline,
    prefix_heading_ids,
    relative_time,
    sanitize_errors,
    scrub_answer_text,
)
from .demo_tiles import get_demo_tiles

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

# 'toc' adds id="slug" attributes to headings so the plan-panel side rail
# (Milestone D) can deep-link to a section with #slug.
_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br", "toc"]


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
        # Show the welcome interstitial once per session. Cleared by
        # welcome_view so the workspace loads directly on subsequent
        # navigations (logout/login flushes the session, resetting it).
        request.session["show_welcome"] = True
        return redirect("welcome")

    # Localize at request time (gettext, not gettext_lazy): LocaleMiddleware
    # has already activated the right language for this request.
    # House style: replace em dashes with colons.
    error = (
        _("Incorrect password.")
        if DEMO_PASSWORD
        else _("DEMO_PASSWORD is not configured: set it in your .env file.")
    )
    return render(request, "login.html", {"error": error})


def logout_view(request):
    request.session.flush()
    return redirect("login")


# ---------------------------------------------------------------------------
# Welcome interstitial
# ---------------------------------------------------------------------------

@demo_login_required
def welcome_view(request):
    """
    Brief welcome page shown once per session right after login. Auto-
    advances to the chat workspace after a short pause (handled
    client-side in welcome.html). If the user lands here without the
    show_welcome flag set (already saw it this session, or refreshed
    the URL directly later), bounce straight to chat so we never block
    a returning user with an interstitial.
    """
    if not request.session.pop("show_welcome", False):
        return redirect("chat")
    request.session.modified = True
    return render(request, "welcome.html")


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

    # Milestone F: attach a relative-time label to each conv for the sidebar.
    # Backfill created_at on older session entries (pre-Milestone-F) by
    # parsing the legacy timestamp string, falling back to 'now' if it can't
    # be parsed so we never crash on stale session shapes.
    now_ts = int(time.time())
    enriched: list[dict] = []
    for c in conversations:
        created = c.get("created_at")
        if not isinstance(created, (int, float)):
            created = _parse_legacy_timestamp(c.get("timestamp"), now_ts)
            c["created_at"] = created  # persist the backfill
        view_c = dict(c)
        view_c["time_label"] = relative_time(created, now_ts)
        enriched.append(view_c)
    # Persist the backfill so subsequent requests skip it
    request.session["conversations"] = conversations
    request.session.modified = True

    # Milestone R: provider picker options. Built from SUPPORTED_PROVIDERS so
    # the dropdown automatically picks up any new providers Ben adds to the
    # registry. Display names are friendly labels for the UI; the hidden
    # input still posts back the canonical lowercase key.
    from .utils.llm_config import SUPPORTED_PROVIDERS, LLM_PROVIDER
    from .utils.provider_choice import PROVIDER_DISPLAY_NAMES
    provider_options = [
        (key, PROVIDER_DISPLAY_NAMES.get(key, key.title()))
        for key in SUPPORTED_PROVIDERS
    ]

    return render(request, "chat.html", {
        "conversations":    enriched,
        "current_messages": current_messages,
        "current_conv_id":  current_id,
        "demo_tiles":       get_demo_tiles(),  # Milestone G: configurable carousel
        # Milestone R: data for the input-bar provider picker.
        "provider_options":  provider_options,
        "provider_default":  LLM_PROVIDER,
    })


def _parse_legacy_timestamp(ts_str: str | None, fallback: int) -> int:
    """Best-effort parse of the old '%Y-%m-%d %H:%M' timestamp into Unix epoch."""
    if not ts_str:
        return fallback
    try:
        return int(time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M")))
    except (ValueError, TypeError):
        return fallback


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

    # Milestone K: optional A/B-test toggle from the input bar. Truthy
    # strings ("1", "true", "yes", "on") all map to True; everything else
    # to False. Manager will normalize again.
    ab_test_raw = (request.POST.get("ab_test") or "").strip().lower()
    ab_test = ab_test_raw in ("1", "true", "yes", "on")
    # Milestone L: optional plan-mode override from the input-bar toggle.
    # Manager will normalize unknown values to "auto".
    plan_mode = request.POST.get("plan_mode")
    # Milestone R: optional LLM-provider override from the input-bar picker.
    # parse_provider() returns None for empty / unknown values so the
    # pipeline transparently falls back to the env-default provider.
    from .utils.provider_choice import parse_provider, log_choice
    llm_provider = parse_provider(request.POST.get("llm_provider"))
    log_choice(
        provider      = llm_provider,
        query         = query,
        org_namespace = request.session.get("org_namespace", "general"),
        path          = "post",
    )

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

    # ── DEMO_MODE: auto-attach the synthetic Gwinnett voterfile ──────────────
    # When the upload UI is hidden (DEMO_MODE is on) the operator cannot attach
    # a voterfile through the chat. We auto-attach the curated synthetic file
    # so the voterfile + export agents can run and produce a CSV target list.
    # Real uploads (when DEMO_MODE is off) take precedence over the demo file.
    if uploaded_file_path is None and getattr(settings, "DEMO_MODE", False):
        demo_voterfile = os.path.join(
            settings.BASE_DIR, "data", "demo", "gwinnett_demo_voterfile.csv"
        )
        if os.path.exists(demo_voterfile):
            uploaded_file_path = demo_voterfile

    # ── Pipeline ─────────────────────────────────────────────────────────────
    try:
        from .agents.manager import run_query  # deferred import to avoid circular

        result = run_query(
            query            = query,
            org_namespace    = request.session.get("org_namespace", "general"),
            uploaded_file_path = uploaded_file_path,
            ab_test          = ab_test,
            plan_mode        = plan_mode,
            llm_provider     = llm_provider,
        )
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        return render(request, "partials/message.html", {"error": f"Pipeline error: {exc}"})

    print(f"[DEBUG] run_query keys={list(result.keys())} | generated_file_path={result.get('generated_file_path')}", flush=True)

    final_answer        = result.get("final_answer", "")
    active_agents       = result.get("active_agents", [])
    generated_file_path = result.get("generated_file_path")
    errors              = result.get("errors", [])

    # Milestone E: scrub raw agent-error lines the synthesizer sometimes echoes
    # into the answer text. (Errors are sanitised AFTER markdown render below
    # so we can suppress the generic-fallback chip when the answer looks fine.)
    final_answer = scrub_answer_text(final_answer)

    # Bubble id (Milestone D): used to namespace heading anchors so side-panel
    # nav links jump to the right bubble even when multiple plans share section
    # titles. Also used as the data-attr the edit-and-rerun JS targets.
    bubble_id = "b-" + uuid.uuid4().hex[:10]

    # ── Markdown → HTML ───────────────────────────────────────────────────────
    answer_html = md_lib.markdown(final_answer, extensions=_MD_EXTENSIONS)
    answer_html = prefix_heading_ids(answer_html, bubble_id)

    # Now that we know what the rendered answer looks like, drop the generic
    # "agent reported an issue" chip when the deliverable is meaningful. The
    # specific chips (auth, rate-limit, quota) still surface so a real outage
    # is never hidden.
    errors = sanitize_errors(errors, answer_html=answer_html)

    # ── Source cards + plan-run flag (Milestone A: visible intelligence) ─────
    source_cards = extract_sources(result.get("research_results") or [])
    is_plan      = is_plan_run(active_agents)
    c3_footer    = c3_footer_text() if is_plan else None

    # ── Download metadata ─────────────────────────────────────────────────────
    # Build a list of downloads, one entry per generated file. Plans return both
    # a DOCX and a CSV target list; single-topic answers usually return one or none.
    # Older callers may only set generated_file_path, so we fall back to that.
    generated_files = result.get("generated_files") or (
        [generated_file_path] if generated_file_path else []
    )
    _label_by_ext = {
        ".docx": "Download Word Doc",
        ".csv":  "Download CSV",
        ".xlsx": "Download Excel",
    }
    downloads = []
    for fp in generated_files:
        if not fp:
            continue
        fname = os.path.basename(fp)
        ext   = os.path.splitext(fname)[1].lower()
        label = _label_by_ext.get(ext)
        if not label:
            continue
        downloads.append({"filename": fname, "label": label})

    # Backward-compatible single-file fields (first download, if any).
    generated_filename = downloads[0]["filename"] if downloads else None
    download_label     = downloads[0]["label"]    if downloads else None
    if not downloads:
        generated_file_path = None

    # ── Session history ───────────────────────────────────────────────────────
    conversations = request.session.get("conversations", [])
    current_id    = request.session.get("current_conv_id")

    # Find the active conversation, or create a new one
    conv = next((c for c in conversations if c["id"] == current_id), None) if current_id else None
    if conv is None:
        current_id = str(uuid.uuid4())
        conv = {
            "id":         current_id,
            "title":      auto_title(query),
            "timestamp":  time.strftime("%Y-%m-%d %H:%M"),
            "created_at": int(time.time()),  # Milestone F: drives sidebar relative_time()
            "messages":   [],
        }
        conversations.insert(0, conv)
        conversations = conversations[:MAX_CONVERSATIONS]
        request.session["current_conv_id"] = current_id

    # Enrich downloads with thumbnail metadata so both the live render and
    # session-restored history can show typed badges without re-running this.
    downloads = enrich_downloads(downloads)

    # Build the plan-panel outline (Milestone D). Cheap to compute, gated
    # on is_plan_run, so single-topic answers get an empty/no-show payload
    # and the template skips the side panel entirely.
    outline = plan_outline(final_answer, active_agents, source_cards, downloads)

    conv["messages"].append({
        "role":     "user",
        "content":  query,
        "msg_id":   uuid.uuid4().hex[:10],   # for edit-and-rerun targeting
    })
    conv["messages"].append({
        "role":                "assistant",
        "content":             final_answer,
        "answer_html":         answer_html,
        "active_agents":       active_agents,
        "generated_file_path": generated_file_path,
        "generated_filename":  generated_filename,
        "download_label":      download_label,
        "downloads":           downloads,
        "source_cards":        source_cards,
        "c3_footer":           c3_footer,
        "errors":              errors,
        "outline":             outline,
        "bubble_id":           bubble_id,
    })

    request.session["conversations"] = conversations
    request.session.modified = True

    from .utils.provider_choice import provider_label as _provider_label
    return render(request, "partials/message.html", {
        "answer_html":         answer_html,
        "active_agents":       active_agents,
        "generated_file_path": generated_file_path,
        "generated_filename":  generated_filename,
        "download_label":      download_label,
        "downloads":           downloads,
        "source_cards":        source_cards,
        "c3_footer":           c3_footer,
        "errors":              errors,
        "outline":             outline,
        "bubble_id":           bubble_id,
        # Milestone R: "Powered by" chip on the response bubble.
        "provider_label":      _provider_label(llm_provider),
    })


# ---------------------------------------------------------------------------
# Streaming endpoint (Milestone A: visible intelligence)
# ---------------------------------------------------------------------------
#
# The browser opens an EventSource against /stream/?query=... and watches the
# pipeline run live. The agent worker runs on a background thread and pushes
# progress events onto an in-process queue. The generator below drains that
# queue, formats each event as SSE, and emits a final "done" event with the
# rendered HTML once the worker finishes. No Redis, no extra deps.
#
# Why one connection (not two): a separate /send/ + /events/ pair would force
# us to share the run's final state across requests, which without Redis means
# global dicts that race. Streaming the result back on the same connection
# keeps the lifetime of the run scoped to one HTTP request.

def _format_sse(event_dict: dict) -> str:
    """Serialize a payload as a single SSE ``data:`` frame."""
    return f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"


@demo_login_required
def stream_query_view(request):
    """
    SSE endpoint that runs the pipeline and streams agent progress in real
    time. The final "done" event carries the rendered HTML the chat UI swaps
    into the message thread, so a single request covers both the live trace
    and the final answer.

    Query parameters (GET):
        query — the user's prompt (required)

    File uploads are not supported on this endpoint; the existing /send/
    HTMX path remains for upload flows. Demo mode auto-attaches the synthetic
    voterfile here too, mirroring /send/.
    """
    query = request.GET.get("query", "").strip()
    if not query:
        return HttpResponse("query parameter required", status=400)

    # Milestone K: optional A/B-test toggle from the input bar.
    ab_test_raw = (request.GET.get("ab_test") or "").strip().lower()
    ab_test = ab_test_raw in ("1", "true", "yes", "on")
    # Milestone L: optional plan-mode override from the input-bar toggle.
    plan_mode = request.GET.get("plan_mode")
    # Milestone R: optional LLM-provider override from the input-bar picker.
    from .utils.provider_choice import parse_provider, log_choice
    llm_provider = parse_provider(request.GET.get("llm_provider"))
    log_choice(
        provider      = llm_provider,
        query         = query,
        org_namespace = request.session.get("org_namespace", "general"),
        path          = "stream",
    )

    org_namespace = request.session.get("org_namespace", "general")

    # Demo mode: auto-attach the synthetic Gwinnett voterfile so the voterfile
    # and export agents can run end-to-end without a real upload.
    uploaded_file_path = None
    if getattr(settings, "DEMO_MODE", False):
        demo_voterfile = os.path.join(
            settings.BASE_DIR, "data", "demo", "gwinnett_demo_voterfile.csv"
        )
        if os.path.exists(demo_voterfile):
            uploaded_file_path = demo_voterfile

    run_id = progress.new_run_id()
    progress.create(run_id)

    # Holders the worker writes into; the generator reads them after the run
    # is signalled done. Using a dict keeps it picklable-free and obvious.
    holder: dict = {"result": None, "error": None}

    def _worker():
        try:
            from .agents.manager import run_query_streaming  # deferred import
            holder["result"] = run_query_streaming(
                query              = query,
                org_namespace      = org_namespace,
                run_id             = run_id,
                uploaded_file_path = uploaded_file_path,
                ab_test            = ab_test,
                plan_mode          = plan_mode,
                llm_provider       = llm_provider,
            )
        except Exception as exc:
            logger.exception("Streaming pipeline error: %s", exc)
            holder["error"] = str(exc)
        finally:
            # Tell the consumer the run is done so the drain loop can exit.
            progress.emit(run_id, "run_finished")

    worker_thread = threading.Thread(target=_worker, daemon=True)

    def _event_stream():
        # Initial frame so the EventSource ``onopen`` settles before we run.
        yield _format_sse({"type": "hello", "run_id": run_id})
        worker_thread.start()
        try:
            for evt in progress.drain(run_id):
                # The wrapper signals completion via run_finished, which we do
                # not forward; we exit the loop and emit a final ``done`` frame
                # carrying the rendered HTML.
                if evt.type == "run_finished":
                    break
                yield _format_sse(evt.to_dict())

            # Wait for the worker to finish (almost always already done by
            # the time run_finished arrived; this is just paranoia for slow
            # interpreters).
            worker_thread.join(timeout=5.0)

            if holder["error"]:
                # Milestone E: map raw exceptions (e.g. AuthenticationError
                # from the LLM client) to a short, human label before it
                # reaches the EventSource handler in chat.html.
                yield _format_sse({
                    "type": "error",
                    "label": friendly_error(holder["error"]),
                })
                return

            result = holder["result"] or {}
            payload = _build_done_payload(request, query, result)
            yield _format_sse(payload)
        finally:
            progress.finish(run_id)

    response = StreamingHttpResponse(_event_stream(), content_type="text/event-stream")
    response["Cache-Control"]    = "no-cache"
    response["X-Accel-Buffering"] = "no"   # disable proxy buffering on Render/nginx
    return response


def _build_done_payload(request, query: str, result: dict) -> dict:
    """
    Render the final assistant bubble HTML from a completed pipeline result
    and persist the message into the user's session, mirroring the
    side-effects of ``send_message_view`` so reloads show the same history.
    """
    final_answer        = result.get("final_answer", "")
    active_agents       = result.get("active_agents", [])
    generated_file_path = result.get("generated_file_path")
    errors              = result.get("errors", [])

    # Milestone E: same scrubbing as the HTMX path so SSE clients see the
    # friendly error chip and a clean answer rather than raw 401 dumps.
    final_answer = scrub_answer_text(final_answer)

    bubble_id = "b-" + uuid.uuid4().hex[:10]
    answer_html  = md_lib.markdown(final_answer, extensions=_MD_EXTENSIONS)
    answer_html  = prefix_heading_ids(answer_html, bubble_id)

    # Suppress the generic-fallback chip when the rendered answer is meaningful
    # (matches /send/ behaviour added with the chip-noise fix).
    errors = sanitize_errors(errors, answer_html=answer_html)
    source_cards = extract_sources(result.get("research_results") or [])
    is_plan      = is_plan_run(active_agents)
    c3_footer    = c3_footer_text() if is_plan else None

    generated_files = result.get("generated_files") or (
        [generated_file_path] if generated_file_path else []
    )
    _label_by_ext = {
        ".docx": "Download Word Doc",
        ".csv":  "Download CSV",
        ".xlsx": "Download Excel",
    }
    downloads = []
    for fp in generated_files:
        if not fp:
            continue
        fname = os.path.basename(fp)
        ext   = os.path.splitext(fname)[1].lower()
        label = _label_by_ext.get(ext)
        if not label:
            continue
        downloads.append({"filename": fname, "label": label})

    generated_filename = downloads[0]["filename"] if downloads else None
    download_label     = downloads[0]["label"]    if downloads else None
    if not downloads:
        generated_file_path = None

    # Attach thumbnail metadata (kind/color) so download cards render with
    # typed badges in both the live bubble and any session-restored history.
    downloads = enrich_downloads(downloads)

    # Plan outline for the side panel (Milestone D).
    outline = plan_outline(final_answer, active_agents, source_cards, downloads)

    from .utils.provider_choice import provider_label as _provider_label
    bubble_html = render_to_string("partials/message.html", {
        "answer_html":         answer_html,
        "active_agents":       active_agents,
        "generated_file_path": generated_file_path,
        "generated_filename":  generated_filename,
        "download_label":      download_label,
        "downloads":           downloads,
        "source_cards":        source_cards,
        "c3_footer":           c3_footer,
        "errors":              errors,
        "outline":             outline,
        "bubble_id":           bubble_id,
        # Milestone R: "Powered by" chip on the response bubble.
        "provider_label":      _provider_label(llm_provider),
    }, request=request)

    # Persist into the session so refreshes show the same history.
    conversations = request.session.get("conversations", [])
    current_id    = request.session.get("current_conv_id")
    conv = next((c for c in conversations if c["id"] == current_id), None) if current_id else None
    if conv is None:
        current_id = str(uuid.uuid4())
        conv = {
            "id":         current_id,
            "title":      auto_title(query),
            "timestamp":  time.strftime("%Y-%m-%d %H:%M"),
            "created_at": int(time.time()),  # Milestone F: drives sidebar relative_time()
            "messages":   [],
        }
        conversations.insert(0, conv)
        conversations = conversations[:MAX_CONVERSATIONS]
        request.session["current_conv_id"] = current_id

    conv["messages"].append({
        "role":     "user",
        "content":  query,
        "msg_id":   uuid.uuid4().hex[:10],
    })
    conv["messages"].append({
        "role":                "assistant",
        "content":             final_answer,
        "answer_html":         answer_html,
        "active_agents":       active_agents,
        "generated_file_path": generated_file_path,
        "generated_filename":  generated_filename,
        "download_label":      download_label,
        "downloads":           downloads,
        "source_cards":        source_cards,
        "c3_footer":           c3_footer,
        "errors":              errors,
        "outline":             outline,
        "bubble_id":           bubble_id,
    })
    request.session["conversations"] = conversations
    request.session.modified = True

    # Streaming-response gotcha: SessionMiddleware.process_response runs BEFORE
    # the StreamingHttpResponse generator yields, so by the time we mutate the
    # session here it's too late to be auto-saved at the end of the request.
    # Force an explicit save so SSE-completed turns persist into the sidebar
    # history just like /send/ HTMX turns do.
    try:
        request.session.save()
    except Exception:
        # Never let a session-store hiccup crash the SSE done frame; the bubble
        # was already rendered to the client.
        logger.exception("Failed to save session on SSE done frame")

    return {
        "type":          "done",
        "html":          bubble_html,
        "active_agents": active_agents,
        "sources_count": len(source_cards),
        "downloads_count": len(downloads),
        "plan_panel":    outline.get("show_panel", False),
    }


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

# ---------------------------------------------------------------------------
# Conversation management API (Milestone F)
# ---------------------------------------------------------------------------
#
# Three small JSON endpoints power the sidebar history UI. They all use the
# same request.session["conversations"] list as the rest of the app, so no
# database migration is required. Each one:
#   - requires the demo session (auth decorator)
#   - is POST-only (CSRF enforced by Django middleware)
#   - returns a JSON status payload, never an HTML page
#   - is no-op-safe: missing IDs return 404 cleanly
#
# Body parsing accepts either form-encoded or application/json so the
# frontend fetch() call can stay minimal (JSON.stringify with a CSRF header).

def _read_json_body(request) -> dict:
    """
    Best-effort body parse: prefer JSON, fall back to form-encoded.
    Returns an empty dict on parse failure so callers don't have to wrap
    every access in a try block.
    """
    ctype = request.content_type or ""
    if "application/json" in ctype:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    # Form-encoded fallback
    return dict(request.POST.items())


@demo_login_required
@require_POST
def rename_conv_view(request, conv_id: str):
    """
    Update a conversation's title. Body: {"title": "<new title>"}.
    Trims whitespace, rejects empty, caps at 80 chars to keep the sidebar tidy.
    Returns: 200 {"ok": True, "title": "..."} | 400 invalid | 404 missing.
    """
    body  = _read_json_body(request)
    title = (body.get("title") or "").strip()
    if not title:
        return HttpResponse(
            json.dumps({"ok": False, "error": "Title cannot be empty"}),
            status=400, content_type="application/json",
        )
    if len(title) > 80:
        title = title[:80].rstrip()

    conversations = request.session.get("conversations", [])
    for c in conversations:
        if c.get("id") == conv_id:
            c["title"] = title
            request.session["conversations"] = conversations
            request.session.modified = True
            return HttpResponse(
                json.dumps({"ok": True, "title": title}),
                status=200, content_type="application/json",
            )
    return HttpResponse(
        json.dumps({"ok": False, "error": "Conversation not found"}),
        status=404, content_type="application/json",
    )


@demo_login_required
@require_POST
def delete_conv_view(request, conv_id: str):
    """
    Remove a conversation from the sidebar list. If the active conversation
    was deleted, clear current_conv_id so the next chat view falls back to
    the empty-state landing page instead of pointing at a dead reference.
    Returns: 200 {"ok": True} | 404 missing.
    """
    conversations = request.session.get("conversations", [])
    new_list = [c for c in conversations if c.get("id") != conv_id]
    if len(new_list) == len(conversations):
        return HttpResponse(
            json.dumps({"ok": False, "error": "Conversation not found"}),
            status=404, content_type="application/json",
        )
    request.session["conversations"] = new_list
    if request.session.get("current_conv_id") == conv_id:
        request.session["current_conv_id"] = None
    request.session.modified = True
    return HttpResponse(
        json.dumps({"ok": True}),
        status=200, content_type="application/json",
    )


@demo_login_required
@require_POST
def reorder_conv_view(request):
    """
    Reorder the conversation list. Body: {"order": ["<id1>", "<id2>", ...]}.
    Items appearing in 'order' are arranged in that sequence; items not
    listed are appended at the end in their original relative order so a
    partial payload (e.g. only the visible ones) doesn't lose anything.
    Returns: 200 {"ok": True, "order": [...]} | 400 invalid body.
    """
    body  = _read_json_body(request)
    order = body.get("order")
    if not isinstance(order, list) or any(not isinstance(x, str) for x in order):
        return HttpResponse(
            json.dumps({"ok": False, "error": "Body must be {order: [str, ...]}"}),
            status=400, content_type="application/json",
        )

    conversations = request.session.get("conversations", [])
    by_id = {c.get("id"): c for c in conversations}
    seen: set[str] = set()
    new_list: list[dict] = []
    for cid in order:
        if cid in by_id and cid not in seen:
            new_list.append(by_id[cid])
            seen.add(cid)
    # Tail: anything not mentioned, in original order
    for c in conversations:
        if c.get("id") not in seen:
            new_list.append(c)

    request.session["conversations"] = new_list
    request.session.modified = True
    return HttpResponse(
        json.dumps({"ok": True, "order": [c.get("id") for c in new_list]}),
        status=200, content_type="application/json",
    )
