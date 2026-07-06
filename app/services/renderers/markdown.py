"""
Markdown Renderer — pārvērš KnowledgeObjects uz Markdown HTML.

Šis ir pirmais rendereris, bet ne galvenais datu attēlošanas veids.
Renders to HTML ar GitHub-like styling.
"""

import json
from typing import Any

from app.services.renderers.base import BaseRenderer, register


class MarkdownRenderer(BaseRenderer):
    name = "markdown"
    label = "Markdown"
    description = "Renders knowledge objects as formatted markdown"
    icon = "📝"

    def render(self, objects: list[dict], capture_ref: dict[str, Any]) -> str:
        if not objects:
            return self._html_empty(capture_ref)

        lines: list[str] = []
        source_url = capture_ref.get("source_url", "")
        source_title = capture_ref.get("source_title", "")

        def parse_tags(tags):
            if isinstance(tags, str):
                try: return json.loads(tags)
                except: return []
            return tags or []

        # Wrap in prose content div
        lines.append('<div class="prose max-w-none">')

        # Header
        title = source_title or "Untitled"
        lines.append(f"<h1>{self._esc(title)}</h1>")
        if source_url:
            lines.append(f'<p><strong>Source:</strong> <a href="{self._esc(source_url)}">{self._esc(source_url)}</a></p>')
        lines.append(f"<p><strong>Type:</strong> {self._esc(capture_ref.get('capture_type', 'page'))}</p>")
        proj = capture_ref.get("project")
        if proj:
            lines.append(f"<p><strong>Project:</strong> {self._esc(proj)}</p>")
        tags = parse_tags(capture_ref.get("tags"))
        if tags:
            lines.append(f"<p><strong>Tags:</strong> {', '.join(self._esc(t) for t in tags)}</p>")
        saved = capture_ref.get("saved_at", "")
        if saved:
            lines.append(f"<p><strong>Saved:</strong> {saved}</p>")

        lines.append("<hr>")

        for ko in objects:
            props = ko.get("properties", {})
            ko_type = ko.get("type", "unknown")

            if ko_type == "metadata":
                lines.append("<section class='ko-section'>")
                lines.append("<h2>Page Metadata</h2>")
                lines.append("<table><tbody>")
                for k, v in props.items():
                    if v:
                        if isinstance(v, list):
                            v = ", ".join(v)
                        lines.append(f"<tr><td><strong>{k}</strong></td><td>{self._esc(str(v))}</td></tr>")
                lines.append("</tbody></table>")
                lines.append("</section>")

            elif ko_type == "article":
                text = props.get("text", "")
                lines.append("<hr>")
                lines.append(f"<h2>{self._esc(props.get('title', 'Content'))}</h2>")
                for para in text.split("\n"):
                    para = para.strip()
                    if para:
                        lines.append(f"<p>{self._esc(para)}</p>")

            elif ko_type == "heading":
                level = min(props.get("level", 2), 6)
                text = props.get("text", "")
                lines.append(f"<h{level}>{self._esc(text)}</h{level}>")

            elif ko_type == "code_block":
                lang = props.get("language", "")
                code = props.get("code", "")
                extra = f' class="language-{self._esc(lang)}"' if lang else ""
                lines.append(f"<pre{extra}><code>{self._esc(code)}</code></pre>")

            elif ko_type == "link":
                href = props.get("href", "")
                text = props.get("text", "")
                if href and text:
                    lines.append(f'<p class="ko-link">→ <a href="{self._esc(href)}">{self._esc(text)}</a></p>')
                elif href:
                    lines.append(f'<p class="ko-link">→ <a href="{self._esc(href)}">{self._esc(href)}</a></p>')

            elif ko_type == "image":
                src = props.get("src", "")
                alt = props.get("alt", "")
                lines.append(f'<p><img src="{self._esc(src)}" alt="{self._esc(alt)}" loading="lazy"></p>')

            elif ko_type == "quote":
                text = props.get("text", "")
                source = props.get("source", "")
                if text:
                    lines.append(f"<blockquote><p>{self._esc(text)}</p>")
                    if source:
                        lines.append(f"<footer>— {self._esc(source)}</footer>")
                    lines.append("</blockquote>")

            elif ko_type == "list_item":
                text = props.get("text", "")
                if text:
                    lines.append(f"<li>{self._esc(text)}</li>")

            elif ko_type == "video":
                lines.append("<section class='ko-section video-card'>")
                lines.append(f"<h2>🎬 {self._esc(props.get('title', 'Video'))}</h2>")
                lines.append("<table class='kv-props-table'><tbody>")
                # Core info
                if props.get("author"):
                    channel_url = props.get("channel_url") or ""
                    if channel_url:
                        lines.append(f'<tr><td>Channel</td><td><a href="{self._esc(channel_url)}">{self._esc(props["author"])}</a></td></tr>')
                    else:
                        lines.append(f"<tr><td>Channel</td><td>{self._esc(props['author'])}</td></tr>")
                if props.get("channel_id"):
                    lines.append(f'<tr><td>Channel ID</td><td><code>{self._esc(props["channel_id"])}</code></td></tr>')
                if props.get("view_count"):
                    lines.append(f'<tr><td>Views</td><td>{self._esc(str(props["view_count"]))}</td></tr>')
                if props.get("view_count_text"):
                    lines.append(f'<tr><td>Views</td><td>{self._esc(props["view_count_text"])}</td></tr>')
                if props.get("duration_seconds"):
                    mins, secs = divmod(int(props["duration_seconds"]), 60)
                    hrs, mins = divmod(mins, 60)
                    if hrs:
                        dur = f"{hrs}:{mins:02d}:{secs:02d}"
                    else:
                        dur = f"{mins}:{secs:02d}"
                    lines.append(f"<tr><td>Duration</td><td>{dur}</td></tr>")
                if props.get("publish_date"):
                    lines.append(f"<tr><td>Published</td><td>{self._esc(props['publish_date'])}</td></tr>")
                if props.get("category"):
                    lines.append(f"<tr><td>Category</td><td>{self._esc(props['category'])}</td></tr>")
                if props.get("keywords"):
                    kws = ", ".join(props["keywords"][:10])
                    lines.append(f"<tr><td>Keywords</td><td>{self._esc(kws)}</td></tr>")
                if props.get("is_live"):
                    lines.append("<tr><td>Live</td><td>🔴 Yes</td></tr>")
                if props.get("like_count_text"):
                    lines.append(f"<tr><td>Likes</td><td>{self._esc(props['like_count_text'])}</td></tr>")
                lines.append("</tbody></table>")
                # Thumbnail
                if props.get("thumbnail"):
                    lines.append(f'<p><img src="{self._esc(props["thumbnail"])}" alt="Video thumbnail" style="max-width:480px;border-radius:8px;" loading="lazy"></p>')
                # Description
                desc = props.get("description", "")
                if desc:
                    lines.append("<h3>Description</h3>")
                    for para in desc.split("\n"):
                        para = para.strip()
                        if para:
                            lines.append(f"<p>{self._esc(para)}</p>")
                # Video URL
                video_id = props.get("video_id", "")
                watch_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
                if watch_url:
                    lines.append(f'<p><a href="{self._esc(watch_url)}" class="btn" target="_blank">▶ Watch on YouTube</a></p>')
                lines.append("</section>")

        # Footer
        captured = capture_ref.get("captured_at", "")
        if captured:
            lines.append("<hr>")
            lines.append(f'<p class="text-muted"><em>Extracted by Recollect — {captured}</em></p>')

        lines.append("</div>")

        return "\n".join(lines)

    def _esc(self, s: str) -> str:
        """HTML escape."""
        if s is None:
            return ""
        return (s.replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&#39;"))

    def _html_empty(self, capture_ref: dict) -> str:
        title = capture_ref.get("source_title", "Untitled")
        return f'<div class="prose max-w-none"><h1>{self._esc(title)}</h1><p><em>No extracted content.</em></p></div>'


# ─── Automātiski reģistrējas ─────────────────────────────────────
register(MarkdownRenderer())