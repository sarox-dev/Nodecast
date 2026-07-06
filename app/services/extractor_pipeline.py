"""
Extractor Pipeline — palaiž Extractorus pēc prioritātēm.

Pipeline:
1. Specializētie Python extractori (YouTube, GitHub, Reddit...)
2. Config-driven Engine — ja ir YAML konfigs konkrētai vietnei
3. Generic HTML Extractor — fallback, vienmēr pēdējais

Python extractori ir prioritāri, jo tie ir rūpīgāk izstrādāti
un apstrādā edge case'us. Config engine ir domāts jaunām vietnēm,
kurām vēl nav Python extractora.
"""

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult
from app.services.extractors import BaseExtractor
from app.services.extractors.generic_html import GenericHtmlExtractor
from app.services.extractors.engine import ConfigEngine


# Reģistrēti Python extractori — izpildās pirms config engine
_PYTHON_EXTRACTORS: list[BaseExtractor] = []

# Config Engine — izpildās starp Python un GenericHtml
_config_engine = ConfigEngine()

# Generic HTML — vienmēr pēdējais fallback
_generic_html = GenericHtmlExtractor()


def register_extractor(extractor: BaseExtractor):
    """Pievieno Python extractoru pipeline (prioritāri, pirms config engine)."""
    _PYTHON_EXTRACTORS.append(extractor)


def get_registered_extractors() -> list[BaseExtractor]:
    """Atgriež visus reģistrētos extractorus (debug)."""
    return _PYTHON_EXTRACTORS.copy()


def run_pipeline(package: CapturePackage, html: str | None) -> ExtractorResult:
    """
    Palaiž extractor pipeline.

    Secība:
    1. Python extractori (specializēti, prioritāri)
    2. Config Engine (ja ir atbilstoša konfigurācija)
    3. GenericHtmlExtractor (fallback)
    """
    if not html:
        return ExtractorResult(
            warnings=["No HTML available for extraction"],
        )

    # Nodrošinām ka Python extractori ir reģistrēti
    from app.services.extractors import ensure_extractors_registered
    ensure_extractors_registered()

    # 1. Python extractori — specializēti, rūpīgi testēti
    for extractor in _PYTHON_EXTRACTORS:
        if extractor.can_handle(package, html):
            result = extractor.extract(package, html)
            if result.knowledge_objects:
                return result

    # 2. Config Engine — mēģina atrast YAML konfigurāciju
    config_result = _config_engine.extract(package, html)
    if config_result and config_result.knowledge_objects:
        return config_result

    # 3. Generic HTML — vienmēr strādā, ja ir HTML
    return _generic_html.extract(package, html)


def extract_and_save(user_id: str, package: CapturePackage, html: str | None) -> ExtractorResult:
    """
    Palaiž pipeline un saglabā rezultātus datubāzē.
    """
    from app.services.knowledge_store import save_knowledge_objects

    result = run_pipeline(package, html)
    if result.knowledge_objects:
        saved = save_knowledge_objects(user_id, result)
        result.knowledge_objects = result.knowledge_objects[:saved]
    return result