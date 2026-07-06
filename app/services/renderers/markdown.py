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
        lines.append('<div class="prose max-w-none kv-renderer-output">')

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

        # Sort objects by position
        sorted_objects = sorted(objects, key=lambda o: o.get("position", 0))

        for ko in sorted_objects:
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
                width = props.get("width")
                height = props.get("height")
                size_attr = ""
                if width and height:
                    size_attr = f' width="{self._esc(str(width))}" height="{self._esc(str(height))}"'
                lines.append(f'<p><img src="{self._esc(src)}" alt="{self._esc(alt)}" loading="lazy"{size_attr}></p>')

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
                    lines.append(f'<p><a href="{self._esc(watch_url)}" target="_blank">▶ Watch on YouTube</a></p>')
                lines.append("</section>")

            elif ko_type == "reddit_post":
                lines.append("<section class='ko-section reddit-card'>")
                lines.append(f"<h2>📰 {self._esc(props.get('title', 'Reddit Post'))}</h2>")
                lines.append("<table class='kv-props-table'><tbody>")
                if props.get("author"):
                    lines.append(f"<tr><td>Author</td><td>{self._esc(props['author'])}</td></tr>")
                if props.get("subreddit"):
                    lines.append(f"<tr><td>Subreddit</td><td>r/{self._esc(props['subreddit'])}</td></tr>")
                if props.get("score"):
                    lines.append(f"<tr><td>Score</td><td>{self._esc(str(props['score']))}</td></tr>")
                if props.get("timestamp"):
                    lines.append(f"<tr><td>Posted</td><td>{self._esc(props['timestamp'])}</td></tr>")
                if props.get("comments_count"):
                    lines.append(f"<tr><td>Comments</td><td>{self._esc(str(props['comments_count']))}</td></tr>")
                lines.append("</tbody></table>")
                if props.get("description"):
                    lines.append("<h3>Description</h3>")
                    lines.append(f"<p>{self._esc(props['description'])}</p>")
                if props.get("url"):
                    lines.append(f'<p><a href="{self._esc(props["url"])}" target="_blank">🔗 View on Reddit</a></p>')
                lines.append("</section>")

            elif ko_type == "document":
                blocks = props.get("blocks", [])
                if not blocks:
                    continue
                lines.append('<div class="document-content">')
                for block in blocks:
                    lines.append(self._render_block(block))
                lines.append('</div>')

            elif ko_type == "anchor":
                selected_text = props.get("selected_text", "")
                if selected_text:
                    lines.append("<section class='ko-section'>")
                    lines.append("<h2>📌 Anchor — Selected Text</h2>")
                    lines.append(f"<blockquote><p>{self._esc(selected_text)}</p></blockquote>")
                    before = props.get("before_text", "")
                    after = props.get("after_text", "")
                    if before:
                        lines.append(f'<p class="text-muted"><small>Before: {self._esc(before)}</small></p>')
                    if after:
                        lines.append(f'<p class="text-muted"><small>After: {self._esc(after)}</small></p>')
                    lines.append("</section>")

            elif ko_type == "json_ld":
                lines.append("<section class='ko-section'>")
                schema_type = props.get("schema_type", "Thing")
                data = props.get("data", {})
                lines.append(f"<h3>Schema: {self._esc(schema_type)}</h3>")
                if isinstance(data, dict):
                    lines.append("<table class='kv-props-table'><tbody>")
                    for k, v in data.items():
                        if isinstance(v, list):
                            v = ", ".join(str(x) for x in v[:5])
                            if len(v) > 200:
                                v = v[:200] + "..."
                        elif isinstance(v, dict):
                            v = str(v.get("name", v.get("@id", str(v))))
                        if v:
                            lines.append(f"<tr><td>{self._esc(k)}</td><td>{self._esc(str(v)[:300])}</td></tr>")
                    lines.append("</tbody></table>")
                lines.append("</section>")

        # Footer
        captured = capture_ref.get("captured_at", "")
        if captured:
            lines.append("<hr>")
            lines.append(f'<p class="text-muted"><em>Extracted by Recollect — {captured}</em></p>')

        lines.append("</div>")

        return "\n".join(lines)

    def _render_block(self, block: dict) -> str:
        """Renderē vienu satura bloku uz HTML."""
        btype = block.get("type", "")
        content = block.get("content", "")

        if btype == "heading":
            level = min(block.get("level", 2), 6)
            return f"<h{level}>{self._esc(content)}</h{level}>"

        if btype == "paragraph":
            return f"<p>{self._esc(content)}</p>"

        if btype == "image":
            src = block.get("src", "")
            alt = block.get("alt", "")
            width = block.get("width")
            height = block.get("height")
            size = ""
            if width and height:
                size = f' width="{self._esc(str(width))}" height="{self._esc(str(height))}"'
            caption = block.get("caption", "")
            result = f'<p><img src="{self._esc(src)}" alt="{self._esc(alt)}" loading="lazy"{size}></p>'
            if caption:
                result += f'<figcaption>{self._esc(caption)}</figcaption>'
            return result

        if btype == "blockquote":
            return f"<blockquote><p>{self._esc(content)}</p></blockquote>"

        if btype == "code":
            lang = block.get("language", "")
            code = self._esc(content)
            if lang:
                return f'<pre class="language-{self._esc(lang)}"><code>{code}</code></pre>'
            return f"<pre><code>{code}</code></pre>"

        if btype == "hr":
            return "<hr>"

        if btype == "list_item":
            lt = block.get("list_type", "ul")
            depth = block.get("depth", 0)
            indent = "  " * depth
            marker = "-" if lt == "ul" else "1."
            return f"{indent}{marker} {self._esc(content)}"

        if btype == "table":
            rows = block.get("rows", [])
            if not rows:
                return ""
            result = ["<table><tbody>"]
            for i, row in enumerate(rows):
                cells = [f"<td>{self._esc(c)}</td>" for c in row]
                result.append(f"<tr>{''.join(cells)}</tr>")
            result.append("</tbody></table>")
            return "\n".join(result)

        return ""

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