"""Small, conservative evidence checks for explicit English/Latvian constraints.

These checks recognize literal exclusions and an explicit lack of a cloud
requirement. They do not infer product capabilities from a missing word, a title,
an AI summary or another source. Unrecognized semantics remain outside scope.
"""
from __future__ import annotations

import re
import unicodedata


_WITHOUT_CLOUD = re.compile(
    r'\b(?:without\s+(?:any\s+|a\s+|the\s+)?cloud(?:[-\s]+(?:dependency|dependencies|services?|servers?|storage|sync(?:hronization)?|account))?'
    r'|(?:with\s+)?no\s+cloud(?:[-\s]+(?:dependency|dependencies|services?|servers?|storage|sync(?:hronization)?|account))?'
    r'|bez\s+mākoņ(?:a|iem)(?:\s+(?:pakalpojumiem|servera|sinhronizācijas))?)\b', re.I,
)
_EXCLUDE = re.compile(
    r'\b(?:exclude|excluding|except|izņemot|izslēdzot)\s+'
    r'(?:"(?P<quoted>[^"\n]{1,100})"|“(?P<curly>[^”\n]{1,100})”|(?P<word>[\w.+/-]{1,100}))', re.I,
)
_CLOUD_NOUN = r'cloud(?:[-\s]+(?:sync(?:hronization)?|storage|services?|servers?|account|connection|dependency))?'
_SUPPORT = re.compile(
    rf'\b(?:(?:works?|runs?|operates?|functions?|can\s+be\s+used)\s+(?:entirely\s+|fully\s+)?without\s+(?:any\s+|a\s+|the\s+)?{_CLOUD_NOUN}'
    rf'|no\s+{_CLOUD_NOUN}\s+(?:is\s+)?(?:required|needed)'
    r'|no\s+cloud[-\s]+dependenc(?:y|ies)'
    rf'|(?:does\s+not|do\s+not|doesn[’\']t|don[’\']t|never)\s+(?:require|need|depend\s+on)\s+(?:an?\s+|the\s+)?{_CLOUD_NOUN}'
    rf'|{_CLOUD_NOUN}\s+(?:(?:is|are)\s+)?(?:optional|not\s+(?:required|needed|mandatory|necessary))'
    r'|(?:works?|runs?|operates?)\s+(?:entirely\s+|fully\s+|completely\s+)?offline'
    r'|(?:darbojas|strādā)\s+(?:pilnībā\s+)?bez\s+mākoņ\w*'
    r'|mākoņ\w*(?:\s+(?:sinhronizācij\w*|pakalpojum\w*|server\w*))?\s+(?:ir\s+)?(?:neobligāt\w*|nav\s+(?:obligāt\w*|nepieciešam\w*))'
    r'|darbojas\s+(?:pilnībā\s+)?bezsaistē)\b', re.I,
)
_REQUIRED = re.compile(
    rf'\b(?:(?:requires?|needs?|depends?\s+on|must\s+use)\s+(?:an?\s+|the\s+)?{_CLOUD_NOUN}'
    rf'|{_CLOUD_NOUN}\s+(?:(?:is|are)\s+)?(?:required|mandatory|necessary|not\s+optional)'
    r'|(?:nepieciešam\w*|vajag|jāizmanto)\s+(?:\w+\s+){0,2}mākoņ\w*'
    r'|mākoņ\w*(?:\s+(?:server\w*|pakalpojum\w*|sinhronizācij\w*))?\s+(?:ir\s+)?(?:obligāt\w*|nepieciešam\w*))\b', re.I,
)
_UNCERTAIN = re.compile(
    r'\?|\b(?:unclear|unknown|whether|might|maybe|perhaps|unless|if|apparently|allegedly|'
    r'neskaidr\w*|nezinām\w*|varbūt|iespējams|ja|nevar)\b|'
    r'\b(?:not|never|cannot|can[’\']t|won[’\']t|doesn[’\']t|does\s+not)\s+(?:\w+\s+){0,2}(?:work|run|operate|function|possible|documented|confirmed|proven)\b|'
    r'\bnot\s+without\b', re.I,
)


def _normalize(text: str) -> str:
    return unicodedata.normalize('NFC', text).casefold()


def parse_content_constraints(query: str) -> tuple[str, list[dict]]:
    """Separate a positive search topic from supported explicit constraints."""
    constraints, spans = [], []
    normalized = unicodedata.normalize('NFC', query)
    quotes = [match.span() for match in re.finditer(r'"[^"\n]*"|“[^”\n]*”', normalized)]
    def quoted(position):
        return any(start <= position < end for start, end in quotes)
    for match in _WITHOUT_CLOUD.finditer(normalized):
        if quoted(match.start()) or re.search(r'\bnot\s+$', normalized[:match.start()], re.I):
            continue
        constraints.append({'kind': 'cloud_not_required'})
        spans.append(match.span())
    for match in _EXCLUDE.finditer(normalized):
        if quoted(match.start()):
            continue
        value = next(value for value in match.group('quoted', 'curly', 'word') if value)
        constraints.append({'kind': 'exclude_text', 'value': value})
        spans.append(match.span())
    positive = list(normalized)
    for start, end in spans:
        positive[start:end] = ' ' * (end - start)
    search_text = ' '.join(''.join(positive).split()).strip(' ,;:')
    unique = list({tuple(sorted(item.items())): item for item in constraints}.values())
    return search_text or query, unique


def _cloud_status(text: str) -> str:
    # Only the visible, original excerpt can establish support. A question,
    # conditional claim or contradiction must not become a positive capability.
    text = _normalize(text[:700])
    if _UNCERTAIN.search(text):
        return 'unknown'
    matches = list(_SUPPORT.finditer(text))
    residual = list(text)
    for match in matches:
        residual[match.start():match.end()] = ' ' * (match.end() - match.start())
    if _REQUIRED.search(''.join(residual)):
        return 'contradicted'
    return 'supported' if matches else 'unknown'


def filter_content_constraints(items: list[dict], constraints: list[dict]) -> tuple[list[dict], dict]:
    counts = {'applied': len(constraints), 'supported': 0, 'contradicted': 0, 'unknown': 0}
    if not constraints:
        return items, counts
    accepted = []
    for item in items:
        statuses = []
        for constraint in constraints:
            if constraint['kind'] == 'cloud_not_required':
                statuses.append(_cloud_status(str(item.get('content') or '')))
            else:
                haystack = _normalize(' '.join(str(item.get(key) or '') for key in ('content', 'context_header', 'source_title')))
                value = re.escape(_normalize(constraint['value']))
                statuses.append('contradicted' if re.search(rf'(?<!\w){value}(?!\w)', haystack) else 'supported')
        status = 'contradicted' if 'contradicted' in statuses else 'unknown' if 'unknown' in statuses else 'supported'
        counts[status] += 1
        if status == 'supported':
            accepted.append(item)
    return accepted, counts
