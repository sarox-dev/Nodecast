"""
Generic HTML Extractor — vispārējs fallback Extractor.

Darbojas uz jebkura HTML. Atgriež:
- metadata — title, description, keywords, author, language, open graph
- article — galvenais saturs (no <article>/<main> vai <body> kā fallback)
- headings[] — visi h1-h6
- links[] — limitēti uz 30, bez navigācijas saitēm
- code_blocks[] — visi <pre><code> bloki
- images[] — visi <img> ar src
- json_ld — Schema.org dati (ja atrasti)

Izmanto html_tools.py JSON-LD un meta tagu atpazīšanai.
"""

import re
from html.parser import HTMLParser

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult, KnowledgeObject
from app.services.extractors import BaseExtractor
from app.services.extractors.html_tools import find_json_ld, find_meta_tags

# Vienmēr izlaistie tagi — tie nesatur lapas saturu
EXCLUDED_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript"}

# Maksimālais linku skaits — lai YouTube nenoslīcinātu
MAX_LINKS = 30


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
        self.body_text_parts: list[str] = []
        self.headings: list[dict] = []
        self.links: list[dict] = []
        self.code_blocks: list[dict] = []
        self.images: list[dict] = []

        # Stāvokļi
        self._in_body = False
        self._in_title = False
        self._skip_depth = 0
        self._text_buffer = ""
        self._collect_text = False
        self._heading_level = 0
        self._in_heading = False
        self._in_a = False
        self._in_pre = False
        self._in_code = False
        self._current_attrs: dict = {}
        self._code_language = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        ad = dict(attrs)

        if tag in EXCLUDED_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        if tag == "body":
            self._in_body = True
            return
        if tag == "title":
            self._in_title = True
            self._text_buffer = ""
            return
        if tag in ("pre",):
            self._in_pre = True
            self._code_language = self._detect_code_language(ad.get("class", "") or "")
            self._text_buffer = ""
            return
        if tag == "code" and self._in_pre:
            self._in_code = True
            return
        if tag == "a" and ad.get("href"):
            self._in_a = True
            self._current_attrs = ad
            self._text_buffer = ""
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_level = int(tag[1])
            self._in_heading = True
            self._text_buffer = ""
            return
        if tag == "img" and ad.get("src"):
            from urllib.parse import urljoin
            src = ad.get("src", "") or ""
            if not src.startswith(("http://", "https://", "data:")):
                src = urljoin(self.base_url, src)
            self.images.append({
                "src": src,
                "alt": ad.get("alt", "") or "",
                "width": ad.get("width"),
                "height": ad.get("height"),
            })
            return
        if tag == "meta":
            name = (ad.get("name", ad.get("property", "")) or "").lower()
            content = ad.get("content", "") or ""
            if name == "description":
                self.description = content
            elif name == "keywords":
                self.keywords = [k.strip() for k in content.split(",") if k.strip()]
            elif name == "author":
                self.author = content
            return

        if self._in_body and tag in ("p", "li", "div", "section", "span", "blockquote",
                                      "td", "th", "dt", "dd", "label", "figcaption", "article",
                                      "main"):
            self._collect_text = True
            return

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in EXCLUDED_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if self._skip_depth > 0:
            return

        if tag == "body":
            self._in_body = False
            if self._text_buffer.strip():
                self.body_text_parts.append(self._text_buffer.strip())
            self._text_buffer = ""
            self._collect_text = False
            return

        if tag == "title" and self._in_title:
            self.title = self._text_buffer.strip()
            self._in_title = False
            self._text_buffer = ""
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._in_heading:
            text = self._text_buffer.strip()
            if text:
                self.headings.append({"level": self._heading_level, "text": text})
            self._in_heading = False
            self._text_buffer = ""
            return

        if tag == "a" and self._in_a:
            href = self._current_attrs.get("href", "")
            if not href.startswith(("http://", "https://", "mailto:", "#")):
                from urllib.parse import urljoin
                href = urljoin(self.base_url, href)
            text = self._text_buffer.strip()
            if href and text and len(self.links) < MAX_LINKS:
                if not any(x in href for x in ("googleadservices", "doubleclick", "facebook.com/tr")):
                    self.links.append({
                        "href": href,
                        "text": text[:200],
                        "rel": self._current_attrs.get("rel", ""),
                    })
            self._in_a = False
            self._text_buffer = ""
            return

        if tag == "pre":
            code = self._text_buffer.strip()
            if code:
                self.code_blocks.append({"language": self._code_language, "code": code})
            self._in_pre = False
            self._in_code = False
            self._text_buffer = ""
            return
        if tag == "code":
            self._in_code = False

        if self._collect_text and tag in ("p", "li", "div", "section", "span", "blockquote",
                                           "td", "th", "dt", "dd", "label", "figcaption",
                                           "article", "main"):
            text = self._text_buffer.strip()
            if text:
                self.body_text_parts.append(text)
            self._text_buffer = ""
            self._collect_text = False

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_title or self._in_heading or self._in_a or self._in_pre or self._in_code:
            self._text_buffer += data
        elif self._collect_text:
            self._text_buffer += data

    def get_body_text(self) -> str:
        """Atgriež visu savākto body tekstu, apvienotu."""
        text = " ".join(self.body_text_parts)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _detect_code_language(self, class_str: str) -> str:
        match = re.search(r'(?:language-|lang-)(\w+)', class_str)
        if match:
            return match.group(1)
        if class_str:
            return class_str.split()[-1]
        return ""


