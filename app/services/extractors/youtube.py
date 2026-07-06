"""
YouTube Extractor — specializēts YouTube video extractor.

Izmanto kopīgos HTML rīkus no html_tools.py un url_tools.py,
nevis savas implementācijas.

Šis extractors ir "gaļīgs" Python extractors, kas demonstrē,
kā rīkoties ar sarežģītām lapām (YouTube), kurām ir vairāki
JSON avoti, deep nesting un fallback ķēdes.

Nākotnē lielākā daļa šīs loģikas var tikt pārcelta uz konfigurāciju.
"""

from app.models.capture_package import CapturePackage
from app.models.knowledge import ExtractorResult, KnowledgeObject
from app.services.extractors import BaseExtractor
from app.services.extractors.html_tools import find_json_var, find_json_ld, find_meta_tag
from app.services.extractors.path_tools import resolve_path, get_first_existing
from app.services.extractors.url_tools import match_domain, extract_video_id

# ─── YouTube atpazīšana ─────────────────────────────────────────

_YOUTUBE_DOMAINS = ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"]

# Video lapu ceļi — watch, shorts, youtu.be
_VIDEO_PATHS = ["/watch", "/shorts/"]


def _is_youtube_video_url(url: str) -> bool:
    """Vai URL ir YouTube video lapa."""
    if not match_domain(url, _YOUTUBE_DOMAINS):
        return False
    # youtu.be vienmēr ir video
    if "youtu.be" in url.lower():
        return True
    # youtube.com — jābūt /watch vai /shorts/
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path
    return any(path.startswith(p) or path == p for p in _VIDEO_PATHS)


# ─── YouTube Extractor ───────────────────────────────────────────

