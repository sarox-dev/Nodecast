"""
HTML Tools — ģeneriski rīki HTML parsēšanai.

Funkcijas darbam ar JavaScript JSON objektiem, JSON-LD un meta tagiem HTML lapās.
Visas funkcijas ir neatkarīgas no konkrētas vietnes — izmantojamas jebkurā extractorā.
"""

import json
import re
from typing import Any


def find_json_var(html: str, var_name: str) -> dict | None:
    """
    Atrod JavaScript mainīgā vērtību HTML un atgriež to kā dict.

    Meklē `var_name = {...};` vai `var_name = {...}` HTML saturā.
    Balansē `{}` iekavas, lai atrastu korektu JSON robežu.

    Args:
        html: Pilns HTML saturs
        var_name: JavaScript mainīgā nosaukums (e.g. 'ytInitialPlayerResponse')

    Returns:
        Dict ja atrasts un izdevās parsēt, None ja nav
    """
    if not html:
        return None

    # Atrodam mainīgā definīciju: var_name =  vai var_name=
    pattern = re.escape(var_name) + r"\s*=\s*"
    match = re.search(pattern, html)
    if not match:
        return None

    start = match.end()
    # Atrodam pirmo {
    brace_start = html.find("{", start)
    if brace_start == -1:
        return None

    # Balansējam iekavas
    depth = 0
    in_string = False
    escape = False
    for i in range(brace_start, len(html)):
        ch = html[i]

        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue

        if not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[brace_start : i + 1])
                    except json.JSONDecodeError:
                        return None

    return None


def find_json_vars(html: str) -> dict[str, dict]:
    """
    Atrod VISUS JavaScript objektus HTML (ietin mainīgā vērtībā).

    Meklē `var XXX = {...}` vai `window.XXX = {...}` patternus.

    Returns:
        Dict ar mainīgo nosaukumiem kā atslēgām un to vērtībām
    """
    results = {}
    if not html:
        return results

    # Meklējam `var XXX = {` vai `window.XXX = {` vai `XXX = {`
    pattern = re.compile(
        r'(?:var\s+|window\.|const\s+|let\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(\{)',
    )
    for match in pattern.finditer(html):
        var_name = match.group(1)
        # Izlaižam jau atrastos un acīmredzami ne-JSON mainīgos
        if var_name in results or var_name in (
            "function", "if", "else", "return", "true", "false",
            "null", "undefined", "this", "typeof",
        ):
            continue

        data = find_json_var(html, var_name)
        if data is not None:
            results[var_name] = data

    return results


def find_json_ld(html: str) -> list[dict]:
    """
    Atrod visus JSON-LD <script type='application/ld+json'> blokus HTML.

    Returns:
        Saraksts ar visiem atrastajiem JSON-LD objektiem
    """
    results: list[dict] = []
    if not html:
        return results

    pattern = re.compile(
        r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                results.append(data)
            elif isinstance(data, list):
                results.extend(data)
        except json.JSONDecodeError:
            continue

    return results


def find_meta_tags(html: str) -> dict[str, str]:
    """
    Atrod visus meta tagus HTML un atgriež tos kā plakanu dict.

    Atbalsta:
    - <meta name="..." content="...">
    - <meta property="..." content="...">
    - <meta itemprop="..." content="...">
    - <meta charset="...">

    Returns:
        Dict ar name/property kā atslēgu un content kā vērtību
    """
    result: dict[str, str] = {}
    if not html:
        return result

    # Standard meta tags: name/property + content
    for attr_name in ("name", "property", "itemprop"):
        pattern = re.compile(
            rf'<meta\s+{attr_name}=["\']([^"\']+)["\'][^>]*?\s+content=["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        for match in pattern.finditer(html):
            key = match.group(1).lower()
            value = match.group(2)
            if key and value and key not in result:
                result[key] = value

    # Reversed order: content before name/property
    pattern = re.compile(
        r'<meta\s+content=["\']([^"\']*)["\'][^>]*?\s+(?:name|property|itemprop)=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        key = match.group(2).lower()
        value = match.group(1)
        if key and value and key not in result:
            result[key] = value

    # charset
    charset_match = re.search(
        r'<meta\s+charset=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if charset_match:
        result["charset"] = charset_match.group(1)

    return result


def find_meta_tag(html: str, name: str) -> str:
    """
    Atrod vienu meta tagu pēc name/property.

    Args:
        html: HTML saturs
        name: Meta tag name/property (e.g. 'og:title', 'description')

    Returns:
        Content vērtība vai tukša string, ja nav atrasts
    """
    meta_tags = find_meta_tags(html)
    return meta_tags.get(name.lower(), "")


def extract_text_between(html: str, tag: str) -> str:
    """
    Izvelk tekstu starp HTML tagiem (vienkāršs regex).

    Piemērs: extract_text_between(html, 'title') -> "Page Title"

    Args:
        html: HTML saturs
        tag: Taga nosaukums (bez < >)

    Returns:
        Teksts starp <tag>...</tag> vai tukša string
    """
    if not html:
        return ""
    match = re.search(
        rf'<{tag}[^>]*>(.*?)</{tag}>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        # Remove any inner HTML tags
        text = re.sub(r'<[^>]+>', '', match.group(1))
        return text.strip()
    return ""
