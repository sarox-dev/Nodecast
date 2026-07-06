"""
Testē Reddit pipeline ar reālu lapu.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.capture_package import CapturePackage, SourceInfo
from app.services.extractor_pipeline import run_pipeline


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

    print("1. Ielādēju Reddit...")
    html = fetch_html(url)
    if not html:
        print("FAIL")
        return
    print(f"   {len(html):,} bytes\n")

    pkg = CapturePackage(
        capture_id="reddit_test",
        source=SourceInfo(url=url, title=""),
    )

    print("2. Palaizam pipeline...")
    result = run_pipeline(pkg, html)
    print(f"   KnowledgeObjects: {len(result.knowledge_objects)}")
    print(f"   Warnings: {result.warnings}\n")

    if not result.knowledge_objects:
        print("   (tukšs!)")
        return

    for ko in result.knowledge_objects:
        print(f"\n[{ko.type}] (by: {ko.extracted_by}) conf={ko.confidence}")
        for k, v in ko.properties.items():
            if isinstance(v, str) and len(v) > 120:
                v = v[:120] + "..."
            print(f"  {k}: {v}")

    # Pārbaudam specifiskus laukus
    print(f"\n\n--- Kopsavilkums ---")
    types = [ko.type for ko in result.knowledge_objects]
    print(f"Tipi: {', '.join(sorted(set(types)))}")

    for ko in result.knowledge_objects:
        if ko.type == "reddit_post":
            print(f"Reddit post author: {ko.properties.get('author', 'N/A')}")
            print(f"Reddit post subreddit: {ko.properties.get('subreddit', 'N/A')}")
            print(f"Reddit post score: {ko.properties.get('score', 'N/A')}")
            print(f"Reddit post comments: {ko.properties.get('comments_count', 'N/A')}")


if __name__ == "__main__":
    main()