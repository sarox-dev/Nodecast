"""
Debug: pārbauda vai Config Engine atrod Reddit config un CSS selektorus strādā.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.extractors.config_loader import get_config_for_url
from app.services.extractors.engine import ConfigEngine
from app.models.capture_package import CapturePackage, SourceInfo


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
    url = "https://old.reddit.com/r/AiBuilders/comments/1uomau5/i_spent_a_week_turning_claude_into_a_second_brain/"

    print(f"1. Vai config_loader atrod config URL: {url}")
    config = get_config_for_url(url)
    if config:
        print(f"   ATRATS: {config['name']} v{config['version']}")
    else:
        print("   NAV atrasts!")
        return
    
    print("\n2. Pārbaudam CSS selektorus uz reāla HTML...")
    html = fetch_html(url)
    if not html:
        print("   FAIL: nevar ielādēt HTML")
        return
    print(f"   HTML: {len(html):,} bytes")
    
    engine = ConfigEngine()
    
    # Testējam CSS selektorus
    tests = [
        "a.title",
        "a.author",
        ".score.unvoted",
        ".redditname a",
        "time.live-timestamp",
        "time.live-timestamp@datetime",
        "[data-author]",
        "[data-score]",
        "a.title@href",
    ]
    
    for sel in tests:
        result = engine._extract_css(html, sel)
        if result:
            print(f"   ✓ $css:{sel} → {result[:80]}")
        else:
            print(f"   ✗ $css:{sel} → (nav atrasts)")
    
    print("\n3. Palaizam engine.extract()...")
    pkg = CapturePackage(
        capture_id="reddit_debug",
        source=SourceInfo(url=url, title=""),
    )
    result = engine.extract(pkg, html)
    print(f"   KnowledgeObjects: {len(result.knowledge_objects)}")
    for ko in result.knowledge_objects:
        print(f"   [{ko.type}] extracted_by={ko.extracted_by}")
        for k, v in list(ko.properties.items())[:5]:
            if isinstance(v, str) and len(v) > 80:
                v = v[:80] + "..."
            print(f"     {k}: {v}")
    
    if not result.knowledge_objects:
        print("   (tukšs — nekas netika atrasts)")


if __name__ == "__main__":
    main()