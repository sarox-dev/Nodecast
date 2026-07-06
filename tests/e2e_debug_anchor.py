"""
Pārbauda ko pipeline atgriež www.reddit.com ar anchor.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.capture_package import CapturePackage, SourceInfo, Anchor
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


print("1. Testējam www.reddit.com (8KB shell) ar anchor...")
html = fetch_html("https://www.reddit.com/r/AiBuilders/comments/1uomau5/")
print(f"   HTML size: {len(html) if html else 0} bytes\n")

pkg = CapturePackage(
    source=SourceInfo(url="https://www.reddit.com/r/AiBuilders/comments/1uomau5/", title=""),
    anchor=Anchor(selected_text="AI advice is about prompting"),
)
result = run_pipeline(pkg, html)
print(f"Pipeline KnowledgeObjects: {len(result.knowledge_objects)}")
for ko in result.knowledge_objects:
    print(f"  [{ko.type}] by={ko.extracted_by} pos={ko.position}")
    for k, v in list(ko.properties.items())[:3]:
        vs = str(v)[:80]
        print(f"    {k}: {vs}")

print("\n==================\n")

print("2. Testējam old.reddit.com ar anchor...")
html2 = fetch_html("https://old.reddit.com/r/AiBuilders/comments/1uomau5/")
print(f"   HTML size: {len(html2) if html2 else 0} bytes\n")

pkg2 = CapturePackage(
    source=SourceInfo(url="https://old.reddit.com/r/AiBuilders/comments/1uomau5/", title=""),
    anchor=Anchor(selected_text="Most AI advice is about prompting"),
)
result2 = run_pipeline(pkg2, html2)
print(f"Pipeline KnowledgeObjects: {len(result2.knowledge_objects)}")
for ko in result2.knowledge_objects:
    print(f"  [{ko.type}] by={ko.extracted_by} pos={ko.position}")
    for k, v in list(ko.properties.items())[:3]:
        vs = str(v)[:80]
        print(f"    {k}: {vs}")