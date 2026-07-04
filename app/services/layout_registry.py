"""
Layout Registry — ielādē, kešo, un atrod Capture Layouts pēc URL.

Layout faili glabājas: contents/layouts/*.yaml
"""

import fnmatch
import os
from pathlib import Path
from urllib.parse import urlparse

from app.core.security import CONTENTS_DIR
from app.models.capture_layout import CaptureLayout, LayoutMatchResult, yaml_to_layout


LAYOUTS_DIR = CONTENTS_DIR / "layouts"


def _ensure_layouts_dir():
    """Izveido layouts direktoriju, ja neeksistē."""
    os.makedirs(str(LAYOUTS_DIR), exist_ok=True)


def _load_all_layouts() -> list[CaptureLayout]:
    """Ielādē visus YAML layout failus no contents/layouts/."""
    _ensure_layouts_dir()
    layouts = []
    for fpath in sorted(LAYOUTS_DIR.glob("*.yaml")):
        try:
            yaml_str = fpath.read_text(encoding="utf-8")
            layout = yaml_to_layout(yaml_str)
            layouts.append(layout)
        except Exception as e:
            print(f"Warning: Failed to load layout {fpath.name}: {e}")
    return layouts


def list_layouts() -> list[dict]:
    """Atgriež visu layoutu sarakstu (bez pilniem datiem — tikai metadatus)."""
    layouts = _load_all_layouts()
    return [
        {
            "name": l.name,
            "version": l.version,
            "description": l.description,
            "domains": l.domains,
            "patterns": l.patterns,
            "capture_types": [c.type for c in l.captures],
        }
        for l in layouts
    ]


def _normalize_domain(d: str) -> str:
    """Normalizē domain — noņem www. priekšā."""
    return d.lower().removeprefix("www.")


def get_layout_for_url(url: str) -> LayoutMatchResult:
    """
    Atrod piemērotāko Layout konkrētam URL.

    Matching order:
    1. Domain match + pattern match (visprecīzākais)
    2. Domain match (ja layout nav patternu, der jebkurš URL uz šī domain)
    3. Default layout (ja ir)
    """
    if not url:
        return LayoutMatchResult(matched=False)

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        norm_domain = _normalize_domain(domain)
        path = parsed.path.rstrip("/") or "/"
    except Exception:
        return LayoutMatchResult(matched=False)

    layouts = _load_all_layouts()
    if not layouts:
        return LayoutMatchResult(matched=False)

    # 1. Domain match + pattern match
    for layout in layouts:
        # Check if any domain matches (normalized)
        domain_match = False
        for d in layout.domains:
            if _normalize_domain(d) == norm_domain:
                domain_match = True
                break

        if not domain_match:
            continue

        # Ja nav patternu — domain match der
        if not layout.patterns:
            return LayoutMatchResult(
                matched=True,
                layout=layout,
                capture_types=layout.captures,
            )

        # Pārbaudam patternus
        # Patterns var būt ar domain (piem., "github.com/*/issues/*") vai bez
        for pattern in layout.patterns:
            p = pattern.lower()

            # If pattern contains a domain, extract and normalize it
            pattern_domain = ""
            pattern_path = p
            if "//" in p:
                # Full URL pattern like "https://github.com/*"
                # Not expected in our format, but handle gracefully
                continue
            if "/" in p:
                # Could be "domain/path" or just "/path"
                parts = p.split("/", 1)
                candidate_domain = parts[0]
                if "." in candidate_domain or candidate_domain == "localhost":
                    pattern_domain = _normalize_domain(candidate_domain)
                    pattern_path = "/" + parts[1] if len(parts) > 1 else "/"

            # Check domain match for this pattern
            if pattern_domain and pattern_domain != norm_domain:
                continue

            # Check path match
            # For patterns like "youtube.com/watch*", pattern_path = "/watch*"
            # For patterns like "github.com/*/issues/*", pattern_path = "/*/issues/*"
            match_path = pattern_path
            if fnmatch.fnmatch(path, match_path):
                return LayoutMatchResult(
                    matched=True,
                    layout=layout,
                    capture_types=layout.captures,
                )

    # 2. Default layout (ja ir) — fallback for any URL
    for layout in layouts:
        if layout.name == "default":
            return LayoutMatchResult(
                matched=True,
                layout=layout,
                capture_types=layout.captures,
            )

    return LayoutMatchResult(matched=False)


def get_layout_by_name(name: str) -> CaptureLayout | None:
    """Atrod layout pēc nosaukuma."""
    for layout in _load_all_layouts():
        if layout.name == name:
            return layout
    return None


def save_layout(layout: CaptureLayout) -> Path:
    """Saglabā layout kā YAML failu. Pārraksta ja eksistē."""
    from app.models.capture_layout import layout_to_yaml

    _ensure_layouts_dir()
    fpath = LAYOUTS_DIR / f"{layout.name}.yaml"
    yaml_str = layout_to_yaml(layout)
    fpath.write_text(yaml_str, encoding="utf-8")
    return fpath


def delete_layout(name: str) -> bool:
    """Dzēš layout failu. Atgriež True ja izdevās."""
    fpath = LAYOUTS_DIR / f"{name}.yaml"
    if fpath.exists():
        fpath.unlink()
        return True
    return False