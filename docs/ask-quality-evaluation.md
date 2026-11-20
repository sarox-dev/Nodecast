# Local Ask quality evaluation

Run from the Core repository root:

```sh
python3 scripts/evaluate_ask_quality.py --output /tmp/ask-quality.json
```

The evaluator creates and removes a temporary SQLite library with 27 synthetic
sources and 15 labeled questions. It calls `query_memory(synthesize=False)`,
including the real candidate search, evidence selection and packet limits. It
does not use the installed library, call AI/embedding providers, import webpages,
or evaluate generated answers. Database paths are restored even on failure.

The corpus covers source comparisons, exact errors, Latvian, mixed Chinese and
technical text, Unicode normalization, unavailable information, unconfirmed
personal intent, negation, rejected evidence, source crowding and token limits.

## Metric definitions

- Source Recall@5: expected sources found among the first five **distinct source
  IDs in the final packet**. Recall in packet uses all selected sources.
- Source Precision@5: relevant distinct sources divided by returned distinct
  sources, up to five. Repeated evidence from one source does not increase the
  denominator. Evidence precision/recall are reported separately.
- Recall is undefined for questions with no expected evidence; precision is
  undefined for empty results. JSON uses `null`, and macro averages omit those
  undefined values. Forbidden-source hits remain explicit for negative cases.
- Provenance integrity checks the seeded evidence ID, source ID, original URL
  and exact excerpt prefix. This is **not** semantic citation support or an
  evaluation of extraction from raw HTML.

## First measured improvement, 2026-11-20

Baseline: Core `db50531`. The before/after reports use the same corpus SHA-256,
`ab3d64138afb8a2e1bda472d0a0ad98c9ed67d99057ace91d0103898afd46b83`.

Two fragments from one source previously occupied slots before another source
could contribute its first fragment. Selection now takes one useful fragment
per source before filling with more evidence, retaining the existing two/four
fragment passes. Navigation-only text cannot gain a first slot just because it
comes from another source. The Recall cache version changes to avoid reusing
answers based on the previous packet selection.

| Measurement | Before | After |
| --- | ---: | ---: |
| Source Recall@5 | 0.8410 | 0.8576 |
| Source recall in the final packet | 0.8618 | 0.8889 |
| Source Precision@5 | 0.8750 | 0.8750 |
| Evidence recall in the packet | 0.8152 | 0.8152 |
| Evidence precision in the packet | 0.8472 | 0.8472 |
| Seeded provenance integrity | 100% | 100% |

The five-source crowding case improves from 4/5 to 5/5 sources; the eight-source
case improves from 7/8 to 8/8. The regression test fails with baseline selection
and passes with the new first-source pass. Reports preserve per-question results:
[before](reports/2026-11-20-ask-quality-before.json) and
[after](reports/2026-11-20-ask-quality-after.json).

## Remaining limits

These are small, deterministic synthetic measurements, not production quality or
user-retention evidence. They are not directly comparable to the older
multilingual baseline, which uses a different corpus, pipeline and source
precision denominator. Latencies are informational and have no CI threshold.

The Latvian question about English context-memory evidence still misses its
source without translation/semantic expansion. The negated cloud query still
returns a forbidden source. Navigation fragments can remain when there is room,
and the token-budget case intentionally cannot include every relevant excerpt.
This change repairs source crowding, not those semantic or relevance limits.
When a packet is full, this deliberately favors source breadth over a second
excerpt from its leading source. It does not improve candidate ranking or filter
irrelevant matches; that tradeoff still needs real beta questions.

The next quality step is an audited set of real beta questions and sources,
including explicit constraints and semantic citation support. Real-provider and
authenticated UI results must be recorded separately from this local baseline.
