import json

from app.services.memory_retrieval import _parse_streamed_synthesis, _StreamingBlockParser, _StreamingDisplayParser, _validated_synthesis_block, _repair_missing_table_fallback


def parse(block):
    raw = '\n'.join(['VIEW: compare', 'TITLE: Example', 'SUMMARY: Summary [EVIDENCE: a]',
                     'SECTION: Details', 'CONTENT: Explanation [EVIDENCE: a]',
                     'EVIDENCE: a,b', 'BLOCK: ' + json.dumps(block)])
    return _parse_streamed_synthesis(raw, {'a', 'b'}, 'test')['sections'][0]


def test_structured_lists_and_tables_preserve_citations():
    item = {'text': 'A', 'evidence_ids': ['a']}
    for kind in ('bullets', 'numbered'):
        assert parse({'type': kind, 'items': [item]})['blocks'][0]['items'][0]['parts'][1] == {'evidence_id': 'a'}
    table = parse({'type': 'table', 'columns': ['A', 'B'], 'rows': [[item, {'missing': True}]]})['blocks'][0]
    assert table['rows'][0][1] == {'missing': True}


def test_invalid_blocks_leave_prose_fallback():
    section = parse({'type': 'bullets', 'items': [{'text': 'Invented', 'evidence_ids': ['unknown']}]})
    assert section['blocks'] == []
    assert section['content'] == 'Explanation'
    assert parse({'type': 'table', 'columns': ['A', 'B'], 'rows': [[{'missing': True}]]})['blocks'] == []
    assert parse({'type': [], 'items': []})['blocks'] == []


def test_streamed_blocks_wait_for_complete_validated_line():
    parser = _StreamingBlockParser({'a'})
    block = json.dumps({'type': 'bullets', 'items': [{'text': 'Supported', 'evidence_ids': ['a']}]})
    assert parser.feed('SECTION: Details\nEVIDENCE: a\nBLOCK: ' + block[:12]) == []
    events = parser.feed(block[12:] + '\nSECTION: Next\n')
    assert events[0]['section'] == 0
    assert events[0]['block']['items'][0]['parts'][1] == {'evidence_id': 'a'}
    assert parser.feed('BLOCK: ' + block + '\n') == []  # no evidence in this section
    assert parser.feed('EVIDENCE: a\nBLOCK: ' + block, final=True)[0]['section'] == 1


def test_streamed_malformed_block_does_not_expose_text():
    parser = _StreamingBlockParser({'a'})
    assert parser.feed('SECTION: Details\nEVIDENCE: a\nBLOCK: {"type":"bullets","items":[{"text":"bad","evidence_ids":["unknown"]}]}\n') == []


def test_display_parser_handles_field_names_and_lines_split_at_every_character():
    parser = _StreamingDisplayParser()
    raw = 'TITLE: Hidden\nSUMMARY: Overview\nSECTION: Details\nCONTENT: Fallback\nEVIDENCE: a\nBLOCK: {"secret":true}\n'
    result = ''.join(parser.feed(char) for char in raw)
    assert result == 'Overview\n\nDetails\nFallback'


def test_comparison_labels_from_question_are_not_cited_as_evidence():
    question = 'Salīdzini Obsidian, Notion un Logseq'
    block = {'type': 'table', 'columns': ['Tool', 'Sync'], 'rows': [
        [{'query_label': 'Obsidian'}, {'missing': True}],
        [{'query_label': 'Notion'}, {'missing': True}],
        [{'query_label': 'Logseq'}, {'text': 'File sync', 'evidence_ids': ['a']}],
    ]}
    encoded = json.dumps(block)
    final = _validated_synthesis_block(encoded, {'a'}, question)
    assert [row[0]['parts'][0]['text'] for row in final['rows']] == ['Obsidian', 'Notion', 'Logseq']
    assert final['rows'][1][1] == {'missing': True}
    assert final['rows'][2][1]['parts'][1] == {'evidence_id': 'a'}
    stream = _StreamingBlockParser({'a'}, question)
    events = stream.feed('SECTION: Comparison\nEVIDENCE: a\nBLOCK: ' + encoded + '\n')
    assert events[0]['block'] == final
    raw = '\n'.join(['VIEW: compare', 'TITLE: Example', 'SUMMARY: Supported [EVIDENCE: a]',
                     'SECTION: Comparison', 'CONTENT: Fallback [EVIDENCE: a]',
                     'EVIDENCE: a', 'BLOCK: ' + encoded])
    assert _parse_streamed_synthesis(raw, {'a'}, 'test', question)['sections'][0]['blocks'][0] == final


def test_query_labels_cannot_be_invented_or_used_as_facts():
    def validate(rows, query='Compare Obsidian and Notion'):
        return _validated_synthesis_block(json.dumps({'type':'table', 'columns':['Tool','Feature'], 'rows':rows}), {'a'}, query)
    assert validate([[{'query_label':'Obsidian'}, {'query_label':'Notion'}]]) is None
    assert validate([[{'query_label':'Logseq'}, {'missing':True}]]) is None
    assert validate([[{'query_label':'Obsidian', 'missing':True}, {'missing':True}]]) is None
    assert validate([[{'query_label':'Ob'}, {'missing':True}]]) is None


def test_failed_table_reference_becomes_cited_excerpts_not_an_empty_promise():
    raw = '\n'.join(['VIEW: compare', 'TITLE: Apps', 'SUMMARY: Overview [EVIDENCE: a]',
                     'SECTION: Apps', 'CONTENT: Skatiet tabulu; nepietiekami pamatotas īpašības nav norādītas.',
                     'EVIDENCE: a', 'BLOCK: {invalid json}'])
    result = _parse_streamed_synthesis(raw, {'a'}, 'test', 'salīdzini visas lietotnes')
    _repair_missing_table_fallback(result, [
        {'id': 'a', 'content': 'Logseq offers daily notes.'},
        {'id': 'b', 'content': 'Uncited source must not appear.'},
    ])
    section = result['sections'][0]
    assert 'could not be displayed' in section['content']
    assert 'Logseq offers daily notes.' in section['content']
    assert 'Uncited source' not in section['content']
    assert {'evidence_id': 'a'} in section['content_parts']
