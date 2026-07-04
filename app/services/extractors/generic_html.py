"""
Generic HTML Extractor — vispārējs fallback Extractor.

Darbojas uz jebkura HTML. Atgriež:
- metadata — title, description, keywords, author, language
- article — galvenais saturs (no <article> vai <main> vai <body>)
- headings[] — visi h1-h6
- links[] — visi <a> ar href
- code_blocks[] — visi <pre><code> bloki
- images[] — visi <img> ar src
"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult, KnowledgeObject
from app.services.extractors import BaseExtractor


class _GenericHtmlParser(HTMLParser):
    """HTML parseris, kas savāc strukturētus datus no jebkura HTML."""

    def __init__(self, base_url: str = ""):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url

        # Rezultāti
        self.title = ""
        self.description = ""
        self.keywords: list[str] = []
        self.author = ""
        self.language = ""
        self.canonical = ""

        self.article_texts: list[str] = []
        self.headings: list[dict] = []
        self.links: list[dict] = []
        self.code_blocks: list[dict] = []
        self.images: list[dict] = []

        # Stāvokļi
        self._in_head = False
        self._in_title = False
        self._in_article = False
        self._in_main = False
        self._in_pre = False
        self._in_code = False
        self._in_a = False
        self._current_tag = ""
        self._current_attrs: dict = {}
        self._text_buffer = ""
        self._heading_level = 0
        self._skip_nested = 0
        self._in_heading = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        ad = dict(attrs)

        if tag == "html":
            self.language = ad.get("lang", "")
        if tag == "head":
            self._in_head = True
        if tag == "title":
            self._in_title = True
            self._text_buffer = ""
        if tag in ("article",):
            self._in_article = True
            self._text_buffer = ""
        if tag in ("main",):
            self._in_main = True
        if tag == "pre":
            self._in_pre = True
            self._code_language = self._detect_code_language(ad.get("class", "") or "")
            self._text_buffer = ""
        if tag == "code" and self._in_pre:
            self._in_code = True
        if tag == "a" and ad.get("href"):
            self._in_a = True
            self._current_attrs = ad
            self._text_buffer = ""
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_level = int(tag[1])
            self._in_heading = True
            self._text_buffer = ""
        if tag == "img" and ad.get("src"):
            src = ad.get("src", "") or ""
            if not src.startswith(("http://", "https://", "data:")):
                src = urljoin(self.base_url, src)
            self.images.append({
                "src": src,
                "alt": ad.get("alt", "") or "",
                "width": ad.get("width"),
                "height": ad.get("height"),
            })
        if tag == "meta":
            name = (ad.get("name", ad.get("property", "")) or "").lower()
            content = ad.get("content", "") or ""
            if name == "description":
                self.description = content
            elif name == "keywords":
                self.keywords = [k.strip() for k in content.split(",") if k.strip()]
            elif name == "author":
                self.author = content

        # Skip deeply nested non-semantic content
        if tag in ("script", "style", "nav", "header", "footer", "aside"):
            self._skip_nested += 1

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in ("script", "style", "nav", "header", "footer", "aside"):
            if self._skip_nested > 0:
                self._skip_nested -= 1
            return

        if tag == "title" and self._in_title:
            self.title = self._text_buffer.strip()
            self._in_title = False
        if tag == "head":
            self._in_head = False
        if tag == "article":
            self._in_article = False
        if tag == "main":
            self._in_main = False
        if tag == "pre":
            if self._text_buffer.strip():
                self.code_blocks.append({
                    "language": getattr(self, "_code_language", ""),
                    "code": self._text_buffer.strip(),
                })
            self._in_pre = False
            self._in_code = False
            self._text_buffer = ""
        if tag == "code" and self._in_code:
            self._in_code = False
        if tag == "a" and self._in_a:
            href = self._current_attrs.get("href", "")
            if not href.startswith(("http://", "https://", "mailto:", "#")):
                href = urljoin(self.base_url, href)
            text = self._text_buffer.strip()
            if href and text:
                self.links.append({
                    "href": href,
                    "text": text[:200],
                    "rel": self._current_attrs.get("rel", ""),
                })
            self._in_a = False
            self._text_buffer = ""
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._in_heading:
            text = self._text_buffer.strip()
            if text:
                self.headings.append({
                    "level": self._heading_level,
                    "text": text,
                })
            self._in_heading = False
            self._text_buffer = ""

    def handle_data(self, data):
        if self._skip_nested > 0:
            return
        if self._in_title or self._in_heading or self._in_a or self._in_pre or self._in_code:
            self._text_buffer += data
        elif self._in_article or self._in_main:
            self._text_buffer += data

    def _detect_code_language(self, class_str: str) -> str:
        """Mēģina noteikt programmēšanas valodu no klases nosaukuma."""
        match = re.search(r'(?:language-|lang-)(\w+)', class_str)
        if match:
            return match.group(1)
        if class_str:
            return class_str.split()[-1]
        return ""


class GenericHtmlExtractor(BaseExtractor):
    """Vispārējs HTML Extractor — darbojas uz jebkura HTML satura."""

    name = "generic-html"
    version = "1.0"

    def can_handle(self, package: CapturePackage, html: str | None) -> bool:
        """Vienmēr var apstrādāt — šis ir fallback."""
        return html is not None and len(html) > 0

    def extract(self, package: CapturePackage, html: str | None) -> ExtractorResult:
        if not html:
            return ExtractorResult(
                warnings=["No HTML provided to GenericHtmlExtractor"],
            )

        base_url = package.source.url or ""
        parser = _GenericHtmlParser(base_url=base_url)
        parser.feed(html)

        objects: list[KnowledgeObject] = []
        pos = 0

        # 1. Metadata
        meta_props = {
            "title": parser.title or package.source.title or "",
            "description": parser.description,
            "keywords": parser.keywords,
            "author": parser.author,
            "language": parser.language or package.page_metadata.language if package.page_metadata else "",
        }
        if any(meta_props.values()):
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="metadata",
                properties={k: v for k, v in meta_props.items() if v},
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 2. Article (main content)
        article_text = parser._text_buffer.strip() if (parser._in_article or parser._in_main) else ""
        if not article_text and parser.article_texts:
            article_text = " ".join(parser.article_texts)
        if article_text and len(article_text) > 20:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="article",
                properties={
                    "title": parser.title or package.source.title or "",
                    "text": article_text[:10000],
                    "word_count": len(article_text.split()),
                },
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 3. Headings
        for h in parser.headings:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="heading",
                properties=h,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 4. Links
        for link in parser.links:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="link",
                properties=link,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 5. Code blocks
        for cb in parser.code_blocks:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="code_block",
                properties=cb,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 6. Images
        for img in parser.images:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="image",
                properties=img,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # Confidence: high for deterministic HTML parsing
        confidence = 0.95 if objects else 0.5
        warnings = []
        if not objects:
            warnings.append("No knowledge objects extracted from HTML")

        return ExtractorResult(
            knowledge_objects=objects,
            confidence=confidence,
            extractor_version=self.version,
            warnings=warnings,
        )