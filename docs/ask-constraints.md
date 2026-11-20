# Explicit Ask conditions

Ask separates a positive search topic from supported content conditions before
candidate search. The original question remains in the result, answer prompt and
cache identity. After all original/alternative candidates are merged, conditions
are checked against evidence before diversity selection and packet limits.

Supported syntax in this iteration:

- `without cloud`, `with no cloud dependency`, `bez mākoņa`: require an explicit
  English/Latvian statement of operation without cloud, offline operation, lack
  of a cloud requirement, or optional cloud use.
- `exclude X`, `excluding X`, `except X`, `izņemot X`, `izslēdzot X`: literal,
  case-insensitive whole-term exclusions. Quote a multiword value, for example
  `notes excluding "Dropbox Sync"`. This is a text exclusion, not inferred entity
  identity. Operators inside a quoted search phrase are not interpreted.

A missing cloud word is not proof. Questions, recognized uncertain/conditional
claims and contradictions do not establish a cloud-free capability. The check
uses only original evidence within the visible 700-character excerpt, not AI
summaries, save reasons or source titles. An explicit cloud requirement in the
same excerpt overrides a positive absence/optional statement. Literal exclusions
also inspect source/context titles to avoid returning the excluded text as the
result's label.

`retrieval.constraints` reports applied checks and supported/contradicted/unknown
candidate counts. Only supported excerpts enter the packet. The UI explains that
unconfirmed conditions do not prove the library has no matching source. There is
no database migration or capability fact store.

## Verification and limits

`tests/test_ask_constraints.py` exercises the real isolated local retrieval and
v2 stream, positive and negative English/Latvian claims, optional cloud, missing
information, conflicting statements, quoted operators and a second candidate
search. Nine original acceptance cases failed against the pre-change selection.

Run the unchanged local corpus with:

```sh
python3 scripts/evaluate_ask_quality.py --output /tmp/ask-quality.json
```

Compared with [the source-diversity result](reports/2026-11-20-ask-quality-after.json),
[this local result](reports/2026-11-20-ask-constraints-local.json) changes only
`negative`: the forbidden cloud source is removed. Source/evidence recall and all
other packets are unchanged; forbidden-source query count is 1 → 0. Macro source
precision changes 0.8750 → 0.9545, with empty-result precision undefined and omitted
from the mean; this is not a production-quality estimate.

This is a bounded pattern recognizer, not general natural-language entailment or
universal multilingual constraint handling. A complex statement may be withheld,
and a claim requiring context outside the excerpt cannot be confirmed. Multi-tool
comparisons, sarcasm and arbitrary negation are not guaranteed. Checks operate on
individual retrieved excerpts, not every passage in a whole source. Search still
has a bounded candidate pool; zero selected evidence is not proof of absence.
Unrecognized condition syntax keeps the normal search behavior. No external
provider or model download is introduced by these local checks.
