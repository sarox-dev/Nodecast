"""
Analizē Reddit HTML — lai saprastu post struktūru un izveidotu configu.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.extractors.html_tools import find_json_var, find_json_ld, find_meta_tags


def fetch_html(url: str) -> str | None:
    import subprocess, shutil
    curl = shutil.which("curl")
    if not curl:
        return None
    result = subprocess.run(
        [curl, "-sL", "--max-time", "15",
         "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
         url],
        capture_output=True, text=True, timeout=20,
    )
    return result.stdout if result.returncode == 0 else None


def main():
    # Divas Reddit versijas
    urls = [
        ("old.reddit.com", "https://old.reddit.com/r/AiBuilders/comments/1uomau5/i_spent_a_week_turning_claude_into_a_second_brain/"),
        ("www.reddit.com", "https://www.reddit.com/r/AiBuilders/comments/1uomau5/i_spent_a_week_turning_claude_into_a_second_brain/"),
    ]

    for name, url in urls:
        print(f"\n{'='*60}")
        print(f"REDDIT: {name}")
        print(f"{'='*60}")
        html = fetch_html(url)
        if not html:
            print("  FAIL: Nevarēja ielādēt")
            continue

        print(f"  HTML izmērs: {len(html):,} bytes")

        # Meta tagi
        meta = find_meta_tags(html)
        print(f"  Meta tagi: {len(meta)}")
        for k in ["og:title", "og:description", "og:site_name", "description", "author"]:
            if k in meta:
                print(f"    {k}: {meta[k][:100]}")

        # JSON-LD
        ld = find_json_ld(html)
        print(f"  JSON-LD: {len(ld)}")
        for obj in ld[:2]:
            print(f"    @type: {obj.get('@type', '?')}")
            for k in ["name", "headline", "description", "author", "datePublished"]:
                if k in obj:
                    v = obj[k]
                    if isinstance(v, str):
                        print(f"    {k}: {v[:80]}")
                    elif isinstance(v, dict):
                        print(f"    {k}: (dict) {v.get('name', '?')}")

        # Meklējam JSON mainīgos
        for var in ["__r", "window.__r", "redditInitialState", "r"]:
            data = find_json_var(html, var)
            if data is not None:
                print(f"  JSON var '{var}': keys={list(data.keys())[:8]}")

        # Meklējam post title un text HTML struktūrā
        # old.reddit specifiski
        if "class=\"title\"" in html or "class=\"usertext-body\"" in html:
            import re
            titles = re.findall(r'<a[^>]*class="title"[^>]*>(.*?)</a>', html, re.DOTALL)
            if titles:
                print(f"  Post title (HTML): {titles[0][:100]}")
            bodies = re.findall(r'<div[^>]*class="usertext-body"[^>]*>(.*?)</div>', html, re.DOTALL)
            if bodies:
                clean = re.sub(r'<[^>]+>', '', bodies[0]).strip()
                print(f"  Post body (HTML): {clean[:200]}")

        # Pārbaudam vai www.reddit ir JSON dati
        if name == "www.reddit.com":
            # Meklējam specifiskus datus
            for key in ["postId", "title", "selftext", "author"]:
                count = html.count(key)
                if count > 0:
                    print(f"  Atslēga '{key}' atrasta {count} reizes")


if __name__ == "__main__":
    main()