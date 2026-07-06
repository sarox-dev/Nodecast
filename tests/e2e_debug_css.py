"""
Debug CSS selector regex — pārbauda katru pattern atsevišķi.
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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


def test_selector(name, pattern, html):
    m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if m:
        print(f"  ✓ {name}")
        # Atrodam kontekstu ap match
        start = max(0, m.start() - 20)
        end = min(len(html), m.end() + 80)
        ctx = html[start:end].replace('\n', ' ')
        print(f"    Konteksts: ...{ctx}...")
    else:
        print(f"  ✗ {name}")


def test_css_extract(html, selector):
    """Tieša CSS extrakcija bez engine."""
    # Atritribūta izvilkšana
    attr = None
    if "@" in selector:
        selector, attr = selector.rsplit("@", 1)
        if not selector:
            selector = f"[{attr}]"

    # Tag
    tag_pattern = r'(div|span|a|p|h[1-6]|time|section|article|main|body|li|ul|ol|img|input|form|button|meta|link|script|style|td|th|tr|table|thead|tbody|blockquote|pre|code|figcaption|figure|dd|dl|dt|label|select|option|textarea)'

    class_name = None
    elem_id = None
    attrs = {}

    if "#" in selector:
        parts = selector.split("#", 1)
        selector = parts[0]
        elem_id = parts[1].split("[")[0].split(".")[0]

    if "." in selector and not selector.startswith("."):
        parts = selector.split(".", 1)
        selector = parts[0]
        class_name = parts[1].split("[")[0]
    elif selector.startswith("."):
        class_name = selector.split(".")[1].split("[")[0]
        selector = ""

    bracket_match = re.search(r'\[([^\]=]+)(?:=([^\]]*))?\]', selector)
    if bracket_match:
        attr_name = bracket_match.group(1)
        attr_value = bracket_match.group(2)
        if attr_value:
            attr_value = attr_value.strip("'\"")
        selector = selector[:bracket_match.start()]
        attrs[attr_name] = attr_value if attr_value else "*"

    if not selector:
        tag = tag_pattern
    else:
        tag = re.escape(selector)

    print(f"\nSelektors: '{selector}' class={class_name} id={elem_id} attrs={attrs} attr_extract={attr}")

    class_part = f' class="[^"]*\\b{re.escape(class_name)}\\b[^"]*"' if class_name else ""
    id_part = f' id="{re.escape(elem_id)}"' if elem_id else ""

    attr_parts = ""
    for aname, avalue in attrs.items():
        if avalue == "*":
            attr_parts += rf'[^>]*\s{re.escape(aname)}(?:\s|=|>)'
        else:
            aq = re.escape(avalue)
            attr_parts += rf'[^>]*\s{re.escape(aname)}=["\']{aq}["\']'

    if attr:
        pattern = rf'<{tag}{class_part}{id_part}{attr_parts}[^>]*\s{re.escape(attr)}=["\']([^"\']+)["\']'
    else:
        pattern = rf'<{tag}{class_part}{id_part}{attr_parts}[^>]*>(.*?)</{tag}>'

    print(f"  Pattern: {pattern[:120]}...")
    test_selector(f"regex match ({selector})", pattern, html)

    if not attr:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            text = re.sub(r'<[^>]+>', '', match.group(1))
            print(f"  Value: {text.strip()[:80]}")


def main():
    url = "https://old.reddit.com/r/AiBuilders/comments/1uomau5/i_spent_a_week_turning_claude_into_a_second_brain/"
    html = fetch_html(url)
    if not html:
        print("FAIL")
        return

    for sel in ["a.author", "a.author@href", ".score.unvoted",
                ".redditname a", "time.live-timestamp",
                "time.live-timestamp@datetime", "[data-author]"]:
        test_css_extract(html, sel)


if __name__ == "__main__":
    main()