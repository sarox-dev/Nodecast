"""Run with pytest after installing Playwright and its Chromium browser."""
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parent.parent


def test_escaped_metadata_remains_text_in_real_dom():
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for name in ["ui-utils.js", "atomic-view.js", "entity-view.js", "settings.js"]:
            source = (ROOT / "app/static/js" / name).read_text()
            start = source.index("function escapeHtml(")
            end = source.index("\n}", start) + 2
            page.evaluate("window.escapeHtml = " + source[start:end])
            result = page.evaluate("""() => {
                const input = 'Example " onmouseover="window.__xss=1';
                const node = document.createElement('div');
                node.innerHTML = '<a title="' + escapeHtml(input) + '">Source</a>';
                node.firstChild.dispatchEvent(new MouseEvent('mouseover'));
                return { title: node.firstChild.title,
                         handler: node.firstChild.getAttribute('onmouseover'),
                         executed: Boolean(window.__xss), input };
            }""")
            assert result["title"] == result["input"]
            assert result["handler"] is None
            assert not result["executed"]
        browser.close()
