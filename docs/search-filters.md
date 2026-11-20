# Shared saved-library filters

The home search and results search share one filter state. The filter icon is
available before entering text; opening it switches Web to Ask. Checkboxes and
dates are a draft until **Apply**. **Cancel**, closing the dialog and Escape leave
the active selection unchanged. **Clear all** removes active filters immediately.
Each active chip can also be removed. Applying/removing filters with results open
reruns the current query; applying on the home screen waits for Search.

Filters persist across new questions and reloads in local storage under the
signed-in member's opaque ID. They are not shared between accounts or browsers.
Web search does not apply library filters. A query containing only filters, or an
empty query with an active filter, can browse saved items.

## Facets and date semantics

- Sources use canonical URL hostnames (case folded, IDNA, `www.` removed), not
  user-supplied site labels. Multiple sources are OR; separate facets are AND.
- Material types use the existing capture metadata (`snippet`, `page`, `video`,
  `bookmark`, etc.). A `page` label does not prove that the complete page was
  captured; no source data is reclassified or re-extracted.
- Saved time uses **captures.saved_at**, not publication time or captured_at.
  Today/yesterday mean local calendar days in the browser's IANA time zone.
  Last 7/30 days include today. Custom From/Through dates are inclusive in the UI;
  SQL uses UTC `[local midnight, next local midnight)` boundaries, including DST.
- An empty facet means unrestricted. At most 20 values per facet are accepted.
  Invalid fields, source syntax, dates and time zones return 422 before streaming.

Manual filters are bound SQL predicates before lexical/semantic candidate limits,
including all optional AI-expanded searches. No new persistent data store or
schema migration is required. Cache identity includes the resolved filter scope.

## Natural language

The same selected filters are returned to the UI as removable/editable chips.
Recognized explicit metadata phrases are separated from the search topic:

- `Parādi visu info par Docker ko saglabāju vakar` → topic `Docker`, Yesterday.
- `Docker from GitHub yesterday` → known `github.com` source and Yesterday.
- `Docker no 2026-11-01 līdz 2026-11-20` → an inclusive custom date range.
- Explicit snippet/bookmark/page wording can select the corresponding type.

Local LV/EN rules handle the presets, dates and known source aliases without AI.
Unmentioned facets retain their prior selection. An explicit new condition
replaces that facet. Manual Apply/removal reruns with `interpret_filters=false`,
so wording in the old question cannot silently reapply the removed filter.
Quoted/code phrases, negated metadata and conflicting simple date phrases are not
silently interpreted as filters. This is bounded parsing, not universal language
understanding.

For supported additional calendar phrases (`pagājušajā nedēļā`, `last week`,
previous calendar month, etc.), the UI can request one optional Recall-provider
plan **after local results have appeared**. It has an 8-second timeout and a
4096-character response bound. Only complete custom date ranges and exact,
allowlisted metadata-only phrases are accepted. The planner receives the query,
reference date, time zone and current date selection, not saved source text,
source facets or account identity. It cannot rewrite the search topic or set SQL,
source/type filters or account scope. Output remains model-derived and editable.
If unavailable or invalid, the existing filters/local matches remain visible and
the UI says that the time condition was not applied; it does not synthesize an
answer pretending that condition was applied.

## Ask packet versus saved-item browsing

Ask still uses up to eight evidence cards within its token budget. Below it,
**Matching saved items** lists distinct original captures with local lexical/title
matches, the same metadata/content predicates, total count, stable date/ID sorting
and explicit pagination (20 per UI page; API maximum 50). Metadata-only bookmarks
can match titles or filter-only browsing. Saved text uses the existing Markdown
renderer, including current `content` evidence as escaped text; original URLs remain accessible. This list is local lexical browsing,
not a claim of exhaustive semantic recall or a list of all AI-expanded matches.

## API

`GET /api/memory/filters` returns this member's source/type values and counts.
Existing JSON and v1/v2 stream queries accept:

```json
{
  "query": "Docker",
  "filters": {"sources": ["github.com"], "period": "yesterday"},
  "timezone": "Europe/Riga",
  "interpret_filters": true
}
```

Responses include `filters`, `resolved_filters` and `filter_search_text` when the
filter contract is used. `POST /api/memory/browse` uses the same body plus `limit`
and `offset`. `POST /api/memory/filters/interpret` supplies the optional calendar
plan; `synthesize=false` never invokes it. Returned exact `filter_phrases` travel
with the current query when its proposed dates are applied. Every endpoint
requires a member and uses that member's database.

Implementation: `search_filters.py`, `saved_search.py`, `database.py`,
`memory_retrieval.py`, memory routes and `library-filters.js`. Time zone fallback
data is pinned through the PSF [tzdata package](https://pypi.org/project/tzdata/)
for systems without an IANA database, including Windows.

Verification: `tests/test_search_filters.py` and
`tests/test_search_filters_browser.py` cover calendar/DST boundaries, filters
before lexical/vector limits, source provenance, JSON/both streams, AI expansion,
pagination/bookmarks, no-AI fallback, provider-plan validation, per-account
persistence, Apply/Cancel/Clear, next queries, filter-only browsing and theme/mobile
layout. AI calendar responses in acceptance tests are synthetic; they do not
establish real-provider interpretation quality.
