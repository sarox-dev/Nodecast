"""
Analizē YouTube HTML — pārbauda vai atrod ytInitialPlayerResponse un citus datus.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.extractors.html_tools import find_json_var, find_json_ld, find_meta_tags
from app.services.extractors.path_tools import resolve_path


def fetch_html(url: str) -> str | None:
    import subprocess, shutil
    curl = shutil.which("curl")
    if not curl:
        return None
    result = subprocess.run(
        [curl, "-sL", "--max-time", "15",
         "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
         url],
        capture_output=True, text=True, timeout=20,
    )
    return result.stdout if result.returncode == 0 else None


def main():
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    print(f"Ielādēju: {url}")
    html = fetch_html(url)
    if not html:
        print("FAIL: Nevarēja ielādēt")
        return

    print(f"HTML izmērs: {len(html):,} bytes\n")

    # Meta tagi
    meta = find_meta_tags(html)
    print(f"Meta tagi: {len(meta)}")
    for k in ["og:title", "og:description", "og:video:tag", "author",
              "title", "description"]:
        if k in meta:
            print(f"  {k}: {meta[k][:80]}")

    # JSON-LD
    ld = find_json_ld(html)
    print(f"\nJSON-LD objekti: {len(ld)}")
    for obj in ld[:2]:
        print(f"  @type: {obj.get('@type', '?')}")
        if "name" in obj:
            print(f"  name: {obj['name'][:80]}")

    # Meklējam ytInitialPlayerResponse
    print("\nMeklēju 'ytInitialPlayerResponse'...")
    player = find_json_var(html, "ytInitialPlayerResponse")
    if player:
        print("  ATRATS!")
        vd = player.get("videoDetails", {})
        if vd:
            print(f"  videoId: {vd.get('videoId', 'N/A')}")
            print(f"  title: {vd.get('title', 'N/A')[:80]}")
            print(f"  author: {vd.get('author', 'N/A')}")
            print(f"  channelId: {vd.get('channelId', 'N/A')}")
            print(f"  description length: {len(vd.get('shortDescription', ''))}")
            print(f"  keywords: {vd.get('keywords', [])[:3]}")
        micro = player.get("microformat", {}).get("playerMicroformatRenderer", {})
        if micro:
            print(f"  publishDate: {micro.get('publishDate', 'N/A')}")
            print(f"  category: {micro.get('category', 'N/A')}")
    else:
        print("  NAV atrasts!")
        # Pārbaudam vai vārds vispār ir HTML
        if "ytInitialPlayerResponse" in html:
            print("  -> Teksts 'ytInitialPlayerResponse' IR HTML, bet find_json_var nevar atrast")
            # Atrodam pirmo 200 chars ap to
            idx = html.index("ytInitialPlayerResponse")
            print(f"  -> Konteksts: {html[max(0,idx-30):idx+80]}")
        else:
            print("  -> Teksts 'ytInitialPlayerResponse' NAV HTML")

    # Meklējam ytInitialData
    print("\nMeklēju 'ytInitialData'...")
    init = find_json_var(html, "ytInitialData")
    if init:
        print("  ATRATS!")
    else:
        print("  NAV atrasts!")
        if "ytInitialData" in html:
            print("  -> Teksts IR HTML, bet atrast nevar")

    # Meklējam citus iespējamos JSON mainīgos
    for var in ["__NEXT_DATA__", "__INITIAL_STATE__", "window.__INITIAL_STATE__",
                "ytcfg", "ytplayer.config"]:
        data = find_json_var(html, var)
        if data is not None:
            print(f"\nJSON '{var}': ATRATS! keys={list(data.keys())[:5]}")

    # Pārbaudam vai subtitle/transcript dati ir HTML
    for word in ["caption", "transcript", "subtitle", "subtitles",
                 "playerCaptionsTracklistRenderer", "publishDate"]:
        count = html.count(word)
        if count > 0:
            print(f"  '{word}' atrasts {count} reizes")

    # Meklējam description meta tagus
    desc = meta.get("og:description", meta.get("description", ""))
    print(f"\nDescription no meta: {desc[:100]}")


if __name__ == "__main__":
    main()
