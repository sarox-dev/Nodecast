"""
Raw Capture storage — failsistēmā, nekad nemodificēts.

Struktūra:
  contents/users/{user_id}/raw/
    {capture_id}/
      capture.json   → CapturePackage (bez HTML)
      page.html      → pilns lapas HTML (ja ir)
"""

import json
import os
from pathlib import Path

from app.core.security import CONTENTS_DIR
from app.models.capture_package import CapturePackage


def _raw_dir(user_id: str, capture_id: str) -> Path:
    return CONTENTS_DIR / "users" / user_id / "raw" / capture_id


def save_raw_capture(
    user_id: str,
    package: CapturePackage,
    html: str | None = None,
) -> Path:
    """
    Saglabā Raw Capture failsistēmā.

    - capture.json — vienmēr, satur visu Package (izņemot HTML)
    - page.html — tikai ja html ir padots

    Ja mape jau eksistē, neko nepārraksta — Raw Capture ir immutable.
    Atgriež ceļu līdz raw direktorijai.
    """
    raw_path = _raw_dir(user_id, package.capture_id)
    if raw_path.exists():
        raise FileExistsError(
            f"Raw Capture {package.capture_id} already exists — "
            "Raw Capture is immutable, cannot overwrite."
        )

    os.makedirs(str(raw_path), exist_ok=True)

    # capture.json
    capture_path = raw_path / "capture.json"
    with open(str(capture_path), "w", encoding="utf-8") as f:
        # Use model_dump with exclude_none to keep JSON clean
        json.dump(
            package.model_dump(exclude_none=True, mode="json"),
            f,
            indent=2,
            ensure_ascii=False,
        )

    # page.html
    if html:
        html_path = raw_path / "page.html"
        html_path.write_text(html, encoding="utf-8")

    return raw_path


def load_raw_capture(user_id: str, capture_id: str) -> CapturePackage | None:
    """Nolasa CapturePackage no failsistēmas. Atgriež None ja nav."""
    capture_path = _raw_dir(user_id, capture_id) / "capture.json"
    if not capture_path.exists():
        return None
    with open(str(capture_path), "r", encoding="utf-8") as f:
        return CapturePackage(**json.load(f))


def get_raw_html(user_id: str, capture_id: str) -> str | None:
    """Nolasa page.html no failsistēmas. Atgriež None ja nav."""
    html_path = _raw_dir(user_id, capture_id) / "page.html"
    if not html_path.exists():
        return None
    return html_path.read_text(encoding="utf-8")


def raw_exists(user_id: str, capture_id: str) -> bool:
    return _raw_dir(user_id, capture_id).exists()


def raw_size(user_id: str, capture_id: str) -> int:
    """Atgriež raw direktorijas izmēru baitos."""
    raw_path = _raw_dir(user_id, capture_id)
    if not raw_path.exists():
        return 0
    total = 0
    for f in raw_path.iterdir():
        if f.is_file():
            total += f.stat().st_size
    return total


def list_raw_captures(user_id: str) -> list[str]:
    """Atgriež visu lietotāja raw capture ID sarakstu (pēc modifikācijas laika, jaunākie pirmie)."""
    raw_root = CONTENTS_DIR / "users" / user_id / "raw"
    if not raw_root.exists():
        return []
    dirs = [d.name for d in raw_root.iterdir() if d.is_dir()]
    # Sort by modification time (newest first)
    dirs.sort(
        key=lambda d: (raw_root / d / "capture.json").stat().st_mtime
        if (raw_root / d / "capture.json").exists()
        else 0,
        reverse=True,
    )
    return dirs