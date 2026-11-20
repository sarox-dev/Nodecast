#!/usr/bin/env python3
"""Measure actual v2 retrieval with fixed synthetic planner responses, never AI."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import ask_search_plan, database, memory_retrieval
from scripts.evaluate_ask_quality import isolated_database, load_corpus, score_packet, _mean

CORPUS = ROOT / 'tests/fixtures/ask_expansion_corpus.json'


def evaluate_expansion(corpus):
    with isolated_database():
        uid = database.create_user_in_db('expansion-eval', 'synthetic-not-a-login-hash')
        keys, originals = {}, {}
        for source in corpus['captures']:
            url = 'https://example.invalid/' + source['id']
            database.insert_capture_ref(uid, source['id'], 'snippet', url, source['title'], 'example.invalid', '', '', [], '', '')
            for key, text in source['evidence']:
                aid = database.insert_atomic(uid, 'text', text, source_id=source['id'], context_header=source['title'])
                keys[key] = aid
                originals[aid] = {'key': key, 'source_id': source['id'], 'url': url, 'text': text}
        rows = []
        for case in corpus['queries']:
            planner_calls = []
            def planner(user_id, provider, model, messages, **_options):
                assert user_id == uid
                payload = json.loads(messages[1]['content'])
                assert payload == {'query': case['query']}
                planner_calls.append(True)
                return json.dumps({'queries': case['planner_queries']}, ensure_ascii=False)
            with patch.object(memory_retrieval, 'get_ai_assignment_for_feature', return_value={'provider_id': 'synthetic', 'model': 'fixed-response'}), \
                 patch.object(memory_retrieval, 'get_ai_provider', return_value={'id': 'synthetic'}), \
                 patch.object(ask_search_plan, 'call_provider_model', side_effect=planner), \
                 patch.object(memory_retrieval, 'stream_provider_model', return_value=iter(())):
                events = list(memory_retrieval.stream_memory_query_v2(uid, case['query'], diagnostics=True))
            result = events[-1]['data']['result']
            local = next(event['data']['result'] for event in events if event['event'] == 'evidence.selected')
            scored = score_packet(result['items'], case['expected_sources'], [keys[key] for key in case['expected']], originals)
            rows.append({
                'id': case['id'], 'query': case['query'], 'kind': case['kind'],
                'expected_sources': case['expected_sources'], **scored,
                'actual_evidence_keys': [originals[item['id']]['key'] for item in result['items']],
                'initial_local_sources': list(dict.fromkeys(item['source_id'] for item in local['items'])),
                'planner_calls': len(planner_calls), 'planner_status': result['diagnostics']['planner_status'],
                'performed_queries': [event['data']['query'] for event in events if event['event'] == 'search.performed'],
                'forbidden_source_hits': sorted(set(scored['actual_sources']) & set(case['forbidden_sources'])),
            })
        metrics = {key: _mean([row[key] for row in rows]) for key in ('source_recall_at_5', 'source_recall_in_packet', 'source_precision_at_5', 'evidence_recall_in_packet', 'evidence_precision_in_packet')}
        metrics['provenance_integrity'] = all(row['provenance_integrity'] for row in rows)
        metrics['queries_with_forbidden_sources'] = sum(bool(row['forbidden_source_hits']) for row in rows)
        return {
            'corpus_version': corpus['version'],
            'corpus_sha256': hashlib.sha256(json.dumps(corpus, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            'planner_sha256': hashlib.sha256((ROOT / 'app/services/ask_search_plan.py').read_bytes()).hexdigest(),
            'pipeline': 'stream_memory_query_v2 with real plan validation and local candidate/constraint/packet selection',
            'scope': 'Fixed synthetic planner replies; no external AI, generated-answer or production quality evaluation. Initial local evidence remains separately reported.',
            'captures': len(corpus['captures']), 'queries': len(rows), 'metrics': metrics, 'results': rows,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=CORPUS)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(evaluate_expansion(load_corpus(args.corpus)), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
