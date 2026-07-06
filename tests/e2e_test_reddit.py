"""
End-to-end tests — reālas lapas cauri visam pipeline.

Pārbauda:
1. Config Engine (ja ir config)
2. Python extractori
3. GenericHtmlExtractor (fallback)

Lietošana:
    source .venv/bin/activate
    python tests/e2e_test_reddit.py
"""

import json
import sys
import os

# Pievienojam projekta sakni path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.capture_package import CapturePackage, SourceInfo
from app.services.extractor_pipeline import run_pipeline


# Reddit post URL
REDDIT_URL = "https://old.reddit.com/r/AiBuilders/comments/1uomau5/i_spent_a_week_turning_claude_into_a_second_brain/"


def fetch_page_html(url: str) -> str | None:
    """Ielādē lapas HTML ar curl."""
    import subprocess
    import shutil

    curl_path = shutil.which("curl")
    if not curl_path:
        print("ERROR: curl nav atrasts. Installē: dnf install curl")
        return None

    result = subprocess.run(
        [curl_path, "-sL",
         "--max-time", "15",
         "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
         url],
        capture_output=True, text=True, timeout=20,
    )

    if result.returncode != 0 or not result.stdout:
        print(f"ERROR: curl failed (exit={result.returncode})")
        return None

    html = result.stdout
    print(f"  HTML size: {len(html):,} bytes")
    return html


def print_result(result):
    """Izvada pipeline rezultātu cilvēklasāmā formātā."""
    from app.services.extractors.html_tools import find_json_ld, find_meta_tags, find_meta_tag

    kos = result.knowledge_objects

    print(f"\n{'='*60}")
    print(f"PIPELINE REZULTĀTS")
    print(f"{'='*60}")
    print(f"  KnowledgeObjects: {len(kos)}")
    print(f"  Confidence:       {result.confidence}")
    print(f"  Warnings:         {len(result.warnings)}")
    for w in result.warnings:
        print(f"    ⚠ {w}")
    print()

    if kos:
        tips = {}
        for ko in kos:
            tips[ko.type] = tips.get(ko.type, 0) + 1
        print("  Tips:")
        for t, c in sorted(tips.items(), key=lambda x: -x[1]):
            print(f"    {t}: {c}")
        print()

        # Izvadam detalizēti interesantākos objektus
        for ko in kos:
            if ko.type in ("metadata", "article", "video"):
                print(f"  [{ko.type}] (extracted_by: {ko.extracted_by})")
                for k, v in ko.properties.items():
                    if isinstance(v, str) and len(v) > 120:
                        v = v[:120] + "..."
                    print(f"    {k}: {v}")
                print()
    else:
        print("  (tukšs — nekas netika atrasts)")
        print()


def check_reddit_html(html: str):
    """Pārbauda vai Reddit HTML satur izmantojamus datus."""
    from app.services.extractors.html_tools import find_json_var, find_json_ld, find_meta_tags

    print(f"\n{'='*60}")
    print(f"REDDIT HTML ANALĪZE")
    print(f"{'='*60}")

    # Meta tagi
    meta = find_meta_tags(html)
    title = meta.get("og:title", meta.get("title", "(nav atrasts)"))
    print(f"  Title: {title[:100]}")
    print(f"  Meta tagi: {len(meta)}")

    # JSON-LD
    ld = find_json_ld(html)
    if ld:
        types = [o.get("@type", "?") for o in ld]
        print(f"  JSON-LD objekti: {len(ld)} — tipi: {types[:5]}")
    else:
        print(f"  JSON-LD: nav atrasts")

    # Meklējam Reddit specifiskus JSON objektus
    for var_name in ["__r", "__data", "window.__r", "post", "redditInitialState"]:
        data = find_json_var(html, var_name)
        if data is not None:
            print(f"  JSON var '{var_name}': {type(data).__name__}, keys: {list(data.keys())[:10]}")

    print()


def main():
    print("=" * 60)
    print("END-TO-END TEST: Reddit post")
    print("=" * 60)
    print(f"\nURL: {REDDIT_URL}")
    print()

    # 1. Ielādējam HTML no Reddit
    print("1. Ielādējam lapu...")
    html = fetch_page_html(REDDIT_URL)
    if not html:
        print("FAIL: Nevarēja ielādēt lapu")
        sys.exit(1)

    # 2. Analizējam HTML saturu
    print("\n2. Analizējam HTML...")
    check_reddit_html(html)

    # 3. Veidojam CapturePackage
    print("3. Veidojam CapturePackage...")
    package = CapturePackage(
        capture_id="e2e_reddit_test",
        source=SourceInfo(url=REDDIT_URL, title=""),
    )

    # 4. Palaizam extractor pipeline
    print("4. Palaizam extractor pipeline...")
    result = run_pipeline(package, html)

    # 5. Izvadam rezultātu
    print("\n5. Rezultāts:")
    print_result(result)

    # 6. Kopsavilkums
    print(f"{'='*60}")
    print(f"KOPSAVILKUMS")
    print(f"{'='*60}")
    if result.knowledge_objects:
        print(f"  ✓ Pipeline atgrieza {len(result.knowledge_objects)} KnowledgeObjects")
        types = set(ko.type for ko in result.knowledge_objects)
        print(f"  ✓ Tipi: {', '.join(sorted(types))}")

        # Pārbaudam vai ir metadata
        if any(ko.type == "metadata" for ko in result.knowledge_objects):
            print(f"  ✓ Metadata — atrasts")
        if any(ko.type == "article" for ko in result.knowledge_objects):
            print(f"  ✓ Article — atrasts")
        if any(ko.type == "heading" for ko in result.knowledge_objects):
            print(f"  ✓ Headings — atrasti")
        if any(ko.type == "link" for ko in result.knowledge_objects):
            print(f"  ✓ Links — atrasti")
    else:
        print(f"  ✗ Pipeline neko neatgrieza")

    print()


if __name__ == "__main__":
    main()