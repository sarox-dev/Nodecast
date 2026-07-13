"""
Capture Layout — deklaratīva konfigurācija Capture tipiem.

Nosaka:
- Uz kādiem domain/pattern attiecas
- Kādas pogas rādīt extensionā
- Kādu capture_type nosūtīt backendam
- Kādus CSS selektorus izmantot satura fokusēšanai

Dokumentācija: AI_Vault/Nodecast/Architecture/CaptureLayout.md
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CaptureLayoutCapture(BaseModel):
    """Viena capture tipa definīcija Layoutā."""

    type: str = "page"
    """capture_type vērtība (issue, video, thread, conversation, page, ...)"""

    label: str = "Save"
    """Pogas teksts extensionā"""

    icon: str | None = None
    """Ikonas nosaukums (nākotnē, priekš UI)"""

    selector: str | None = None
    """CSS selektors galvenajam satura elementam. 
    Ja norādīts, extension fokusējas uz šo elementu."""

    priority: int = 0
    """Jo augstāks, jo pirmāks pogu sarakstā"""


class CaptureLayout(BaseModel):
    """Viena Layout konfigurācija — attiecas uz vienu vai vairākiem domainiem."""

    name: str
    """Layout unikālais nosaukums (piem., 'github-issue', 'youtube-video')"""

    version: int = 1
    """Layout versija — priekš cache invalidācijas"""

    description: str = ""
    """Cilvēkam lasāms apraksts"""

    domains: list[str] = Field(default_factory=list)
    """Precīzi domain vārdi (piem., ['github.com', 'www.github.com'])"""

    patterns: list[str] = Field(default_factory=list)
    """URL pattern matches (piem., ['github.com/*/issues/*', 'github.com/*/pull/*'])
    Izmanto vienkāršu glob matching (* jebkur, ** visi apakšceļi).
    Ja tukšs, attiecas uz visiem domain URLs."""

    captures: list[CaptureLayoutCapture] = Field(default_factory=list)
    """Pieejamie capture tipi šim domainam"""

    collect_html: bool = True
    """Vai savākt pilnu lapas HTML (var atslēgt ātrumam)"""

    collect_metadata: bool = True
    """Vai vākt OG/Twitter/Schema.org metadatus"""


class LayoutMatchResult(BaseModel):
    """Rezultāts pēc URL pārbaudes — ko extensions saņem."""

    matched: bool
    layout: CaptureLayout | None = None
    capture_types: list[CaptureLayoutCapture] = Field(default_factory=list)
    """Tie capture tipi, kas atbilst šim URL"""


# ─── YAML serializācijas palīgs ──────────────────────────────────

def layout_to_yaml(layout: CaptureLayout) -> str:
    """Pārvērš Layout uz YAML string."""
    import yaml
    return yaml.dump(
        layout.model_dump(exclude_none=True, mode="json"),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def yaml_to_layout(yaml_str: str) -> CaptureLayout:
    """Nolasa Layout no YAML string."""
    import yaml
    data = yaml.safe_load(yaml_str)
    return CaptureLayout(**data)