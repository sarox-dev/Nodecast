# Guarded Ask query translation

Optional query expansion uses the existing assigned Recall provider. It does not
install a model or add an embedding/index pipeline. The v2 UI still receives
local evidence before the planner runs. The original question is always kept.

## Conditions and technical terms

Recognized [content conditions](ask-constraints.md) are separated from the search
topic. The positive topic can be translated even when the question contains
`bez mākoņa`, `without cloud`, or a literal exclusion. Every merged evidence
candidate must still pass the **original** local conditions. A translated query
is never a replacement for those conditions or a source of product facts.

Exact quoted/code-like topics, numeric conditions and unsupported recognized
negation remain on the guarded original-only path. An exclusion's quoted value
is handled as a condition, not as an exact quoted positive topic. An alternative
cannot add a new recognized condition or unsupported sensitive syntax.

Alternatives must preserve technical tokens, all-cap acronyms and internal-cap
identifiers from the positive topic, such as `llama.cpp`, `KV`, `SQLite` and `WAL`.
Additional search matches must also contain these anchors in their original text
or indexed context header. This prevents a relaxed OR match for a translated
word such as `concurrent` from adding an unrelated PostgreSQL source to a SQLite
question. This extra check does not remove the original local search results.
Ordinary title-case words are not automatically classified as named entities.

The existing limits remain: up to three alternatives, 200 characters per query,
4096 characters in the planner reply, an 8-second provider-call timeout and local
user-scoped searches. The planner receives only the bounded original question,
not saved source text. Answer synthesis separately receives its selected evidence
under the existing provider configuration. Invalid plans/failures retain local
results. There is no iterative tool loop.

## API behavior

JSON, legacy stream and v2 stream all use the same content checks and may expand
search when AI synthesis is enabled, `cross_language=true`, and mode is not `fast`.
`cross_language=false` or `mode=fast` skips this query-planning call. It does not
change separately configured embedding-provider settings. `synthesize=false`
skips both query-planning and answer-model calls, including in the legacy stream.
Without an assigned Recall provider, local results continue to work.

The Recall cache version is `recall-stream-v16-guarded-query-expansion`. Source
text, source IDs and URLs remain unchanged; only selected derived results change.

## Reproducible synthetic measurements

```sh
python3 scripts/evaluate_ask_quality.py --output /tmp/ask-local.json
python3 scripts/evaluate_ask_expansion.py --output /tmp/ask-expansion.json
```

The first command is the unchanged 15-question local-only corpus. All its packets
remain identical to the constraint iteration: its forbidden cloud source is
removed, the Latvian→English local-only context question still has no match.

The second command uses 8 synthetic sources and 7 questions/paraphrases, the real
v2 retrieval/validation pipeline and **fixed synthetic planner replies**. No AI is
contacted and no generated-answer quality is scored. It includes existing working
translations as controls, three previously skipped constrained questions and two
alternatives that drop technical anchors.

Baseline `adaada0` → this iteration, identical corpus hash:

| Measurement | Before | After |
| --- | ---: | ---: |
| Source recall in packet | 0.5714 | 1.0000 |
| Source Precision@5 | 0.6750 | 1.0000 |
| Questions with forbidden sources | 2 | 0 |
| Seeded provenance integrity | 100% | 100% |

[Before report](reports/2026-11-20-ask-expansion-before.json) and
[after report](reports/2026-11-20-ask-expansion-after.json). These small deterministic
figures measure our handling of specified plans, not real-model translation
quality, production retrieval quality, or universal multilingual understanding.
The source/precision definitions and undefined empty-result denominator policy
are the same as in [the local evaluation](ask-quality-evaluation.md).

`test_ask_expansion_api.py` uses normal synthetic-member login and checks the JSON
and both stream contracts, source ownership, disabled expansion, no-AI requests,
provider absence and planner failure. Chromium checks the real UI receiving an
English source and a valid evidence citation for a Latvian constrained question;
the model reply is explicitly simulated. Real-provider observations, when run,
must be reported separately from these fixtures.
