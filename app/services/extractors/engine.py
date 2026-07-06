"""
Config Engine — izpilda YAML konfigurācijas un veido KnowledgeObjects.

Darbība:
1. Saņem CapturePackage + HTML
2. Atrast atbilstošu konfigurāciju pēc URL (config_loader)
3. Izvelk visus nepieciešamos JSON avotus no HTML
4. Katram 'objects[].fields' laukam mēģina atrast vērtību
5. Veido KnowledgeObjects un atgriež ExtractorResult

Config formāts:
    name: str          — unikāls nosaukums
    version: int       — config versija
    match: {domains, patterns}  — URL noteikšana
    sources: [{type, name}]     — JSON avoti (json_var, json_ld, meta)
    objects: [{type, fields}]   — KnowledgeObject definīcijas

Field vērtības:
    "source_name.dot.path"          → path pret avotu
    ["path1", "path2"]              → fallback ķēde (pirmais, kas atrasts)
    "$meta:property_name"           → meta tags
    "$source.field"                 → CapturePackage source lauks
    {"path": "...", "transform": "..."} — ar transformāciju
"""

from typing import Any

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult, KnowledgeObject
from app.services.extractors import BaseExtractor
from app.services.extractors.config_loader import get_config_for_url
from app.services.extractors.html_tools import find_json_var, find_json_ld, find_meta_tag
from app.services.extractors.path_tools import resolve_path


