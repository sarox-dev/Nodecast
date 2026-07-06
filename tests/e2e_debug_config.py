"""
Debug config_loader — kāpēc config netiek atrasts.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.extractors.config_loader import load_all_configs, get_config_for_url, clear_cache
from app.services.extractors.url_tools import match_domain, match_url_pattern

clear_cache()

# 1. Pārbaudam vai configs vispār ielādējas
configs = load_all_configs()
print(f"Ielādēti configi: {len(configs)}")
for c in configs:
    print(f"  - {c['name']} (v{c['version']}) match={c.get('match', {})}")

# 2. Pārbaudam url_tools
url = "https://old.reddit.com/r/AiBuilders/comments/1uomau5/"
print(f"\nURL: {url}")
print(f"match_domain(old.reddit.com, ['old.reddit.com']): {match_domain(url, ['old.reddit.com'])}")
print(f"match_url_pattern(/comments/: {match_url_pattern(url, ['/comments/'])}")

# 3. Pārbaudam get_config_for_url tieši
config = get_config_for_url(url)
print(f"\nget_config_for_url atgriež: {config}")

# 4. Meklējam pēc nosaukuma
from app.services.extractors.config_loader import get_config_by_name
reddit = get_config_by_name("reddit_post")
print(f"\nget_config_by_name('reddit_post'): {reddit}")

# 5. Pārbaudam config faila atrašanās vietu
import os as _os
configs_dir = _os.path.join(_os.path.dirname(__file__), "../app/services/extractors/configs/")
resolved = _os.path.abspath(configs_dir)
print(f"\nConfigs dir: {resolved}")
print(f"Eksistē: {_os.path.isdir(resolved)}")
if _os.path.isdir(resolved):
    for f in sorted(_os.listdir(resolved)):
        print(f"  {f}")
        if f.endswith('.yaml'):
            with open(_os.path.join(resolved, f)) as fh:
                import yaml
                data = yaml.safe_load(fh)
                print(f"    name: {data.get('name', 'MISSING!')}")