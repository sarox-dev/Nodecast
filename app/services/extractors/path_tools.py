"""
Path Tools — dot notation navigācija JSON struktūrās.

Atrisina ceļus kā 'videoDetails.title' vai 'contents[0].name'
pret jebkuru dict/list struktūru.
"""

from typing import Any


def resolve_path(data: Any, path: str) -> Any:
    """
    Atrisina dot notation ceļu pret JSON struktūru.

    Atbalsta:
    - Vienkāršus laukus: 'title', 'videoDetails.title'
    - Array indeksus: 'contents[0]', 'thumbnails[-1].url'
    - Jauktus: 'results.results.contents[0].videoPrimaryInfoRenderer.title'

    Args:
        data: Dict vai list (JSON struktūra)
        path: Dot notation ceļš (e.g. 'videoDetails.title')

    Returns:
        Vērtība ceļa galā, vai None ja ceļš neeksistē
    """
    if not data or not path:
        return None

    # Sadalam ceļu segmentos, apstrādājot iekavas
    segments = _parse_path(path)

    current = data
    for seg in segments:
        if current is None:
            return None

        if isinstance(seg, int):
            # Array indekss
            if not isinstance(current, (list, tuple)):
                return None
            try:
                current = current[seg]
            except IndexError:
                return None

        elif isinstance(seg, str):
            # Dict atslēga
            if isinstance(current, dict):
                current = current.get(seg)
            elif isinstance(current, (list, tuple)):
                # Mēģinām atrast objektu listā ar šo atslēgu
                # (YouTube struktūrās bieži)
                found = None
                for item in current:
                    if isinstance(item, dict) and seg in item:
                        found = item[seg]
                        break
                current = found
            else:
                return None
        else:
            return None

    return current


def resolve_paths(data: dict, paths: list[str]) -> dict:
    """
    Atrisina vairākus ceļus vienā dict struktūrā.

    Args:
        data: JSON struktūra
        paths: Saraksts ar ceļiem

    Returns:
        Dict ar tikai atrastajiem laukiem
    """
    result = {}
    for path in paths:
        value = resolve_path(data, path)
        if value is not None:
            result[path] = value
    return result


def _parse_path(path: str) -> list[str | int]:
    """
    Pārvērš dot notation ceļu segmentu sarakstā.

    "videoDetails.title" -> ["videoDetails", "title"]
    "contents[0].name" -> ["contents", 0, "name"]
    "thumbnails[-1].url" -> ["thumbnails", -1, "url"]

    Args:
        path: Dot notation ceļš

    Returns:
        Saraksts ar string un int segmentiem
    """
    segments: list[str | int] = []

    # Atdalām pa punktiem, bet saglabājam iekavas
    parts = re_split_dots(path)

    for part in parts:
        # Pārbaudam vai ir array indekss
        bracket_pos = part.find("[")
        if bracket_pos >= 0:
            # Pirms iekavas ir atslēga
            key = part[:bracket_pos]
            if key:
                segments.append(key)

            # Iekšā ir indekss
            inner = part[bracket_pos + 1 : part.find("]")]
            try:
                segments.append(int(inner))
            except ValueError:
                segments.append(inner)

            # Pēc iekavas var būt vēl teksts (reti, bet iespējams)
            after = part[part.find("]") + 1 :]
            if after and after.startswith("."):
                after = after[1:]
            if after:
                segments.append(after)
        else:
            segments.append(part)

    return segments


def re_split_dots(path: str) -> list[str]:
    """
    Sadala ceļu pa punktiem, bet nepa punktiem iekavās.

    "contents[0].name" -> ["contents[0]", "name"]
    "a.b[0].c" -> ["a", "b[0]", "c"]

    Args:
        path: Dot notation ceļš

    Returns:
        Saraksts ar ceļa daļām
    """
    parts: list[str] = []
    current = ""
    depth = 0

    for ch in path:
        if ch == "[":
            depth += 1
            current += ch
        elif ch == "]":
            depth -= 1
            current += ch
        elif ch == "." and depth == 0:
            if current:
                parts.append(current)
                current = ""
        else:
            current += ch

    if current:
        parts.append(current)

    return parts


def path_exists(data: Any, path: str) -> bool:
    """
    Pārbauda vai ceļš eksistē struktūrā (vērtība nav None).

    Args:
        data: JSON struktūra
        path: Dot notation ceļš

    Returns:
        True ja ceļš eksistē un vērtība nav None
    """
    return resolve_path(data, path) is not None


def get_first_existing(data_sources: dict[str, Any], paths: list[str]) -> Any:
    """
    Atgriež pirmo eksistējošo vērtību no saraksta ar ceļiem.

    Katrs ceļš ir formātā 'source_name.path.to.field'.
    data_sources satur avotus (json_var vārdus) kā atslēgas.

    Args:
        data_sources: Dict ar visiem izvilktajiem JSON avotiem
        paths: Saraksts ar 'source.path.to.field' ceļiem

    Returns:
        Pirmā atrastā vērtība vai None
    """
    for path in paths:
        # Atdalām avota nosaukumu (pirmais segments pirms punkta)
        dot_pos = path.find(".")
        if dot_pos < 0:
            # Tiešā atsauce uz avotu
            if path in data_sources:
                return data_sources[path]
            continue

        source_name = path[:dot_pos]
        field_path = path[dot_pos + 1:]

        source_data = data_sources.get(source_name)
        if source_data is None:
            continue

        value = resolve_path(source_data, field_path)
        if value is not None:
            return value

    return None