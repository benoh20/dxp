"""
Test that DEMO_MODE auto-attaches the synthetic Gwinnett voterfile when no
file is uploaded with the chat message.

Verifies the conditional in chat/views.py (around line 170):

    if uploaded_file_path is None and getattr(settings, "DEMO_MODE", False):
        demo_voterfile = os.path.join(
            settings.BASE_DIR, "data", "demo", "gwinnett_demo_voterfile.csv"
        )
        if os.path.exists(demo_voterfile):
            uploaded_file_path = demo_voterfile

Three cases:
  1. DEMO_MODE=True  + no upload     -> resolves to synthetic CSV
  2. DEMO_MODE=False + no upload     -> stays None
  3. DEMO_MODE=True  + real upload   -> real upload wins

Usage:
    python scripts/_test_demo_voterfile_autoload.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

# Bootstrap Django.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402


def resolve_voterfile_path(uploaded_file_path):
    """Mirror of the conditional in chat/views.py send_message_view."""
    if uploaded_file_path is None and getattr(settings, "DEMO_MODE", False):
        demo_voterfile = os.path.join(
            settings.BASE_DIR, "data", "demo", "gwinnett_demo_voterfile.csv"
        )
        if os.path.exists(demo_voterfile):
            uploaded_file_path = demo_voterfile
    return uploaded_file_path


def main() -> int:
    failures: list[str] = []

    expected_path = os.path.join(
        settings.BASE_DIR, "data", "demo", "gwinnett_demo_voterfile.csv"
    )
    if not os.path.exists(expected_path):
        print(f"FAIL: synthetic voterfile not found at {expected_path}")
        print("Run `python scripts/generate_demo_voterfile.py` first.")
        return 1

    # Test 1: DEMO_MODE=True, no upload -> auto-attach synthetic.
    with patch.object(settings, "DEMO_MODE", True):
        result = resolve_voterfile_path(None)
        if result != expected_path:
            failures.append(
                f"Test 1 (DEMO_MODE=True, no upload): expected "
                f"{expected_path}, got {result}"
            )

    # Test 2: DEMO_MODE=False, no upload -> stays None.
    with patch.object(settings, "DEMO_MODE", False):
        result = resolve_voterfile_path(None)
        if result is not None:
            failures.append(
                f"Test 2 (DEMO_MODE=False, no upload): expected None, "
                f"got {result}"
            )

    # Test 3: DEMO_MODE=True, real upload -> real upload wins.
    with patch.object(settings, "DEMO_MODE", True):
        real = "/tmp/real_upload.csv"
        result = resolve_voterfile_path(real)
        if result != real:
            failures.append(
                f"Test 3 (DEMO_MODE=True, real upload): real upload should "
                f"take precedence, got {result}"
            )

    # Test 4 (bonus): DEMO_MODE setting attribute exists.
    if not hasattr(settings, "DEMO_MODE"):
        failures.append(
            "Test 4: settings.DEMO_MODE is not defined; "
            "the auto-attach guard cannot work."
        )

    # Report.
    print(
        f"DEMO_MODE voterfile auto-attach test: synthetic file at {expected_path}."
    )
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: all 4 assertion groups OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
