"""
One-shot helper: fill in Spanish and Vietnamese translations for the
login-flow strings flagged during the audit (login error messages and
the global skip-to-content link).

Also strips the `#, fuzzy` marker so gettext will actually use the
translation at runtime (fuzzy entries fall through to the msgid).

Idempotent. Run from /powerbuilder:
    ./venv/bin/python scripts/_fill_login_translations.py
then recompile:
    msgfmt locale/es/LC_MESSAGES/django.po -o locale/es/LC_MESSAGES/django.mo
    msgfmt locale/vi/LC_MESSAGES/django.po -o locale/vi/LC_MESSAGES/django.mo
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

ES = {
    "Incorrect password.":                            "Contraseña incorrecta.",
    "DEMO_PASSWORD is not configured: set it in your .env file.":
        "DEMO_PASSWORD no está configurada: defínela en tu archivo .env.",
    "Skip to content":                                "Saltar al contenido",
}

# Vietnamese — DRAFT, pending native-speaker review (consistent with the
# rest of the VI .po file's translator note).
VI = {
    "Incorrect password.":                            "Mật khẩu không đúng.",
    "DEMO_PASSWORD is not configured: set it in your .env file.":
        "DEMO_PASSWORD chưa được cấu hình: hãy đặt nó trong tệp .env của bạn.",
    "Skip to content":                                "Bỏ qua đến nội dung chính",
}

# Match a single .po entry: optional comment lines (including #, fuzzy and
# #| previous-msgid hints), then msgid block, then msgstr block.
ENTRY_RE = re.compile(
    r'((?:^#[^\n]*\n)*)'           # group 1: leading comment lines
    r'(msgid (?:"[^"\n]*"\s*\n?)+)'  # group 2: msgid block
    r'(msgstr (?:"[^"\n]*"\s*\n?)+)',  # group 3: msgstr block
    re.MULTILINE,
)


def _decode_msgid(block: str) -> str:
    parts = re.findall(r'"((?:\\.|[^"\\])*)"', block)
    raw = "".join(parts)
    return (
        raw.replace(r"\n", "\n")
           .replace(r"\t", "\t")
           .replace(r"\"", '"')
           .replace(r"\\", "\\")
    )


def _encode_msgstr(s: str) -> str:
    escaped = (
        s.replace("\\", r"\\")
         .replace('"', r"\"")
         .replace("\n", r"\n")
    )
    if len(escaped) <= 70:
        return f'msgstr "{escaped}"\n'
    chunks: list[str] = []
    cur = ""
    for word in escaped.split(" "):
        candidate = (cur + " " + word) if cur else word
        if len(candidate) > 70:
            chunks.append(cur)
            cur = word
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    body = "".join(f'"{c} "\n' if i < len(chunks) - 1 else f'"{c}"\n'
                   for i, c in enumerate(chunks))
    return 'msgstr ""\n' + body


def _strip_fuzzy(comments: str) -> str:
    """Drop `#, fuzzy` markers (and their `#| previous` hint lines) so
    gettext starts using our translation at runtime."""
    out_lines = []
    for line in comments.splitlines(keepends=True):
        # Drop fuzzy flag lines and previous-msgid hints
        if line.startswith("#, ") and "fuzzy" in line:
            # If line is exactly "#, fuzzy\n" drop it; if it's
            # "#, fuzzy, python-format" keep the rest of the flags.
            cleaned = line.replace("fuzzy,", "").replace(", fuzzy", "")
            cleaned = cleaned.replace("fuzzy", "").rstrip(", \n")
            if cleaned.strip() == "#,":
                continue
            out_lines.append(cleaned + "\n")
            continue
        if line.startswith("#|"):
            # Previous-msgid hints are only meaningful alongside fuzzy.
            continue
        out_lines.append(line)
    return "".join(out_lines)


def patch_po(po_path: Path, table: dict[str, str]) -> int:
    src = po_path.read_text()
    n_filled = 0

    def replace(match: re.Match) -> str:
        nonlocal n_filled
        comments_block = match.group(1)
        msgid_block = match.group(2)
        msgstr_block = match.group(3)
        msgid = _decode_msgid(msgid_block)
        if msgid in table:
            new_comments = _strip_fuzzy(comments_block)
            new_msgstr = _encode_msgstr(table[msgid])
            n_filled += 1
            return new_comments + msgid_block + new_msgstr
        return match.group(0)

    new_src = ENTRY_RE.sub(replace, src)
    if new_src != src:
        po_path.write_text(new_src)
    return n_filled


def main() -> int:
    es_path = PROJECT_DIR / "locale" / "es" / "LC_MESSAGES" / "django.po"
    vi_path = PROJECT_DIR / "locale" / "vi" / "LC_MESSAGES" / "django.po"

    es_n = patch_po(es_path, ES)
    vi_n = patch_po(vi_path, VI)

    print(f"Spanish:    filled {es_n} / {len(ES)} login-flow msgstr entries")
    print(f"Vietnamese: filled {vi_n} / {len(VI)} login-flow msgstr entries")

    if es_n != len(ES) or vi_n != len(VI):
        print("WARN: some msgids were not found. Re-run makemessages and "
              "verify the source strings match.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
