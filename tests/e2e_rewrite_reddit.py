"""
Pārbauda URL rewriting — www.reddit.com → old.reddit.com
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.capture_package import CapturePackage, SourceInfo, Anchor
from app.services.extractor_pipeline import run_pipeline, extract_and_save


print("Testējam www.reddit.com ar URL rewriting...")
html = "<html><body><p>Loading shell</p></body></html>"  # Simulējam SPA shell

pkg = CapturePackage(
    capture_id="rewrite_test",
    source=SourceInfo(url="https://www.reddit.com/r/AiBuilders/comments/1uomau5/", title=""),
    anchor=Anchor(selected_text="AI advice about prompting"),
)

result = run_pipeline(pkg, html)
print(f"\nPipeline KnowledgeObjects: {len(result.knowledge_objects)}")
print(f"Rewritten URL: {pkg.source.url}")

for ko in result.knowledge_objects:
    print(f"  [{ko.type}] by={ko.extracted_by}")
    for k, v in list(ko.properties.items())[:3]:
        vs = str(v)[:80]
        print(f"    {k}: {vs}")

if not result.knowledge_objects:
    print("  (tukšs — URL rewriting nestrādāja vai HTML nav pieejams)")