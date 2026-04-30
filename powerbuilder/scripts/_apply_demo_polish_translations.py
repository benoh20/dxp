"""
Fill in ES + VI translations for the demo-polish strings (theme switcher,
A/B toggle, plan-mode toggle). Run after `manage.py makemessages` so the
empty msgstr entries already exist; this script only updates rows whose
msgstr is currently blank.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Translations chosen to match tone used in the rest of the UI (organizer
# voice, no marketing-speak, parenthetical asides for clarification).
ES = {
    "Theme": "Tema",
    "System": "Sistema",
    "Light": "Claro",
    "Dark": "Oscuro",
    "Follow your device setting": "Sigue la preferencia del dispositivo",
    "Always light": "Siempre claro",
    "Always dark": "Siempre oscuro",
    "A/B test toggle": "Activar prueba A/B",
    "A/B test variants": "Variantes A/B",
    "Generate two variants of every social messaging output":
        "Genera dos variantes de cada mensaje en redes sociales",
    "Off (single variant per format).": "Apagado (una sola variante por formato).",
    "On: two variants per social format + sample-size math.":
        "Activado: dos variantes por formato más cálculo de tamaño de muestra.",
    "Plan mode": "Modo del plan",
    "Mode": "Modo",
    "Auto": "Auto",
    "Mobilization": "Movilización",
    "Persuasion": "Persuasión",
    "Let Powerbuilder pick the natural mix":
        "Deja que Powerbuilder elija la mezcla natural",
    "GOTV: speak to supporters who already agree":
        "GOTV: habla con quienes ya están de tu lado",
    "Move undecided or soft-opposing voters":
        "Mueve a votantes indecisos o con oposición leve",
    "Auto picks the mix.": "Auto elige la mezcla.",
    "GOTV your supporters.": "GOTV con tu base.",
    "Move undecided voters.": "Mueve a indecisos.",
}

VI = {
    "Theme": "Giao diện",
    "System": "Hệ thống",
    "Light": "Sáng",
    "Dark": "Tối",
    "Follow your device setting": "Theo cài đặt của thiết bị",
    "Always light": "Luôn sáng",
    "Always dark": "Luôn tối",
    "A/B test toggle": "Bật thử nghiệm A/B",
    "A/B test variants": "Phiên bản A/B",
    "Generate two variants of every social messaging output":
        "Tạo hai phiên bản cho mỗi nội dung mạng xã hội",
    "Off (single variant per format).": "Tắt (một phiên bản cho mỗi định dạng).",
    "On: two variants per social format + sample-size math.":
        "Bật: hai phiên bản mỗi định dạng, kèm tính cỡ mẫu.",
    "Plan mode": "Chế độ kế hoạch",
    "Mode": "Chế độ",
    "Auto": "Tự động",
    "Mobilization": "Huy động",
    "Persuasion": "Thuyết phục",
    "Let Powerbuilder pick the natural mix":
        "Để Powerbuilder chọn cách phối hợp tự nhiên",
    "GOTV: speak to supporters who already agree":
        "GOTV: nói chuyện với những người đã ủng hộ",
    "Move undecided or soft-opposing voters":
        "Lay chuyển cử tri lưỡng lự hoặc chỉ phản đối nhẹ",
    "Auto picks the mix.": "Tự động chọn cách phối.",
    "GOTV your supporters.": "GOTV nhóm ủng hộ.",
    "Move undecided voters.": "Lay chuyển cử tri lưỡng lự.",
}


def _escape_po(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _apply(po_path: Path, mapping: dict[str, str]) -> int:
    text = po_path.read_text(encoding="utf-8")
    updated = 0
    for src, tgt in mapping.items():
        # Match: msgid "src"\nmsgstr ""  (only when msgstr is empty so we never
        # overwrite a translator's prior work).
        src_esc = _escape_po(src)
        tgt_esc = _escape_po(tgt)
        pattern = re.compile(
            r'(msgid "' + re.escape(src_esc) + r'"\nmsgstr )""',
            re.MULTILINE,
        )
        new_text, n = pattern.subn(
            lambda m, t=tgt_esc: m.group(1) + '"' + t + '"',
            text,
        )
        if n:
            text = new_text
            updated += n
    po_path.write_text(text, encoding="utf-8")
    return updated


def main() -> None:
    base = Path(__file__).resolve().parent.parent / "locale"
    es_count = _apply(base / "es" / "LC_MESSAGES" / "django.po", ES)
    vi_count = _apply(base / "vi" / "LC_MESSAGES" / "django.po", VI)
    print(f"ES filled: {es_count} entries")
    print(f"VI filled: {vi_count} entries")
    if es_count == 0 and vi_count == 0:
        print(
            "WARNING: nothing was filled — either the msgids are already "
            "translated or makemessages produced different msgid spelling.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
