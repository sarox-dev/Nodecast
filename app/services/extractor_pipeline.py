"""
Extractor Pipeline — palaiž Extractorus pēc prioritātēm.

1. Exact Domain Extractor (piem., GitHub)
2. Article Extractor (ja ir <article> vai Schema Article)
3. Generic HTML Extractor (fallback — vienmēr)
"""

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult
from app.services.extractors import BaseExtractor
from app.services.extractors.generic_html import GenericHtmlExtractor


# Reģistrēti Extractori prioritārā secībā
_EXTRACTORS: list[BaseExtractor] = [
    # Nākotnē: GitHubExtractor(), ArticleExtractor()
    GenericHtmlExtractor(),  # Fallback — vienmēr pēdējais
]


def register_extractor(extractor: BaseExtractor):
    """Pievieno jaunu Extractor pipeline (pirms GenericHtml)."""
    _EXTRACTORS.insert(len(_EXTRACTORS) - 1, extractor)


def run_pipeline(package: CapturePackage, html: str | None) -> ExtractorResult:
    """
    Palaiž visus Extractorus, kas spēj apstrādāt šo CapturePackage.

    Atgriež pirmā Extractor rezultātu, vai GenericHtml fallback.
    """
    if not html:
        return ExtractorResult(
            warnings=["No HTML available for extraction"],
        )

    for extractor in _EXTRACTORS:
        if extractor.can_handle(package, html):
            result = extractor.extract(package, html)
            if result.knowledge_objects:
                return result
            # Ja nav objektu, turpina uz nākamo Extractor

    return ExtractorResult(
        warnings=["No extractor produced knowledge objects"],
    )


def extract_and_save(user_id: str, package: CapturePackage, html: str | None) -> ExtractorResult:
    """Palaiž pipeline un saglabā rezultātus."""
    from app.services.knowledge_store import save_knowledge_objects

    result = run_pipeline(package, html)
    if result.knowledge_objects:
        saved = save_knowledge_objects(user_id, result)
        result.knowledge_objects = result.knowledge_objects[:saved]  # Keep only saved
    return result