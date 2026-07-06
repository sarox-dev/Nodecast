"""
Testē reālu YouTube video cauri pipeline.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.capture_package import CapturePackage, SourceInfo
from app.services.extractor_pipeline import run_pipeline


YT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def fetch_html(url: str) -> str | None:
    import subprocess, shutil
    curl = shutil.which("curl")
    if not curl:
        print("NAV curl")
        return None
    result = subprocess.run(
        [curl, "-sL", "--max-time", "15",
         "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
         url],
        capture_output=True, text=True, timeout=20,
    )
    return result.stdout if result.returncode == 0 else None


def main():
    print("1. Ielādēju YouTube...")
    html = fetch_html(YT_URL)
    if not html:
        print("FAIL: Nevarēja ielādēt")
        return
    print(f"   {len(html):,} bytes\n")

    pkg = CapturePackage(
        capture_id="yt_test_real",
        source=SourceInfo(url=YT_URL, title=""),
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
            if isinstance(v, str) and len(v) > 100:
                v = v[:100] + "..."
            print(f"  {k}: {v}")

    # Pārbaudam vai ir Python YouTubeExtractor
    from app.services.extractor_pipeline import get_registered_extractors
    print(f"\n\nReģistrētie extractori: {[e.name for e in get_registered_extractors()]}")


if __name__ == "__main__":
    main()
