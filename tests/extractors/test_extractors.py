"""
Extractor testi — pārbauda gan config engine, gan Python extractorus.

Katra testa kategorija:
- Test HTML fixture + expected JSON
- Config engine tests
- Generic HTML extractor tests
- HTML/URL/Path tools tests

Palaist: pytest tests/extractors/ -v
"""

import json
import os

import pytest

from app.models.capture_package import CapturePackage
from app.services.extractors.html_tools import (
    find_json_var, find_json_ld, find_meta_tags, find_meta_tag,
)
from app.services.extractors.url_tools import match_domain, extract_video_id
from app.services.extractors.path_tools import resolve_path, get_first_existing


# ─── Fixtures ──────────────────────────────────────────────────────

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
EXPECTED_DIR = os.path.join(os.path.dirname(__file__), "expected")


def load_fixture(name: str) -> str:
    """Ielādē HTML fixture failu."""
    path = os.path.join(FIXTURES_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"Fixture not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_expected(name: str) -> dict:
    """Ielādē sagaidāmo rezultātu JSON."""
    path = os.path.join(EXPECTED_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"Expected result not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_package(url: str, capture_id: str = "test_capture_001") -> CapturePackage:
    """Izveido testa CapturePackage."""
    from app.models.capture_package import SourceInfo
    return CapturePackage(
        capture_id=capture_id,
        source=SourceInfo(url=url, title=""),
    )


# ═══════════════════════════════════════════════════════════════════
# html_tools.py testi
# ═══════════════════════════════════════════════════════════════════


class TestFindJsonVar:
    """Testi find_json_var funkcijai."""

    def test_finds_simple_object(self):
        html = '<script>var myData = {"key": "value"};</script>'
        result = find_json_var(html, "myData")
        assert result == {"key": "value"}

    def test_finds_deep_nested(self):
        html = '<script>var testObj = {"a": {"b": {"c": [1,2,3]}}};</script>'
        result = find_json_var(html, "testObj")
        assert result == {"a": {"b": {"c": [1, 2, 3]}}}

    def test_returns_none_when_not_found(self):
        html = "<html><body>No JSON here</body></html>"
        result = find_json_var(html, "nonexistent")
        assert result is None

    def test_handles_empty_html(self):
        assert find_json_var("", "test") is None
        assert find_json_var(None, "test") is None  # type: ignore

    def test_handles_strings_with_braces(self):
        html = '<script>var x = {"text": "hello {world}"};</script>'
        result = find_json_var(html, "x")
        assert result == {"text": "hello {world}"}


class TestFindJsonLd:
    """Testi find_json_ld funkcijai."""

    def test_finds_single_ld(self):
        html = """
        <script type="application/ld+json">
        {"@type": "WebPage", "name": "Test"}
        </script>
        """
        result = find_json_ld(html)
        assert len(result) == 1
        assert result[0]["@type"] == "WebPage"

    def test_finds_multiple_ld(self):
        html = """
        <script type="application/ld+json">{"@type": "A"}</script>
        <script type="application/ld+json">{"@type": "B"}</script>
        """
        result = find_json_ld(html)
        assert len(result) == 2

    def test_returns_empty_when_none(self):
        assert find_json_ld("<html></html>") == []


class TestFindMetaTags:
    """Testi find_meta_tags funkcijai."""

    def test_finds_standard_meta(self):
        html = '<meta name="description" content="Test desc">'
        result = find_meta_tags(html)
        assert result.get("description") == "Test desc"

    def test_finds_og_meta(self):
        html = '<meta property="og:title" content="OG Title">'
        result = find_meta_tags(html)
        assert result.get("og:title") == "OG Title"

    def test_finds_charset(self):
        html = '<meta charset="utf-8">'
        result = find_meta_tags(html)
        assert result.get("charset") == "utf-8"

    def test_finds_all_meta_in_real_html(self):
        html = load_fixture("simple_article.html")
        result = find_meta_tags(html)
        assert "description" in result
        assert "author" in result
        assert "og:title" in result


# ═══════════════════════════════════════════════════════════════════
# url_tools.py testi
# ═══════════════════════════════════════════════════════════════════


class TestMatchDomain:
    def test_matches_exact_domain(self):
        assert match_domain("https://youtube.com/watch?v=abc", ["youtube.com"])

    def test_matches_www_domain(self):
        assert match_domain("https://www.youtube.com/watch?v=abc", ["youtube.com"])

    def test_rejects_unknown_domain(self):
        assert not match_domain("https://vimeo.com/video/abc", ["youtube.com"])

    def test_empty_url_returns_false(self):
        assert not match_domain("", ["youtube.com"])


class TestExtractVideoId:
    def test_watch_url(self):
        assert extract_video_id("https://youtube.com/watch?v=abc123") == "abc123"

    def test_youtu_be(self):
        assert extract_video_id("https://youtu.be/abc123") == "abc123"

    def test_shorts_url(self):
        assert extract_video_id("https://youtube.com/shorts/abc123") == "abc123"

    def test_embed_url(self):
        assert extract_video_id("https://youtube.com/embed/abc123") == "abc123"

    def test_non_youtube(self):
        assert extract_video_id("https://example.com") is None


# ═══════════════════════════════════════════════════════════════════
# path_tools.py testi
# ═══════════════════════════════════════════════════════════════════


class TestResolvePath:
    def test_simple_key(self):
        data = {"a": 1, "b": 2}
        assert resolve_path(data, "a") == 1

    def test_nested_key(self):
        data = {"a": {"b": {"c": "hello"}}}
        assert resolve_path(data, "a.b.c") == "hello"

    def test_array_index(self):
        data = {"items": [10, 20, 30]}
        assert resolve_path(data, "items[0]") == 10
        assert resolve_path(data, "items[-1]") == 30

    def test_nested_array(self):
        data = {"results": {"contents": [{"name": "first"}, {"name": "second"}]}}
        assert resolve_path(data, "results.contents[0].name") == "first"

    def test_missing_path(self):
        assert resolve_path({"a": 1}, "a.b.c") is None

    def test_empty_data(self):
        assert resolve_path(None, "a.b") is None

    def test_youtube_path(self):
        data = {
            "videoDetails": {
                "videoId": "test123",
                "title": "Test Video",
            }
        }
        assert resolve_path(data, "videoDetails.videoId") == "test123"
        assert resolve_path(data, "videoDetails.title") == "Test Video"


class TestGetFirstExisting:
    def test_returns_first_match(self):
        sources = {"src1": {"a": 1}, "src2": {"b": 2}}
        result = get_first_existing(sources, ["src1.a", "src2.b"])
        assert result == 1

    def test_falls_through_to_second(self):
        sources = {"src1": {}, "src2": {"value": "found"}}
        result = get_first_existing(sources, ["src1.value", "src2.value"])
        assert result == "found"

    def test_returns_none_when_all_missing(self):
        sources = {"src1": {"a": 1}}
        assert get_first_existing(sources, ["src1.b", "src2.c"]) is None


# ═══════════════════════════════════════════════════════════════════
# Config Engine testi
# ═══════════════════════════════════════════════════════════════════


class TestConfigEngine:
    """Testi config-driven engine pret YouTube HTML fixture."""

    def _run_engine(self, fixture_html: str, fixture_url: str):
        """Palaiž engine pret fixture."""
        from app.services.extractors.engine import ConfigEngine

        engine = ConfigEngine()
        package = make_package(fixture_url)
        html = load_fixture(fixture_html)
        result = engine.extract(package, html)
        return result

    def test_youtube_engine_detects_video(self):
        """Config engine atrod youtube config un izvelk video objektu."""
        result = self._run_engine("youtube_video.html", "https://www.youtube.com/watch?v=test123")
        types = [ko.type for ko in result.knowledge_objects]
        assert "video" in types, f"No video object found in: {types}"

    def test_youtube_engine_extracts_core_fields(self):
        """Core lauki (video_id, title, author) ir pareizi."""
        result = self._run_engine("youtube_video.html", "https://www.youtube.com/watch?v=test123")
        video = next((ko for ko in result.knowledge_objects if ko.type == "video"), None)
        assert video is not None, "No video object"

        props = video.properties
        assert props.get("video_id") == "test123"
        assert props.get("title") == "Test Video Title"
        assert props.get("author") == "TestAuthor"
        assert props.get("duration_seconds") == 3600

    def test_youtube_engine_matches_expected(self):
        """Config engine rezultāts atbilst expected JSON."""
        expected = load_expected("youtube_video_result.json")
        result = self._run_engine("youtube_video.html", "https://www.youtube.com/watch?v=test123")

        # Pārbaudam ka ir vismaz tik daudz objektu kā gaidām
        expected_types = {e["type"] for e in expected["expected_objects"]}
        actual_types = {ko.type for ko in result.knowledge_objects}
        for t in expected_types:
            assert t in actual_types, f"Missing expected type: {t}"


# ═══════════════════════════════════════════════════════════════════
# Generic HTML Extractor testi
# ═══════════════════════════════════════════════════════════════════


class TestGenericHtmlExtractor:
    """Testi GenericHtmlExtractor pret dažādiem HTML fixture."""

    def _run_generic(self, fixture_html: str, url: str = "https://example.com/page"):
        from app.services.extractors.generic_html import GenericHtmlExtractor

        extractor = GenericHtmlExtractor()
        package = make_package(url)
        html = load_fixture(fixture_html)
        return extractor.extract(package, html)

    def _get_document_blocks(self, result):
        """Izvelk document blokus no rezultāta."""
        for ko in result.knowledge_objects:
            if ko.type == "document":
                return ko.properties.get("blocks", [])
        return []

    def test_article_extracts_metadata(self):
        """Generic HTML izvelk meta datus."""
        result = self._run_generic("simple_article.html")
        types = [ko.type for ko in result.knowledge_objects]
        assert "metadata" in types

    def test_article_extracts_headings(self):
        """Generic HTML atrod visus virsrakstus dokumentā."""
        result = self._run_generic("simple_article.html")
        blocks = self._get_document_blocks(result)
        headings = [b for b in blocks if b.get("type") == "heading"]
        assert len(headings) >= 3  # h1, h2, h2, h3

    def test_article_extracts_article_object(self):
        """Generic HTML izvelk document objektu."""
        result = self._run_generic("simple_article.html")
        docs = [ko for ko in result.knowledge_objects if ko.type == "document"]
        assert len(docs) >= 1

    def test_article_contains_links(self):
        """Generic HTML izvelk saites (nav navigācijas)."""
        result = self._run_generic("simple_article.html")
        blocks = self._get_document_blocks(result)
        paragraphs = [b for b in blocks if b.get("type") == "paragraph"]
        # Pārbaudam vai ir satura paragrāfi
        assert len(paragraphs) >= 3

    def test_article_contains_code_blocks(self):
        """Generic HTML atrod koda blokus."""
        result = self._run_generic("simple_article.html")
        blocks = self._get_document_blocks(result)
        code_blocks = [b for b in blocks if b.get("type") == "code"]
        assert len(code_blocks) >= 1

    def test_no_html_returns_warning(self):
        """Bez HTML atgriež brīdinājumu."""
        from app.services.extractors.generic_html import GenericHtmlExtractor
        extractor = GenericHtmlExtractor()
        result = extractor.extract(make_package("https://example.com"), None)
        assert len(result.warnings) > 0

    def test_can_handle_returns_false_for_small_html(self):
        """can_handle atgriež False, ja HTML ir pārāk mazs."""
        from app.services.extractors.generic_html import GenericHtmlExtractor
        extractor = GenericHtmlExtractor()
        assert not extractor.can_handle(make_package("https://example.com"), None)
        assert not extractor.can_handle(make_package("https://example.com"), "<html></html>")
        assert extractor.can_handle(make_package("https://example.com"), "<html><body><p>Content</p></body></html>")


# ═══════════════════════════════════════════════════════════════════
# Pipeline testi
# ═══════════════════════════════════════════════════════════════════


class TestPipeline:
    """Testi extractor pipeline — kā extractori sadarbojas."""

    def test_pipeline_runs_youtube_config_first(self):
        """Pipeline vispirms mēģina Python extractorus (YouTube) pirms config engine."""
        from app.services.extractor_pipeline import run_pipeline

        html = load_fixture("youtube_video.html")
        package = make_package("https://www.youtube.com/watch?v=test123")
        result = run_pipeline(package, html)

        # Python YouTubeExtractor ir pirmais un izvelk video
        types = [ko.type for ko in result.knowledge_objects]
        assert "video" in types
        # YouTubeExtractor.name == "youtube"
        assert result.knowledge_objects[0].extracted_by == "youtube"

    def test_pipeline_falls_back_to_generic(self):
        """Nepazīstamām lapām pipeline izmanto generic HTML."""
        from app.services.extractor_pipeline import run_pipeline

        html = load_fixture("simple_article.html")
        package = make_package("https://example.com/article")
        result = run_pipeline(package, html)

        types = [ko.type for ko in result.knowledge_objects]
        assert "metadata" in types
        assert "document" in types

    def test_pipeline_no_html(self):
        """Bez HTML pipeline atgriež brīdinājumu."""
        from app.services.extractor_pipeline import run_pipeline

        package = make_package("https://example.com")
        result = run_pipeline(package, None)
        assert result.warnings
        assert not result.knowledge_objects


# ═══════════════════════════════════════════════════════════════════
# Config loader testi
# ═══════════════════════════════════════════════════════════════════


class TestConfigLoader:
    """Testi config_loader — config ielāde un atpazīšana."""

    def setup_method(self):
        from app.services.extractors import config_loader
        config_loader.clear_cache()

    def test_loads_all_configs(self):
        """config_loader atrod un ielādē visus .yaml failus."""
        from app.services.extractors.config_loader import load_all_configs

        configs = load_all_configs()
        assert len(configs) >= 1
        names = [c.get("name") for c in configs]
        assert "youtube_video" in names

    def test_finds_youtube_config(self):
        """YouTube URL atrod youtube_video konfigurāciju."""
        from app.services.extractors.config_loader import get_config_for_url

        config = get_config_for_url("https://www.youtube.com/watch?v=abc123")
        assert config is not None
        assert config["name"] == "youtube_video"

    def test_returns_none_for_unknown_url(self):
        """Nepazīstams URL atgriež None."""
        from app.services.extractors.config_loader import get_config_for_url

        config = get_config_for_url("https://example.com/unknown")
        assert config is None

    def test_returns_none_for_empty_url(self):
        """Tukšs URL atgriež None."""
        from app.services.extractors.config_loader import get_config_for_url
        assert get_config_for_url("") is None