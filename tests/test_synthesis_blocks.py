import json

from app.services.memory_retrieval import _parse_streamed_synthesis, _StreamingBlockParser, _StreamingDisplayParser


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