class GenericHtmlExtractor(BaseExtractor):
    """Vispārējs HTML Extractor — darbojas uz jebkura HTML satura."""

    name = "generic-html"
    version = "2.0"

    def can_handle(self, package: CapturePackage, html: str | None) -> bool:
        return html is not None and len(html) > 0

    def extract(self, package: CapturePackage, html: str | None) -> ExtractorResult:
        if not html:
            return ExtractorResult(warnings=["No HTML provided"])

        base_url = package.source.url or ""
        parser = _GenericHtmlParser(base_url=base_url)
        parser.feed(html)

        # Papildus dati no html_tools
        meta_tags = find_meta_tags(html)
        json_ld_objects = find_json_ld(html)

        objects: list[KnowledgeObject] = []
        pos = 0

        # 1. Metadata — bagātināta ar html_tools meta tagiem
        meta_props = self._build_meta_props(parser, meta_tags, package)
        if any(meta_props.values()):
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="metadata",
                properties={k: v for k, v in meta_props.items() if v},
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 2. JSON-LD — Schema.org dati
        for ld_obj in json_ld_objects:
            ld_type = ld_obj.get("@type", "Thing")
            ld_props = self._build_ld_props(ld_obj)
            if ld_props:
                objects.append(KnowledgeObject(
                    capture_id=package.capture_id,
                    type="json_ld",
                    properties={
                        "schema_type": ld_type,
                        "data": ld_props,
                    },
                    confidence=0.95,
                    extracted_by=self.name,
                    position=pos,
                ))
                pos += 1

        # 3. Article / main content
        body_text = parser.get_body_text()
        if body_text and len(body_text) > 30:
            # Mēģinam atrast article specifiskāku info no JSON-LD
            article_title = self._find_article_title(json_ld_objects) or parser.title or package.source.title or ""
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="article",
                properties={
                    "title": article_title,
                    "text": body_text[:15000],
                    "word_count": len(body_text.split()),
                },
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 4. Headings
        for h in parser.headings:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="heading",
                properties=h,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 5. Links
        for link in parser.links:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="link",
                properties=link,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 6. Code blocks
        for cb in parser.code_blocks:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="code_block",
                properties=cb,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 7. Images
        for img in parser.images:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="image",
                properties=img,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

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

    def _build_meta_props(self, parser: _GenericHtmlParser, meta_tags: dict, package: CapturePackage) -> dict:
        """Veido metadata properties, apvienojot no parser un html_tools."""
        # Parser meta dati
        props = {
            "title": parser.title or package.source.title or meta_tags.get("og:title", ""),
            "description": parser.description or meta_tags.get("og:description", ""),
            "keywords": parser.keywords or [],
            "author": parser.author or meta_tags.get("author", ""),
            "language": parser.language or (package.page_metadata.language if package.page_metadata else ""),
        }

        # Open Graph dati (ja nav jau parserī)
        for og_key in ("og:type", "og:url", "og:site_name", "og:image", "og:locale"):
            if og_key in meta_tags and og_key not in props:
                props[og_key.replace(":", "_")] = meta_tags[og_key]

        # Twitter card
        for tw_key in ("twitter:card", "twitter:site", "twitter:creator", "twitter:image"):
            if tw_key in meta_tags:
                props[tw_key.replace(":", "_")] = meta_tags[tw_key]

        return props

    def _build_ld_props(self, ld_obj: dict) -> dict:
        """Veido plakanu dict no JSON-LD objekta (bez dziļas nesting)."""
        props = {}
        interesting_keys = [
            "name", "headline", "description", "author", "datePublished",
            "dateModified", "publisher", "image", "url", "mainEntityOfPage",
        ]
        for key in interesting_keys:
            if key in ld_obj:
                val = ld_obj[key]
                if isinstance(val, dict):
                    # Author/Publisher objekts
                    if "name" in val:
                        props[key] = val["name"]
                    elif "@id" in val:
                        props[key] = val["@id"]
                elif isinstance(val, list):
                    if val and isinstance(val[0], dict) and "name" in val[0]:
                        props[key] = [v.get("name", "") for v in val if isinstance(v, dict)]
                    else:
                        props[key] = val
                else:
                    props[key] = val
        return props

    def _find_article_title(self, json_ld_objects: list[dict]) -> str | None:
        """Mēģina atrast article title no JSON-LD."""
        for ld in json_ld_objects:
            if isinstance(ld, dict):
                ld_type = ld.get("@type", "")
                if ld_type in ("Article", "NewsArticle", "BlogPosting", "WebPage"):
                    return ld.get("headline") or ld.get("name") or None
        return None