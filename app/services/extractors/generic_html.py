"""
Generic HTML Extractor — DOM-secīgs content block ekstraktors.

Stratēģija:
1. Atrod galveno satura konteineru: <article> → <main> → <div[role=main]> → <body>
2. Rekursīvi iziet cauri DOM dokumenta secībā
3. Katram nozīmīgam elementam izveido strukturētu bloku ar position
4. Visi bloki tiek ievietoti vienā "document" tipa KnowledgeObject

Rezultāts ir lineāra bloku virkne tieši tādā secībā, kādu redz lietotājs.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult, KnowledgeObject
from app.services.extractors import BaseExtractor
from app.services.extractors.html_tools import find_json_ld, find_meta_tags

# Elementi, kas pilnībā jāizlaiž
EXCLUDED_TAGS = {
    "script", "style", "nav", "header", "footer", "aside", "noscript",
    "button", "select", "option", "form", "label", "input", "textarea",
    "svg", "path", "canvas", "iframe", "embed", "object", "link", "meta",
}

# Nozīmīgie elementi — katram veidojam bloku
BLOCK_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "img", "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
    "ul", "ol", "li", "figure", "figcaption",
    "hr", "video",
}

# Saturu nesošie elementi — tos izlaižam un ejam iekšā
CONTAINER_TAGS = {
    "div", "section", "span", "main", "article",
    "header", "footer", "nav",  # excluded, bet ja nu tie ir satura konteinerā
}


class _BlockBuilder:
    """
    DOM secīgs bloku būvētājs.

    Lieto HTMLParser ar stack struktūru, lai izsekotu elementu hierarhiju
    un veidotu blokus dokumenta secībā.
    """

    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self.blocks: list[dict] = []
        self.stack: list[dict] = []  # [(tag, attrs), ...]

        # Galvenā satura konteinera izsekošana
        self.in_main = False
        self.main_depth = 0
        self.body_depth = 0

        # Skip tracking
        self.skip_depth = 0

        # Teksta buferis iekš pašreizējā bloka
        self.text_buffer = ""

        # Vai pašlaik vācam tekstu blokam
        self.collecting = False

        # Metadati
        self.meta_tags: dict[str, str] = {}
        self.page_title = ""
        self.json_ld_objects: list[dict] = []

    def feed(self, html: str):
        """Sāk HTML parsēšanu."""
        # Vispirms izvelkam metadatus
        self.meta_tags = find_meta_tags(html)
        self.json_ld_objects = find_json_ld(html)
        # Page title
        title_match = re.search(r'<title>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        if title_match:
            self.page_title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

        # Galvenā konteinera noteikšana
        main_html = self._find_main_content(html)
        if not main_html:
            return

        # Parsējam tikai galveno saturu
        parser = _ContentWalker(self)
        parser.feed(main_html)

    def _find_main_content(self, html: str) -> str | None:
        """
        Atrod galveno satura konteineru HTML.

        Prioritāte: <article> → <main> → <div[role=main]> → <body>
        Atgriež tikai konteinera iekšējo HTML (nevis visu lapu).
        """
        # 1. Mēģinam <article>
        m = re.search(
            r'<article[^>]*>(.*?)</article>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if m and len(m.group(1)) > 100:
            # Atrodam article ar nozīmīgu saturu
            return self._extract_inner(m.group(0))

        # 2. Mēģinam <main>
        m = re.search(
            r'<main[^>]*>(.*?)</main>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if m and len(m.group(1)) > 50:
            return m.group(0)

        # 3. Mēģinam <div role="main">
        m = re.search(
            r'<div[^>]*\brole\s*=\s*["\']?main["\']?[^>]*>(.*?)</div>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if m and len(m.group(1)) > 50:
            return m.group(0)

        # 4. Mēģinam <body>
        m = re.search(
            r'<body[^>]*>(.*?)</body>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if m and len(m.group(1)) > 20:
            return m.group(0)

        # 5. Vienkārši atgriežam visu HTML ja nekas cits neder
        if len(html) > 50:
            return html

        return None

    def _extract_inner(self, element_html: str) -> str:
        """Izvelk elementa iekšējo HTML, noņemot ārējo tagu."""
        m = re.match(r'<[^>]+>(.*)</[^>]+>', element_html, re.DOTALL)
        if m:
            return m.group(1)
        return element_html

    def get_result(self) -> tuple[list[dict], dict]:
        """
        Atgriež (blocks, metadata).
        metadata satur: title, description, keywords, author, language
        """
        meta = {
            "title": self.meta_tags.get("og:title", self.page_title),
            "description": self.meta_tags.get("og:description", self.meta_tags.get("description", "")),
            "keywords": self.meta_tags.get("keywords", "").split(",") if self.meta_tags.get("keywords") else [],
            "author": self.meta_tags.get("author", ""),
            "language": self.meta_tags.get("language", ""),
        }
        if not meta["author"]:
            for k in ("og:video:tag", "twitter:creator", "article:author"):
                if k in self.meta_tags:
                    meta["author"] = self.meta_tags[k]
                    break
        return self.blocks, meta


class _ContentWalker(HTMLParser):
    """
    HTMLParser, kas iziet cauri DOM dokumenta secībā
    un veido blokus no nozīmīgiem elementiem.
    """

    def __init__(self, builder: _BlockBuilder):
        super().__init__(convert_charrefs=True)
        self.builder = builder
        self.stack: list[str] = []  # tag stack
        self.skip_depth = 0
        self.text_buffer = ""
        self.current_block: dict | None = None
        self.position = 0

        # List tracking
        self.in_list = False
        self.list_type = ""
        self.list_depth = 0

        # Table tracking
        self.in_table = False
        self.table_data: list[list[str]] = []
        self.current_row: list[str] = []
        self.current_cell = ""

        # Code tracking
        self.in_pre = False
        self.in_code = False
        self.code_language = ""

        # Heading tracking
        self.in_heading = False
        self.heading_level = 0

        # Figure tracking
        self.in_figure = False
        self.figure_img = None
        self.figure_caption = ""

        # Para
        self.in_p = False
        self.in_blockquote = False
        self.blockquote_text = ""
        self.in_li = False
        self.in_figcaption = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        ad = dict(attrs)

        # Skip excluded
        if tag in EXCLUDED_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth > 0:
            return

        self.stack.append(tag)

        if tag in BLOCK_TAGS:
            self._start_block(tag, ad)
        elif tag in ("div", "section", "span", "main", "article"):
            # Container — vienkārši ejam iekšā
            pass

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in EXCLUDED_TAGS:
            if self.skip_depth > 0:
                self.skip_depth -= 1
            return

        if self.skip_depth > 0:
            return

        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

        if tag in BLOCK_TAGS:
            self._end_block(tag)

    def handle_data(self, data):
        if self.skip_depth > 0:
            return

        if self.in_pre or self.in_code:
            self.text_buffer += data
            return

        if self.in_heading or self.in_p or self.in_li or self.in_blockquote or self.in_figcaption:
            self.text_buffer += data

    def _start_block(self, tag: str, attrs: dict):
        """Sāk jaunu bloku."""
        self.text_buffer = ""

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.in_heading = True
            self.heading_level = int(tag[1])

        elif tag == "p":
            self.in_p = True

        elif tag == "img":
            src = attrs.get("src", "")
            if not src.startswith(("http://", "https://", "data:")):
                src = urljoin(self.builder.base_url, src)
            self._emit_block({
                "type": "image",
                "src": src,
                "alt": attrs.get("alt", ""),
                "width": attrs.get("width"),
                "height": attrs.get("height"),
            })

        elif tag == "blockquote":
            self.in_blockquote = True
            self.blockquote_text = ""

        elif tag == "pre":
            self.in_pre = True
            self.code_language = self._detect_language(attrs.get("class", ""))

        elif tag == "code" and not self.in_pre:
            self.in_code = True

        elif tag == "hr":
            self._emit_block({"type": "hr"})

        elif tag == "ul":
            self.in_list = True
            self.list_type = "ul"
            self.list_depth += 1

        elif tag == "ol":
            self.in_list = True
            self.list_type = "ol"
            self.list_depth += 1

        elif tag == "li":
            self.in_li = True

        elif tag == "table":
            self.in_table = True
            self.table_data = []
            self.current_row = []
            self.current_cell = ""

        elif tag == "tr":
            self.current_row = []

        elif tag in ("th", "td"):
            self.text_buffer = ""

        elif tag == "figure":
            self.in_figure = True
            self.figure_img = None
            self.figure_caption = ""

        elif tag == "figcaption":
            self.in_figcaption = True

        elif tag == "video":
            src = attrs.get("src", "")
            poster = attrs.get("poster", "")
            self._emit_block({
                "type": "video",
                "src": src,
                "poster": poster,
            })

    def _end_block(self, tag: str):
        """Beidz pašreizējo bloku."""

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.in_heading:
            text = self._clean_text(self.text_buffer)
            if text:
                self._emit_block({
                    "type": "heading",
                    "content": text,
                    "level": self.heading_level,
                })
            self.in_heading = False

        elif tag == "p" and self.in_p:
            text = self._clean_text(self.text_buffer)
            if text:
                self._emit_block({"type": "paragraph", "content": text})
            self.in_p = False

        elif tag == "blockquote" and self.in_blockquote:
            text = self._clean_text(self.blockquote_text or self.text_buffer)
            if text:
                self._emit_block({"type": "blockquote", "content": text})
            self.in_blockquote = False

        elif tag == "pre":
            code = self._clean_text(self.text_buffer)
            if code:
                self._emit_block({
                    "type": "code",
                    "content": code,
                    "language": self.code_language,
                })
            self.in_pre = False
            self.in_code = False
            self.text_buffer = ""

        elif tag == "code" and self.in_code and not self.in_pre:
            code = self._clean_text(self.text_buffer)
            if code:
                self._emit_block({"type": "code", "content": code, "language": ""})
            self.in_code = False

        elif tag == "li" and self.in_li:
            text = self._clean_text(self.text_buffer)
            if text:
                self._emit_block({
                    "type": "list_item",
                    "content": text,
                    "list_type": self.list_type,
                    "depth": self.list_depth - 1,
                })
            self.in_li = False

        elif tag == "ul":
            self.list_depth -= 1
            if self.list_depth <= 0:
                self.in_list = False

        elif tag == "ol":
            self.list_depth -= 1
            if self.list_depth <= 0:
                self.in_list = False

        elif tag in ("th", "td"):
            cell_text = self._clean_text(self.text_buffer)
            self.current_row.append(cell_text)

        elif tag == "tr":
            if self.current_row:
                self.table_data.append(list(self.current_row))
            self.current_row = []

        elif tag == "table":
            if self.table_data:
                self._emit_block({
                    "type": "table",
                    "rows": self.table_data,
                })
            self.in_table = False

        elif tag == "figure":
            if self.figure_img:
                block = dict(self.figure_img)
                if self.figure_caption:
                    block["caption"] = self.figure_caption
                self._emit_block(block)
            self.in_figure = False

        elif tag == "figcaption":
            self.figure_caption = self._clean_text(self.text_buffer)
            self.in_figcaption = False

    def _emit_block(self, block: dict):
        """Pievieno bloku ar pozīciju."""
        block["position"] = self.position
        self.position += 1
        self.builder.blocks.append(block)

    def _clean_text(self, text: str) -> str:
        """Notīra tekstu no liekiem baltumiem."""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _detect_language(self, class_str: str) -> str:
        """Detektē valodu no klases nosaukuma (piem., 'language-python')."""
        match = re.search(r'(?:language-|lang-)(\w+)', class_str)
        if match:
            return match.group(1)
        if class_str:
            return class_str.split()[-1]
        return ""


class GenericHtmlExtractor(BaseExtractor):
    """
    Generic HTML Extractor — DOM-secīgs content block ekstraktors.

    Atrod galveno satura konteineru, iziet cauri DOM secībā,
    un izveido "document" tipa KnowledgeObject ar lineāru bloku sarakstu.
    """

    name = "generic-html"
    version = "3.0"

    def can_handle(self, package: CapturePackage, html: str | None) -> bool:
        return html is not None and len(html) > 30

    def extract(self, package: CapturePackage, html: str | None) -> ExtractorResult:
        if not html:
            return ExtractorResult(warnings=["No HTML provided"])

        base_url = package.source.url or ""
        builder = _BlockBuilder(base_url=base_url)
        builder.feed(html)

        blocks, meta = builder.get_result()

        objects: list[KnowledgeObject] = []
        pos = 0

        # 1. Metadata (ja ir)
        meta_props = {k: v for k, v in meta.items() if v}
        if meta_props:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="metadata",
                properties=meta_props,
                confidence=0.95,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # 2. Document — visi satura bloki secībā
        if blocks:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="document",
                properties={
                    "title": meta.get("title", package.source.title or ""),
                    "blocks": blocks,
                    "block_count": len(blocks),
                },
                confidence=0.95,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        warnings = []
        if not objects:
            warnings.append("No content could be extracted from HTML")
            confidence = 0.5
        elif not blocks and len(objects) == 1 and objects[0].type == "metadata":
            # Tikai metadata bez satura — iespējams SPA shell vai verification lapa
            # Atgriežam tukšu, lai pipeline varētu mēģināt citu extractoru
            return ExtractorResult(
                warnings=["HTML appears to be a loading shell — no actual content found"],
            )

        # 3. JSON-LD (ja atrasts)
        json_ld_objects = find_json_ld(html)
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

        warnings = []
        if not objects:
            warnings.append("No content could be extracted")
            confidence = 0.5
        else:
            confidence = 0.95

        return ExtractorResult(
            knowledge_objects=objects,
            confidence=confidence,
            extractor_version=self.version,
            warnings=warnings,
        )

    def _build_ld_props(self, ld_obj: dict) -> dict:
        """Veido plakanu dict no JSON-LD objekta."""
        props = {}
        interesting_keys = [
            "name", "headline", "description", "author", "datePublished",
            "dateModified", "publisher", "image", "url", "mainEntityOfPage",
        ]
        for key in interesting_keys:
            if key in ld_obj:
                val = ld_obj[key]
                if isinstance(val, dict):
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