"""Shared, validated saved-library filters. No provider or database work on import."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(default_factory=list, max_length=20)
    capture_types: list[str] = Field(default_factory=list, max_length=20)
    period: Literal["any", "today", "yesterday", "last7", "last30", "custom"] = "any"
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("sources")
    @classmethod
    def domains(cls, values):
        result = []
        for value in values:
            domain = source_domain("https://" + value)
            if not domain or domain != value.lower().removeprefix("www.") or len(domain) > 253:
                raise ValueError("Invalid source domain")
            result.append(domain)
        return list(dict.fromkeys(result))

    @field_validator("capture_types")
    @classmethod
    def kinds(cls, values):
        if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value) for value in values):
            raise ValueError("Invalid capture type")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def dates(self):
        if any(day and not date(2,1,1) <= day <= date(9998,12,31) for day in (self.start_date,self.end_date)):
            raise ValueError("Date is outside the supported range")
        if self.period == "custom":
            if not (self.start_date or self.end_date):
                raise ValueError("Choose a start or end date")
            if self.start_date and self.end_date and self.start_date > self.end_date:
                raise ValueError("Start date must be before end date")
        else:
            self.start_date = self.end_date = None
        return self


def source_domain(url):
    try:
        parsed = urlsplit(url or "")
        if parsed.scheme not in {"http", "https"}:
            return ""
        host = (parsed.hostname or "").lower().removeprefix("www.").encode("idna").decode("ascii")
        return host if re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) else ""
    except (ValueError, UnicodeError):
        return ""


def local_zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("Invalid time zone") from None


def resolve_filters(filters, timezone_name="UTC", now=None):
    selected = SearchFilters.model_validate(filters or {})
    zone = local_zone(timezone_name)
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date()
    start, end = selected.start_date, selected.end_date
    if selected.period == "today": start = end = today
    elif selected.period == "yesterday": start = end = today - timedelta(days=1)
    elif selected.period in {"last7", "last30"}:
        start, end = today - timedelta(days=int(selected.period[4:]) - 1), today
    def midnight(day):
        return datetime.combine(day, time.min, zone).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "sources": selected.sources, "capture_types": selected.capture_types,
        "saved_after": midnight(start) if start else None,
        "saved_before": midnight(end + timedelta(days=1)) if end else None,
    }


def filter_sql(resolved, alias="c"):
    # The alias is an internal constant; every user-controlled value is bound.
    if alias not in {"c"}: raise ValueError("Invalid capture alias")
    clauses, params = [], []
    for field, column in (("sources", "nodecast_source_domain(c.source_url)"), ("capture_types", "c.capture_type")):
        values = resolved.get(field) or []
        if values:
            clauses.append(column + " IN (" + ",".join("?" for _ in values) + ")")
            params.extend(values)
    if resolved.get("saved_after"):
        clauses.append("julianday(c.saved_at)>=julianday(?)"); params.append(resolved["saved_after"])
    if resolved.get("saved_before"):
        clauses.append("julianday(c.saved_at)<julianday(?)"); params.append(resolved["saved_before"])
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def prepare_filter_context(query, filters=None, timezone_name="UTC", interpret=True, sources=(), phrases=(), now=None):
    """Recognize explicit LV/EN metadata phrases; leave quoted/negated text alone.

    Absent fields never clear a previous choice. An explicit new phrase replaces
    that one facet; manual Apply/removal sets interpret=False but still strips
    recognized metadata wording from the lexical search.
    """
    selected = SearchFilters.model_validate(filters or {}).model_dump(mode="json")
    local_zone(timezone_name)
    masked = re.sub(r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`', lambda m: " " * len(m[0]), query)
    spans, updates, time_matches = [], {}, []
    def add(match, patch):
        if re.search(r"\b(?:not|except|excluding|ne|izņemot|bez)\s*$", masked[max(0, match.start()-24):match.start()], re.I):
            return
        if any(match.start() < b and match.end() > a for a,b in spans): return
        spans.append(match.span()); updates.update(patch)
        if "period" in patch: time_matches.append((match.span(),patch))
    prefix = r"(?:(?:ko\s+)?(?:es\s+)?(?:saglabāju|saglabāts|saglabāt[ao]s|(?:i\s+)?saved(?:\s+on)?)\s+)?"
    for pattern, period in ((r"aizvakar|day before yesterday", "daybefore"), (r"vakar|yesterday", "yesterday"), (r"šodien|today", "today"), (r"pēdēj[āa]s?\s+7\s+dien[āa]s?|(?:in\s+the\s+)?(?:last|past)\s+7\s+days", "last7"), (r"pēdēj[āa]s?\s+30\s+dien[āa]s?|(?:in\s+the\s+)?(?:last|past)\s+30\s+days", "last30")):
        for match in re.finditer(r"\b" + prefix + "(?:" + pattern + r")\b", masked, re.I):
            patch = {"period": period, "start_date": None, "end_date": None}
            if period == "daybefore":
                day = (now or datetime.now(timezone.utc)).astimezone(local_zone(timezone_name)).date() - timedelta(days=2)
                patch.update(period="custom", start_date=day.isoformat(), end_date=day.isoformat())
            add(match, patch)
    for match in re.finditer(r"\b(?:no|from|between)\s+(\d{4}-\d{2}-\d{2})\s+(?:līdz|to|and)\s+(\d{4}-\d{2}-\d{2})\b", masked, re.I):
        try:
            start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2])
            if start <= end: add(match, {"period":"custom", "start_date":str(start), "end_date":str(end)})
        except ValueError: pass
    domains = list(dict.fromkeys(sources))
    for match in re.finditer(r"\b(?:no|from|source:|avots:)\s*([\w.-]+(?:\s*(?:,|un|and)\s*[\w.-]+)*)", masked, re.I):
        found = []
        for name in re.split(r"\s*(?:,|\bun\b|\band\b)\s*", match[1], flags=re.I):
            candidates = [domain for domain in domains if name.casefold() in {domain.casefold(), domain.split('.')[0].casefold()}]
            if len(candidates) != 1: break
            found.extend(candidates)
        else:
            if found: add(match, {"sources": list(dict.fromkeys(found))})
    for pattern, kind in ((r"(?:tikai\s+)?fragmentus|(?:only\s+)?snippets", "snippet"), (r"(?:tikai\s+)?grāmatzīmes|(?:only\s+)?bookmarks", "bookmark"), (r"piln[āa]s\s+lapas|full\s+pages", "page")):
        for match in re.finditer(r"\b(?:" + pattern + r")\b", masked, re.I): add(match, {"capture_types":[kind]})
    # Conflicting date phrases remain text rather than silently picking one.
    if len({tuple(sorted(patch.items())) for _,patch in time_matches}) > 1:
        time_spans = {span for span,_ in time_matches}
        spans = [span for span in spans if span not in time_spans]
        for field in ("period","start_date","end_date"): updates.pop(field,None)
    # AI output may remove exact, bounded phrases only; it cannot rewrite topics.
    for phrase in phrases:
        if isinstance(phrase, str) and 0 < len(phrase) <= 200:
            start = masked.find(phrase)
            if start >= 0 and not any(start < b and start + len(phrase) > a for a,b in spans):
                spans.append((start, start + len(phrase)))
    if interpret: selected.update(updates)
    selected = SearchFilters.model_validate(selected).model_dump(mode="json")
    text = query
    for start, end in sorted(spans, reverse=True): text = text[:start] + " " + text[end:]
    if spans:
        text = re.sub(r"^\s*(?:parādi|atrodi|meklē|show|find|search)(?:\s+(?:man|me))?(?:\s+(?:visu\s+(?:info|informāciju)|visu|all\s+(?:info|information)|everything|all))?(?:\s+(?:par|about|on))?\s+", "", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip(" ,?.")
        text = re.sub(r"(?:,?\s+)?(?:ko|that I|which I)\s*$", "", text, flags=re.I).strip()
    remaining = list(masked)
    for start,end in spans: remaining[start:end] = " " * (end-start)
    remaining = ''.join(remaining)
    ai_hint = r"\b(?:pagājuš\w*|iepriekšēj\w*|aizpagājuš\w*|last\s+(?:week|month)|previous\s+(?:week|month))\b"
    needs_ai = interpret and any(not re.search(r"\b(?:not|except|excluding|ne|izņemot|bez)\s*$",remaining[max(0,m.start()-24):m.start()],re.I) for m in re.finditer(ai_hint,remaining,re.I))
    return {"filters": selected, "resolved": resolve_filters(selected, timezone_name, now),
            "search_text": text.strip(), "timezone": timezone_name,
            "recognized": bool(spans), "interpret": interpret,
            "phrases": list(phrases),
            "needs_ai": bool(needs_ai)}
