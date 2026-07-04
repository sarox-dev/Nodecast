"""
Extractor — datu transformācijas slānis.

Extractor saņem CapturePackage + HTML un atgriež ExtractorResult
ar vairākiem KnowledgeObjects.

Pipeline:
1. CapturePackage
2. Extractor pipeline (pēc prioritātēm)
3. ExtractorResult (knowledge_objects[])
"""

from abc import ABC, abstractmethod

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult


class BaseExtractor(ABC):
    """Bāzes klase visiem Extractoriem."""

    name: str = "base"
    version: str = "1.0"

    @abstractmethod
    def can_handle(self, package: CapturePackage, html: str | None) -> bool:
        """Vai šis Extractor spēj apstrādāt šo CapturePackage?"""
        ...

    @abstractmethod
    def extract(self, package: CapturePackage, html: str | None) -> ExtractorResult:
        """Apstrādā CapturePackage un atgriež ExtractorResult ar KnowledgeObjects."""
        ...