class ConfigEngine(BaseExtractor):
    """
    Config-driven extractor engine.

    Izmanto YAML konfigurācijas, lai noteiktu kā izvilkt
    KnowledgeObjects no jebkuras HTML lapas.

    Ja konfigurācija nav atrasta, extract() atgriež None —
    pipeline turpina ar Python extractoriem.
    """

    name = "config-engine"
    version = "1.0"

    def can_handle(self, package: CapturePackage, html: str | None) -> bool:
        """Pārbauda vai ir konfigurācija šim URL."""
        url = package.source.url or ""
        config = get_config_for_url(url)
        return config is not None

    def extract(self, package: CapturePackage, html: str | None) -> ExtractorResult:
        """
        Izpilda konfigurāciju pret HTML.

        Returns:
            ExtractorResult ar KnowledgeObjects, vai tukšu rezultātu
        """
        url = package.source.url or ""
        config = get_config_for_url(url)

        if not config:
            return ExtractorResult(
                warnings=[f"No config found for URL: {url}"],
            )

        if not html:
            return ExtractorResult(
                warnings=["No HTML available for extraction"],
            )

        # 1. Izvelkam visus nepieciešamos JSON avotus no HTML
        raw_sources = self._extract_sources(config, html)

        # 2. Izvelkam meta tagus (vienmēr pieejami)
        meta_tags = self._get_meta_tags(html)

        # 3. Veidojam KnowledgeObjects
        objects: list[KnowledgeObject] = []
        pos = 0
        warnings: list[str] = []

        for obj_def in config.get("objects", []):
            obj_type = obj_def.get("type", "")
            if not obj_type:
                continue

            fields = obj_def.get("fields", {})
            properties: dict[str, Any] = {}
            obj_confidence = obj_def.get("confidence", 0.9)

            # Pārbaudam condition (ja ir)
            condition = obj_def.get("condition")
            if condition:
                if not self._check_condition(condition, raw_sources, meta_tags, package):
                    continue

            # Katram laukam mēģinām atrast vērtību
            for field_name, field_config in fields.items():
                value = self._resolve_field(field_config, raw_sources, meta_tags, package, html)
                if value is not None:
                    # Transformācijas
                    if isinstance(field_config, dict) and "transform" in field_config:
                        value = self._apply_transform(value, field_config["transform"])
                    properties[field_name] = value

            # Tikai ja ir kaut kas būtisks
            if not properties:
                continue

            # Confidence var būt atkarīgs no tā, kurus avotus izmantojām
            # (vienkārši, bet efektīvi)
            if "player" in raw_sources:
                obj_confidence = max(obj_confidence, 0.95)

            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type=obj_type,
                properties=properties,
                confidence=obj_confidence,
                extracted_by=config.get("name", self.name),
                position=pos,
            ))
            pos += 1

        return ExtractorResult(
            knowledge_objects=objects,
            confidence=0.95 if objects else 0.0,
            extractor_version=f"config-v{config.get('version', 1)}",
            warnings=warnings,
        )

    def _extract_sources(self, config: dict, html: str) -> dict[str, Any]:
        """Izvelk visus nepieciešamos JSON avotus no HTML."""
        sources: dict[str, Any] = {}

        for src_def in config.get("sources", []):
            src_type = src_def.get("type", "")
            src_name = src_def.get("name", "")

            if src_type == "json_var" and src_name:
                data = find_json_var(html, src_name)
                if data is not None:
                    key = src_def.get("key", src_name)
                    sources[key] = data

            elif src_type == "json_ld":
                ld_data = find_json_ld(html)
                if ld_data:
                    key = src_def.get("key", "json_ld")
                    sources[key] = ld_data

        return sources

    def _get_meta_tags(self, html: str) -> dict[str, str]:
        """Izvelk visus meta tagus (kešošana starp izsaukumiem)."""
        from app.services.extractors.html_tools import find_meta_tags
        return find_meta_tags(html)

    def _resolve_field(
        self,
        field_config: Any,
        sources: dict[str, Any],
        meta_tags: dict[str, str],
        package: CapturePackage,
        html: str,
    ) -> Any:
        """
        Atrod vērtību laukam pēc field_config.

        field_config var būt:
        - String: "source_name.path.to.field"
        - List: ["fallback1", "fallback2"]
        - Dict: {"path": "...", "transform": "..."}
        - String ar prefixu: "$meta:og:title", "$source.title"
        """
        # Saraksts ar fallbackiem
        if isinstance(field_config, list):
            for item in field_config:
                value = self._resolve_single_field(item, sources, meta_tags, package, html)
                if value is not None and not (isinstance(value, str) and not value.strip()):
                    return value
            return None

        # Viena vērtība
        return self._resolve_single_field(field_config, sources, meta_tags, package, html)

    def _resolve_single_field(
        self,
        field_def: Any,
        sources: dict[str, Any],
        meta_tags: dict[str, str],
        package: CapturePackage,
        html: str,
    ) -> Any:
        """Atrisina vienu lauka definīciju."""
        if isinstance(field_def, dict):
            path = field_def.get("path", "")
            if path.startswith("$css:"):
                return self._extract_css(html, path[5:])
            value = self._resolve_path(path, sources, meta_tags, package, html)
            if value is not None and "transform" in field_def:
                value = self._apply_transform(value, field_def["transform"])
            return value

        if not isinstance(field_def, str):
            return None

        # $css: (CSS selector)
        if field_def.startswith("$css:"):
            return self._extract_css(html, field_def[5:])

        # $meta: tag
        if field_def.startswith("$meta:"):
            tag_name = field_def[6:]
            return meta_tags.get(tag_name, None)

        # $source: field
        if field_def.startswith("$source."):
            field_name = field_def[8:]
            return getattr(package.source, field_name, None)

        # $source:title (bez punkta)
        if field_def == "$source":
            return package.source.title

        # $ld: path (JSON-LD īsceļš)
        if field_def.startswith("$ld."):
            path = field_def[4:]
            # Meklējam JSON-LD pēc dažādiem iespējamiem key vārdiem
            ld_list = None
            for key in ("ld", "json_ld", "json-ld"):
                ld_list = sources.get(key)
                if ld_list is not None:
                    break
            if not ld_list:
                return None
            return resolve_path(ld_list[0], path)

        # Parasts ceļš: "source_name.path.to.field"
        return self._resolve_path(field_def, sources, meta_tags, package, html)

    def _resolve_path(
        self,
        path: str,
        sources: dict[str, Any],
        meta_tags: dict[str, str],
        package: CapturePackage,
        html: str,
    ) -> Any:
        """Atrisina 'source_name.path.to.field' ceļu."""
        if not path or "." not in path:
            return None

        # Atdalām avota nosaukumu (pirmais segments)
        dot_pos = path.find(".")
        source_name = path[:dot_pos]
        field_path = path[dot_pos + 1:]

        source_data = sources.get(source_name)
        if source_data is None:
            return None

        return resolve_path(source_data, field_path)

    def _check_condition(
        self,
        condition: Any,
        sources: dict[str, Any],
        meta_tags: dict[str, str],
        package: CapturePackage,
    ) -> bool:
        """
        Pārbauda nosacījumu objekta veidošanai.

        Vienkāršākie nosacījumi:
        - String: "source.path" — patiess ja ceļš eksistē
        - Dict: {"exists": "source.path"} — eksistences pārbaude
        """
        if isinstance(condition, str):
            value = self._resolve_single_field(condition, sources, meta_tags, package, "")
            return value is not None and value != ""

        if isinstance(condition, dict):
            if "exists" in condition:
                value = self._resolve_single_field(
                    condition["exists"], sources, meta_tags, package, ""
                )
                return value is not None and value != ""

        return True

    def _extract_css(self, html: str, selector: str) -> str | None:
        """
        Izvelk tekstu no HTML, izmantojot vienkāršu CSS selektoru.

        Atbalsta:
        - tag: "a" — atrod pirmo <a>
        - tag.class: "a.title" — atrod pirmo <a> ar class="...title..."
        - tag#id: "div#content"
        - [attr]: "[data-author]" — atrod elementu ar atribūtu
        - $css:a.title@href — atrod href atribūtu no pirmā <a class="title">
        - $css:$tag.class@attr — izvelk atribūtu
        """
        import re

        if not html or not selector:
            return None

        # Atribūta izvilkšana: "a.title@href"
        extract_attr = None
        if "@" in selector:
            selector, extract_attr = selector.rsplit("@", 1)
            if not selector:
                # Tikai "href" — meklējam jebkuru elementu ar šo atribūtu
                for m in re.finditer(
                    rf'\s{re.escape(extract_attr)}=["\']([^"\']+)["\']',
                    html,
                ):
                    return m.group(1)
                return None

        # Atdalām tag nosaukumu
        parts = selector.strip().split()
        # Ja ir vairākas daļas (piem., ".redditname a"), ņemam pēdējo kā tag
        # bet class meklējam pirmajā daļā
        full_selector = selector
        selector = parts[-1] if len(parts) > 1 else parts[0]

        tag = None
        class_name = None
        elem_id = None
        is_wildcard_tag = False

        # Izņemam tag nosaukumu
        tag_match = re.match(r'^([a-zA-Z0-9]+)', selector)
        if tag_match:
            tag = tag_match.group(1)
            selector = selector[len(tag):]
        else:
            tag = r'[a-zA-Z][a-zA-Z0-9]*'
            is_wildcard_tag = True

        # Izņemam .class — meklējam visā full_selector
        # Atbalstām arī .class1.class2 (vairākas klases)
        class_matches = re.findall(r'\.([a-zA-Z0-9_-]+)', full_selector)
        class_name = " ".join(class_matches) if class_matches else None

        # Izņemam #id
        id_match = re.search(r'#([a-zA-Z0-9_-]+)', full_selector)
        if id_match:
            elem_id = id_match.group(1)

        # Izņemam [attr]
        attrs = re.findall(r'\[([a-zA-Z_-][a-zA-Z0-9_-]*)\]', full_selector)

        # Ja ir [attr] bez tag, meklējam jebkuru elementu
        if not tag_match and not class_name and not elem_id and attrs:
            for attr in attrs:
                for m in re.finditer(
                    rf'<[^>]*\s{re.escape(attr)}=["\']([^"\']+)["\'][^>]*>',
                    html,
                    re.IGNORECASE,
                ):
                    return m.group(1)
            return None

        # Veidojam vienkāršu regex
        # Atrodam elementu ar šiem atribūtiem, neatkarīgi no secības
        # Vairākas klases: katra jāatrod neatkarīgi
        class_req = ""
        if class_matches:
            for c in class_matches:
                class_req += rf'(?=[^>]*\bclass\s*=\s*["\'][^"\']*{re.escape(c)}[^"\']*["\'])'
        id_req = rf'(?=[^>]*\bid\s*=\s*["\']{re.escape(elem_id)}["\'])' if elem_id else ""

        # Ja nav specifiska tag, lietojam wildcard bez escaping
        if is_wildcard_tag:
            if extract_attr:
                pattern = rf'<{tag}{class_req}{id_req}[^>]*\s{re.escape(extract_attr)}=["\']([^"\']+)["\']'
            else:
                pattern = rf'<{tag}{class_req}{id_req}[^>]*>(.*?)</{tag}>'
        else:
            safe_tag = re.escape(tag)
            if extract_attr:
                pattern = rf'<{safe_tag}{class_req}{id_req}[^>]*\s{re.escape(extract_attr)}=["\']([^"\']+)["\']'
            else:
                pattern = rf'<{safe_tag}{class_req}{id_req}[^>]*>(.*?)</{safe_tag}>'

        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            if extract_attr:
                return match.group(1)
            text = re.sub(r'<[^>]+>', '', match.group(1))
            return text.strip() or None

        return None

    def _apply_transform(self, value: Any, transform: str) -> Any:
        """
        Piemēro transformāciju vērtībai.

        Atbalstītās transformācijas:
        - "join_text" — salīmē listi ar stringiem (YouTube runs[])
        - "first" — atgriež pirmo elementu no lista
        - "last" — atgriež pēdējo elementu no lista
        - "str" — pārvērš par string
        - "int" — pārvērš par int
        """
        if transform == "join_text":
            if isinstance(value, list):
                return "".join(str(item.get("text", "") if isinstance(item, dict) else item) for item in value)
            return str(value)

        if transform == "first":
            if isinstance(value, list) and value:
                return value[0]
            return value

        if transform == "last":
            if isinstance(value, list) and value:
                return value[-1]
            return value

        if transform == "str":
            return str(value)

        if transform == "int":
            try:
                return int(value)
            except (ValueError, TypeError):
                return value

        return value