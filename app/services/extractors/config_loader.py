"""
Config Loader — ielādē un kešo extractor konfigurācijas no YAML failiem.

Atrod visus .yaml failus configs/ direktorijā, validē to struktūru
un atgriež kā dicts.
"""

import os
from typing import Any

import yaml


# Noklusējuma configu direktorija (relatīvā pret šo failu)
_DEFAULT_CONFIGS_DIR = os.path.join(os.path.dirname(__file__), "configs")

# Kešs — ielādētie configi (lai nelasītu failus katru reizi)
_config_cache: list[dict] | None = None
_config_dir: str = _DEFAULT_CONFIGS_DIR


def set_config_dir(path: str):
    """Nomaina configu direktoriju (lietderīgi testiem)."""
    global _config_dir, _config_cache
    _config_dir = path
    _config_cache = None


def load_all_configs() -> list[dict]:
    """
    Ielādē visas extractor konfigurācijas no direktorijas.

    Rezultāti tiek kešoti — ja faili nav mainījušies,
    nākamais izsaukums atgriež kešētos datus.

    Returns:
        Saraksts ar validētiem config dicts
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    configs: list[dict] = []
    config_dir = _config_dir

    if not os.path.isdir(config_dir):
        return configs

    for filename in sorted(os.listdir(config_dir)):
        if not filename.endswith((".yaml", ".yml")):
            continue

        filepath = os.path.join(config_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse config {filename}: {e}")
            continue
        except Exception as e:
            print(f"Warning: Failed to read config {filename}: {e}")
            continue

        if not isinstance(data, dict):
            print(f"Warning: Config {filename} is not a dict, skipping")
            continue

        validation_error = validate_config(data)
        if validation_error:
            print(f"Warning: Config {filename} is invalid: {validation_error}")
            continue

        data.setdefault("_filename", filename)
        configs.append(data)

    _config_cache = configs
    return configs


def clear_cache():
    """Notīra kešu (lietderīgi testiem)."""
    global _config_cache
    _config_cache = None


def validate_config(config: dict) -> str | None:
    """
    Validē extractor konfigurācijas struktūru.

    Minimālās prasības:
    - 'name' (string, required)
    - 'version' (int, required)
    - 'match' (dict, required)
    - 'match.domains' vai 'match.patterns' (vismaz viens)
    - 'sources' (list, optional)
    - 'objects' (list, required) — KnowledgeObject definīcijas

    Returns:
        None ja viss ok, string ar kļūdu ja nav
    """
    if not isinstance(config, dict):
        return "Config is not a dict"

    name = config.get("name")
    if not name or not isinstance(name, str):
        return "Missing or invalid 'name' (required string)"

    version = config.get("version")
    if not isinstance(version, (int, float)):
        return "Missing or invalid 'version' (required number)"

    match = config.get("match")
    if not isinstance(match, dict):
        return "Missing 'match' section (required dict)"

    if "domains" not in match and "patterns" not in match:
        return "Match section must have 'domains' or 'patterns'"

    sources = config.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            return "'sources' must be a list"
        for src in sources:
            if not isinstance(src, dict):
                return "Each source must be a dict"
            if "type" not in src:
                return "Each source must have a 'type'"

    objects = config.get("objects")
    if not isinstance(objects, list) or len(objects) == 0:
        return "'objects' must be a non-empty list"

    for obj in objects:
        if not isinstance(obj, dict):
            return "Each object definition must be a dict"
        if "type" not in obj:
            return "Each object definition must have a 'type'"
        if "fields" not in obj:
            return f"Object '{obj.get('type', '?')}' must have 'fields'"

    return None


def get_config_for_url(url: str) -> dict | None:
    """
    Atrod piemērotāko konfigurāciju konkrētam URL.

    Salīdzina URL ar katra config 'match' noteikumiem.
    Prioritāte: specifiskākais patterns wins.

    Args:
        url: Pilns URL

    Returns:
        Config dict vai None ja nav atbilstošas konfigurācijas
    """
    from .url_tools import match_domain, match_url_pattern

    if not url:
        return None

    configs = load_all_configs()
    best_match = None
    best_specificity = 0

    for config in configs:
        match_section = config.get("match", {})
        domains = match_section.get("domains", [])
        patterns = match_section.get("patterns", [])

        # Pārbaudam domēnu
        if domains and not match_domain(url, domains):
            continue

        # Pārbaudam patternus
        if patterns and not match_url_pattern(url, patterns):
            continue

        # Aprēķinām specifitāti — jo vairāk noteikumu, jo specifiskāks
        specificity = len(domains) + len(patterns)
        if specificity > best_specificity:
            best_specificity = specificity
            best_match = config

    return best_match


def get_config_by_name(name: str) -> dict | None:
    """Atrod konfigurāciju pēc nosaukuma."""
    configs = load_all_configs()
    for config in configs:
        if config.get("name") == name:
            return config
    return None