class YouTubeExtractor(BaseExtractor):
    """
    Specializēts YouTube video extractor.

    Stratēģija:
    1. ytInitialPlayerResponse (prioritāri — pilnīgākie dati)
    2. ytInitialData (papildina, ja playerResponse nav)
    3. JSON-LD (Schema.org VideoObject)
    4. DOM meta tagi (fallback)

    Katrs nākamais solis ir mazāk ticams, bet joprojām vērtīgs.
    """

    name = "youtube"
    version = "1.0"

    def can_handle(self, package: CapturePackage, html: str | None) -> bool:
        return _is_youtube_video_url(package.source.url or "")

    def extract(self, package: CapturePackage, html: str | None) -> ExtractorResult:
        url = package.source.url or ""
        video_id = extract_video_id(url) or ""
        objects: list[KnowledgeObject] = []
        pos = 0
        warnings: list[str] = []

        if not html:
            return ExtractorResult(warnings=["No HTML provided"])

        # ── Izvelkam visus JSON avotus ──
        player_data = find_json_var(html, "ytInitialPlayerResponse")
        init_data = find_json_var(html, "ytInitialData")
        json_ld_objects = find_json_ld(html)
        ld_info = {}
        for ld in json_ld_objects:
            if isinstance(ld, dict) and ld.get("@type") in ("VideoObject", "Video"):
                ld_info = ld
                break

        # Apvienojam visus datu avotus path_tools.get_first_existing ērtībai
        sources = {}
        if player_data:
            sources["player"] = player_data
        if init_data:
            sources["init"] = init_data
        if ld_info:
            sources["ld"] = ld_info

        # ── Izvelkam video properties ──
        video_props = self._extract_video_props(sources, html, package, video_id)

        # ── Confidence aprēķins ──
        confidence = 0.50
        if player_data:
            confidence = 0.98
        elif ld_info:
            confidence = 0.90
        elif video_props.get("title") or video_id:
            confidence = 0.70
            warnings.append("Extracted from DOM fallback — missing ytInitialPlayerResponse")

        # ── Video KnowledgeObject ──
        title = video_props.get("title", "")
        if title or video_id:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="video",
                properties=video_props,
                confidence=confidence,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1
        else:
            warnings.append("Could not extract any video data")

        # ── Metadata (ja player_data bija) ──
        meta_props = self._extract_meta_props(player_data, package, title)
        if len(meta_props) > 1:
            meta_conf = confidence if player_data else 0.85
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="metadata",
                properties=meta_props,
                confidence=meta_conf,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # ── Link ──
        watch_url = url or f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        if watch_url:
            objects.append(KnowledgeObject(
                capture_id=package.capture_id,
                type="link",
                properties={"href": watch_url, "text": title or "Watch on YouTube"},
                confidence=1.0,
                extracted_by=self.name,
                position=pos,
            ))
            pos += 1

        # Warnings
        if not player_data:
            warnings.append("ytInitialPlayerResponse not found in page HTML")

        return ExtractorResult(
            knowledge_objects=objects,
            confidence=confidence if objects else 0.0,
            extractor_version=self.version,
            warnings=warnings,
        )

    def _extract_video_props(
        self,
        sources: dict,
        html: str,
        package: CapturePackage,
        video_id: str,
    ) -> dict:
        """Izvelk video properties no visiem pieejamajiem avotiem."""
        props: dict = {}
        player_data = sources.get("player", {})
        init_data = sources.get("init", {})
        ld_info = sources.get("ld", {})
        vd = player_data.get("videoDetails") or {}

        # Video ID
        props["video_id"] = video_id or vd.get("videoId", "")

        # Title — prioritāra ķēde
        props["title"] = (
            vd.get("title")
            or self._yt_init_title(init_data)
            or ld_info.get("name")
            or find_meta_tag(html, "og:title")
            or find_meta_tag(html, "title")
            or package.source.title
            or ""
        )

        # Description
        props["description"] = (
            vd.get("shortDescription")
            or ld_info.get("description")
            or find_meta_tag(html, "og:description")
            or find_meta_tag(html, "description")
            or ""
        )[:2000]

        # Author
        author = vd.get("author", "")
        if not author:
            ld_author = ld_info.get("author", {})
            if isinstance(ld_author, dict):
                author = ld_author.get("name", "")
            elif isinstance(ld_author, str):
                author = ld_author
        if not author:
            author = find_meta_tag(html, "og:video:tag") or find_meta_tag(html, "author")
        if author:
            props["author"] = author

        # Channel ID
        channel_id = vd.get("channelId", "")
        if channel_id:
            props["channel_id"] = channel_id

        # Duration
        duration = int(vd.get("lengthSeconds", 0))
        if not duration:
            micro = player_data.get("microformat", {}).get("playerMicroformatRenderer", {})
            duration = int(micro.get("lengthSeconds", 0))
        if duration:
            props["duration_seconds"] = duration

        # View count
        view_count = int(vd.get("viewCount", 0))
        if view_count:
            props["view_count"] = view_count

        # Keywords
        keywords = vd.get("keywords") or []
        if keywords:
            props["keywords"] = keywords

        # Live
        props["is_live"] = bool(vd.get("isLiveContent", False))

        # Thumbnail
        thumbnail = self._extract_thumbnail(vd, ld_info)
        if thumbnail:
            props["thumbnail"] = thumbnail

        # Publish date
        pub_date = self._extract_publish_date(player_data, ld_info)
        if pub_date:
            props["publish_date"] = pub_date

        # Category
        category = player_data.get("microformat", {}).get("playerMicroformatRenderer", {}).get("category")
        if category:
            props["category"] = category

        # Available countries
        ac = player_data.get("microformat", {}).get("playerMicroformatRenderer", {}).get("availableCountries")
        if ac:
            props["available_countries"] = ac

        return props

    def _yt_init_title(self, data: dict) -> str | None:
        """Mēģina atrast title no ytInitialData struktūras."""
        try:
            contents = data.get("contents", {})
            two_col = contents.get("twoColumnWatchNextResults", {})
            results = two_col.get("results", {})
            primary = results.get("results", {})
            prim_contents = primary.get("contents", [])
            for item in prim_contents:
                vs = item.get("videoPrimaryInfoRenderer", {})
                if not vs:
                    continue
                title_runs = vs.get("title", {}).get("runs", [])
                if title_runs:
                    return "".join(r.get("text", "") for r in title_runs)
        except Exception:
            pass
        return None

    def _extract_thumbnail(self, vd: dict, ld_info: dict) -> str | None:
        """Izvelk thumbnail URL."""
        thumbs = vd.get("thumbnail", {}).get("thumbnails", [])
        if thumbs:
            return thumbs[-1].get("url", "")
        thumbs_url = ld_info.get("thumbnailUrl")
        if thumbs_url:
            if isinstance(thumbs_url, list):
                return thumbs_url[-1] if thumbs_url else None
            return thumbs_url
        return None

    def _extract_publish_date(self, player_data: dict, ld_info: dict) -> str | None:
        """Izvelk publish date no playerResponse vai JSON-LD."""
        micro = player_data.get("microformat", {}).get("playerMicroformatRenderer", {})
        if micro.get("publishDate"):
            return micro["publishDate"]
        if micro.get("uploadDate"):
            return micro["uploadDate"]
        if ld_info.get("uploadDate"):
            return ld_info["uploadDate"]
        return None

    def _extract_meta_props(self, player_data: dict | None, package: CapturePackage, title: str) -> dict:
        """Izvelk metadata properties."""
        meta: dict = {}
        meta["title"] = package.source.title or title or ""

        if not player_data:
            return meta

        micro = player_data.get("microformat", {}).get("playerMicroformatRenderer", {})
        vd = player_data.get("videoDetails", {}) or {}

        if micro.get("publishDate"):
            meta["publish_date"] = micro["publishDate"]
        if micro.get("category"):
            meta["category"] = micro["category"]
        if vd.get("keywords"):
            meta["keywords"] = vd["keywords"]
        if micro.get("availableCountries"):
            meta["available_countries"] = micro["availableCountries"]
        if vd.get("thumbnail"):
            thumbs = vd["thumbnail"].get("thumbnails", [])
            if thumbs:
                meta["thumbnail"] = thumbs[-1].get("url", "")
        if vd.get("isLiveContent"):
            meta["is_live"] = True

        return meta