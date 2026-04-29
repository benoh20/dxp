"""
Milestone Q (i18n): verifies Spanish and Vietnamese plumbing.

Sections:
  (A) settings.py: LANGUAGES tuple has en/es/vi, LocaleMiddleware in chain,
      LOCALE_PATHS pointing at project locale/.
  (B) URLs: /i18n/setlang/ route reachable.
  (C) Templates load i18n: base.html, chat.html, login.html each
      `{% load i18n %}` and use {% trans %} or {% blocktrans %}.
  (D) base.html: language switcher form, dynamic <html lang>, three
      switcher buttons (one per locale).
  (E) .po files exist for es and vi, are non-empty, and translate the
      core UI strings.
  (F) .mo files compiled.
  (G) Activate() per locale: gettext() returns the translated string for
      a known msgid in es and vi.
  (H) Render base.html with translation activated and confirm Spanish
      strings appear (e.g. "Iniciar sesión" or "Nueva conversación").

Setup pattern matches the rest of the suite.
"""

import os, sys, html, re
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-validation-only")
os.environ["DEBUG"] = "True"
import django
django.setup()

PASS = []

def expect(cond, msg):
    if not cond:
        print(f"  FAIL: {msg}")
    assert cond, f"FAIL: {msg}"
    PASS.append(msg)

TEMPLATES = PROJECT_DIR / "templates"
LOCALE = PROJECT_DIR / "locale"
BASE = (TEMPLATES / "base.html").read_text()
CHAT = (TEMPLATES / "chat.html").read_text()
LOGIN = (TEMPLATES / "login.html").read_text()

# ═══════════════════════════════════════════════════════════════════════
print("=== (A) settings.py i18n wiring ===")
n = 0
from django.conf import settings as dj_settings

codes = [code for code, _ in dj_settings.LANGUAGES]
expect("en" in codes, "LANGUAGES includes 'en'")
n += 1
expect("es" in codes, "LANGUAGES includes 'es'")
n += 1
expect("vi" in codes, "LANGUAGES includes 'vi'")
n += 1
expect("django.middleware.locale.LocaleMiddleware" in dj_settings.MIDDLEWARE,
       "LocaleMiddleware in MIDDLEWARE")
n += 1
expect(any(str(p).endswith("locale") for p in dj_settings.LOCALE_PATHS),
       "LOCALE_PATHS contains a 'locale' directory")
n += 1
expect(dj_settings.USE_I18N is True, "USE_I18N = True")
n += 1
print(f"PASS section A: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print("=== (B) /i18n/setlang/ route resolves ===")
n = 0
from django.urls import reverse
url = reverse("set_language")
expect(url.endswith("/setlang/"), f"set_language reverses to a /setlang/ URL (got {url})")
n += 1
print(f"PASS section B: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print("=== (C) Templates load i18n ===")
n = 0
for label, src in [("base.html", BASE), ("chat.html", CHAT), ("login.html", LOGIN)]:
    expect("{% load i18n %}" in src, f"{label} loads i18n")
    n += 1
    expect(("{% trans " in src) or ("{% blocktrans" in src),
           f"{label} uses {{% trans %}} or {{% blocktrans %}}")
    n += 1
print(f"PASS section C: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print("=== (D) base.html: dynamic lang + language switcher ===")
n = 0
expect("{% get_current_language as LANGUAGE_CODE %}" in BASE,
       "base.html captures LANGUAGE_CODE")
n += 1
expect(re.search(r'<html lang="\{\{\s*LANGUAGE_CODE', BASE),
       "<html lang> uses LANGUAGE_CODE template var")
n += 1
expect("{% url 'set_language' %}" in BASE,
       "language switcher posts to set_language URL")
n += 1
expect("get_available_languages" in BASE,
       "switcher iterates get_available_languages")
n += 1
expect('aria-pressed=' in BASE,
       "switcher buttons expose aria-pressed for the active language")
n += 1
print(f"PASS section D: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print("=== (E) .po files present and translated ===")
n = 0
for code in ("es", "vi"):
    po = LOCALE / code / "LC_MESSAGES" / "django.po"
    expect(po.exists(), f"locale/{code}/LC_MESSAGES/django.po exists")
    n += 1
    src = po.read_text()
    expect(f'"Language: {code}\\n"' in src, f"{code} po file declares Language: {code}")
    n += 1
    # Spot-check that core strings have non-empty translations
    for needle in [
        'msgid "New conversation"',
        'msgid "Sign in"',
        'msgid "Password"',
    ]:
        idx = src.find(needle)
        expect(idx >= 0, f"{code} po file contains: {needle}")
        n += 1
        # The msgstr immediately after should be non-empty
        rest = src[idx:idx + 400]
        m = re.search(r'msgstr\s+"([^"]*)"', rest)
        expect(m and m.group(1).strip(),
               f"{code} po file: '{needle}' has a non-empty msgstr")
        n += 1
print(f"PASS section E: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print("=== (F) .mo files compiled ===")
n = 0
for code in ("es", "vi"):
    mo = LOCALE / code / "LC_MESSAGES" / "django.mo"
    expect(mo.exists(), f"locale/{code}/LC_MESSAGES/django.mo exists")
    n += 1
    expect(mo.stat().st_size > 200, f"{code} django.mo is non-trivially sized")
    n += 1
print(f"PASS section F: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print("=== (G) gettext returns translations per locale ===")
n = 0
from django.utils.translation import activate, gettext, deactivate

activate("es")
es_new = gettext("New conversation")
expect(es_new == "Nueva conversación",
       f"Spanish 'New conversation' -> 'Nueva conversación' (got: {es_new!r})")
n += 1
es_signin = gettext("Sign in")
expect(es_signin == "Iniciar sesión",
       f"Spanish 'Sign in' -> 'Iniciar sesión' (got: {es_signin!r})")
n += 1

activate("vi")
vi_new = gettext("New conversation")
expect(vi_new == "Cuộc trò chuyện mới",
       f"Vietnamese 'New conversation' translated (got: {vi_new!r})")
n += 1
vi_signin = gettext("Sign in")
expect(vi_signin == "Đăng nhập",
       f"Vietnamese 'Sign in' -> 'Đăng nhập' (got: {vi_signin!r})")
n += 1

# English should pass through unchanged
activate("en")
expect(gettext("New conversation") == "New conversation",
       "English passthrough for 'New conversation'")
n += 1
deactivate()
print(f"PASS section G: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print("=== (H) Rendered login template contains translated strings ===")
n = 0
from django.template.loader import render_to_string
from django.test import RequestFactory

rf = RequestFactory()
req = rf.get("/login/")

activate("es")
rendered_es = render_to_string("login.html", request=req)
rendered_es = html.unescape(rendered_es)
expect("Iniciar sesión" in rendered_es,
       "Rendered es login.html contains 'Iniciar sesión'")
n += 1
expect("Contraseña" in rendered_es,
       "Rendered es login.html contains 'Contraseña'")
n += 1

activate("vi")
rendered_vi = render_to_string("login.html", request=req)
rendered_vi = html.unescape(rendered_vi)
expect("Đăng nhập" in rendered_vi,
       "Rendered vi login.html contains 'Đăng nhập'")
n += 1
expect("Mật khẩu" in rendered_vi,
       "Rendered vi login.html contains 'Mật khẩu'")
n += 1
deactivate()
print(f"PASS section H: {n} checks")

# ═══════════════════════════════════════════════════════════════════════
print()
print(f"ALL PASS — _test_i18n.py ran {len(PASS)} assertions")
