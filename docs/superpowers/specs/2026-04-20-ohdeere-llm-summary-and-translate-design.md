# `sfp_ohdeere_llm_summary` + `sfp_ohdeere_llm_translate` (Phase 1)

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Add the first two LLM-backed modules to SpiderFoot, backed by the self-hosted `ohdeere-llm-gateway` (Ollama behind an async serial job queue). Both use a new shared helper `spiderfoot/ohdeere_llm.py` that wraps submit-and-poll against the gateway's `POST /api/v1/jobs` + `GET /api/v1/jobs/{id}` endpoints.

- **`sfp_ohdeere_llm_summary`** — post-scan summarizer. Reads all scan events from SpiderFoot's SQLite in `finish()`, builds a structured prompt, emits one `DESCRIPTION_ABSTRACT` summarizing the scan as usable intelligence.
- **`sfp_ohdeere_llm_translate`** — per-event translator for content-heavy event types (`LEAKSITE_CONTENT`, `DARKNET_MENTION_CONTENT`, `RAW_RIR_DATA`). Buffers events during the scan, detects non-English content via a cheap stopword heuristic in `finish()`, translates via `run_prompt()`, re-emits the translated content as a child event of the original.

Both modules use the `finish()` lifecycle hook (matches `sfp_ohdeere_notification`'s pattern) rather than inline `handleEvent` processing. This keeps scan wall-clock time predictable despite the gateway's serial processing.

## Non-goals

- **Not** building `sfp_ohdeere_llm_adverse_media`. Deferred until the gateway runs a larger model (Qwen 32B INT8 is on the user's roadmap). gemma3:4b produces mediocre allegation/sentiment extraction; shipping that with the current model would erode user trust in LLM output generally.
- **Not** building `sfp_ohdeere_llm_entities` (entity normalization / cross-scan clustering). Low hit rate for most scan types; defer until adverse media proves the LLM module pattern works.
- **Not** streaming LLM responses. Gateway doesn't expose streaming; the serial queue implies completion-based processing.
- **Not** caching prompt/response pairs. Same prompt = same gateway cost; acceptable for the user's ad-hoc scan pattern. Adding a cache is a future optimization.
- **Not** cancelling in-flight jobs on timeout. `run_prompt` just raises — the job still consumes gateway capacity until the gateway's 5-minute server-side timeout fires. Calling `DELETE /api/v1/jobs/{id}` on caller timeout is a follow-up.
- **Not** introducing new event types. Summary emits `DESCRIPTION_ABSTRACT`; translate re-emits the input event type with translated `data`. Keeps the typed event registry (Phase 1 item 1) stable.
- **Not** chaining translated content into the event bus during the scan. Translations emit at scan-end via `finish()`, so downstream modules can't react to them during the same scan. Matches the user's stated "post-processing layer" mental model. If a future consumer needs live translated content, that module can be refactored to inline processing later.

## Design

### Shared helper — `spiderfoot/ohdeere_llm.py`

~140 lines. Builds on `spiderfoot/ohdeere_client.py`. Pure stdlib.

**Public API:**

```python
class OhDeereLLMError(RuntimeError): ...
class OhDeereLLMTimeout(OhDeereLLMError): ...
class OhDeereLLMFailure(OhDeereLLMError): ...


def run_prompt(
    prompt: str,
    *,
    base_url: str,
    model: str = "gemma3:4b",
    options: dict | None = None,
    timeout_s: int = 300,
    client: "OhDeereClient | None" = None,
) -> str:
    """Submit a prompt to ohdeere-llm-gateway, poll until completion, return
    the response string.

    Raises:
        OhDeereClientError: client helper is disabled (env vars unset).
        OhDeereLLMTimeout: polling exceeded `timeout_s` without terminal status.
        OhDeereLLMFailure: job reported FAILED or CANCELLED.
    """
```

**Control flow:**

1. Acquire client: `client = client or get_client()`. If `client.disabled`, raise `OhDeereClientError`.
2. Truncate prompt to 200_000 chars (gateway hard cap). If truncated, log a WARNING via `logging.getLogger("spiderfoot.ohdeere_llm")`.
3. Submit: `client.post("/api/v1/jobs", body={"model": model, "prompt": prompt, "options": options or {}}, base_url=base_url, scope="llm:query")`. Store `id`.
4. Poll loop: `client.get(f"/api/v1/jobs/{id}", base_url=base_url, scope="llm:query")`. Sleep with exponential backoff: 1s → 2s → 4s → 8s → 10s cap (resets backoff on each iteration).
5. Terminate on:
   - `status == "DONE"` → return `response["result"]`.
   - `status == "FAILED"` → raise `OhDeereLLMFailure(response.get("error"))`.
   - `status == "CANCELLED"` → raise `OhDeereLLMFailure("job cancelled")`.
   - `time.monotonic() - started > timeout_s` → raise `OhDeereLLMTimeout`.

**Thread-safety:** inherits from `OhDeereClient` singleton. Multiple concurrent `run_prompt()` calls from different modules (e.g. summary + translate running in separate scan threads) serialize on the gateway itself, not on the helper. Helper holds no mutable state.

**What the helper does NOT do:**
- No prompt building or templating — caller supplies the full prompt.
- No response parsing or structured output validation — caller parses as needed.
- No retry on timeout. Caller decides whether to re-submit.
- No caching.
- No job cancellation on caller timeout (deferred).

**Logger:** `logging.getLogger("spiderfoot.ohdeere_llm")`. One DEBUG per poll iteration (diagnostic — "polling job X, status Y, elapsed Z"); one WARNING on prompt truncation. No INFO/ERROR; failures propagate as exceptions for caller handling.

### `sfp_ohdeere_llm_summary`

~180 lines.

**Meta:**
- `flags = []`
- `useCases = ["Investigate", "Passive"]`
- `categories = ["Content Analysis"]`
- `dataSource.model = "FREE_NOAUTH_UNLIMITED"`
- `dataSource.website = "https://docs.ohdeere.se/llm-gateway/"`

**Opts:**

```python
opts = {
    "llm_base_url": "https://llm.ohdeere.internal",
    "model": "gemma3:4b",
    "timeout_s": 300,
    "max_events_per_type": 25,
}
```

**Watched events:** `["ROOT"]` (defensive — modules with empty `watchedEvents` may not receive `finish()` calls in all SpiderFoot versions; watching ROOT hooks the module into the lifecycle without acting on it).

**Produced events:** `["DESCRIPTION_ABSTRACT"]`.

**Lifecycle:**

```python
def handleEvent(self, event):
    # Never acts on ROOT. Only watches it to receive finish().
    return

def finish(self):
    if self._client.disabled or self.errorState or self._summarized:
        return
    self._summarized = True

    scan_id = self.getScanId()
    events = self.sf.db.scanResultEvent(scan_id)   # existing SpiderFootDb method
    if not events:
        summary = "No events were produced in this scan."
    else:
        prompt = self._build_prompt(events)
        try:
            summary = run_prompt(
                prompt,
                base_url=self.opts["llm_base_url"],
                model=self.opts["model"],
                timeout_s=int(self.opts["timeout_s"]),
            )
        except (OhDeereLLMTimeout, OhDeereLLMFailure, OhDeereClientError) as exc:
            self.error(f"OhDeere LLM summary failed: {exc}")
            self.errorState = True
            return

    root_event = self._synthesize_root_event(scan_id)
    self._emit(root_event, "DESCRIPTION_ABSTRACT", summary)
```

**`_build_prompt(events)`:**

1. Count events by type. Take top 20 types by count.
2. For each of the top-N types, sample up to `max_events_per_type` events (oldest first). Include module name, truncated `data` (first 200 chars), truncated `source_data` (first 100 chars).
3. Assemble the final prompt from a fixed template (see below). Hard-cap the total at ~150k chars (leaves 50k of the gateway's 200k budget for the model to write).

**Prompt template:**

```
You are summarizing an OSINT reconnaissance scan. Produce a concise, neutrally-worded
summary (3-5 paragraphs) covering:
- What the scan target was
- Major entities discovered (domains, emails, people, companies)
- Notable risk signals (malicious indicators, breach exposures, vulnerabilities)
- Areas of uncertainty or where human review is warranted

Do NOT draw legal conclusions or attribute intent. Use phrases like "appears to",
"was found to reference", "may be associated with".

Scan target: {target}
Event counts by type:
  {type_counts}

Representative events (max {max_per_type} per type):
{event_samples}

Summary:
```

`{target}` comes from `self.sf.db.scanInstanceGet(scan_id)[2]` (seed_target column). The `_synthesize_root_event` uses the same seed_target to reconstruct the scan's root event so the emitted `DESCRIPTION_ABSTRACT` parents to the scan's actual ROOT.

**Why synthesize a ROOT event:** SpiderFoot event chains require a parent. Emitting `source_event=None` breaks correlation rules. The original ROOT event was created at scan start and isn't available in `finish()` context. Reconstructing it with matching `data` (the seed target) gives the emitted summary a sensible parent — the same one every other first-order event in the scan has.

**Duplicate-call guard:** `self._summarized = True` flag set on first `finish()` call. Multiple `finish()` invocations (orchestrator cleanup) produce one summary.

**Empty-scan handling:** If `scanResultEvent` returns no rows, emit a static "No events were produced in this scan." abstract rather than querying the LLM for nothing.

### `sfp_ohdeere_llm_translate`

~200 lines.

**Meta:**
- `flags = []`
- `useCases = ["Investigate", "Passive"]`
- `categories = ["Content Analysis"]`
- `dataSource.model = "FREE_NOAUTH_UNLIMITED"`

**Opts:**

```python
opts = {
    "llm_base_url": "https://llm.ohdeere.internal",
    "model": "gemma3:4b",
    "timeout_s": 120,
    "max_content_length": 15000,
    "max_events": 20,
    "skip_english": True,
}
```

**Watched events:** `["LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"]`.

**Produced events:** `["LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"]` (same set — translations re-emit as child events of the same type).

**Lifecycle:**

```python
def handleEvent(self, event):
    if self._client.disabled or self.errorState:
        return
    # Cheap buffering during scan — no LLM calls here.
    self._buffer.append((event, event.data or ""))

def finish(self):
    if self._client.disabled or self.errorState or self._translated:
        return
    self._translated = True
    if not self._buffer:
        return

    max_events = int(self.opts["max_events"])
    max_chars = int(self.opts["max_content_length"])
    skip_english = bool(self.opts["skip_english"])
    processed = 0

    for source_event, content in self._buffer:
        if processed >= max_events:
            self.debug(f"hit max_events={max_events}; dropping remainder")
            break
        if skip_english and self._is_probably_english(content):
            continue
        truncated = content[:max_chars]
        prompt = self._build_prompt(truncated)
        try:
            translated = run_prompt(
                prompt,
                base_url=self.opts["llm_base_url"],
                model=self.opts["model"],
                timeout_s=int(self.opts["timeout_s"]),
            )
        except (OhDeereLLMTimeout, OhDeereLLMFailure, OhDeereClientError) as exc:
            self.error(f"OhDeere LLM translate failed: {exc}")
            self.errorState = True
            return
        self._emit(source_event, source_event.eventType, translated)
        processed += 1
```

**Language detection heuristic:**

```python
_STOPWORDS = {"the", "and", "of", "to", "a", "in", "is", "for", "on",
              "that", "with", "as", "this", "by", "be"}

def _is_probably_english(self, text: str) -> bool:
    sample = text[:4000].lower()
    count = sum(len(re.findall(rf"\b{w}\b", sample)) for w in _STOPWORDS)
    return count >= 3
```

Deliberately dumb. False negatives on very short English (OK — short content isn't worth translating). False positives for languages that share common tokens (Dutch's "de" won't trip this, Swedish "is" as a single word is rare in real content). Saves the gateway from processing the 80%+ of content that's already English.

Not adding a dependency like `langdetect` because it's another package to maintain and the heuristic is "good enough" for filtering.

**Prompt template:**

```
Translate the following text to English. Preserve technical terms, URLs, email
addresses, IP addresses, and proper nouns as-is. If the text is already in English,
return it unchanged. Do not add commentary, disclaimers, or notes about the
translation — output only the translated text.

---BEGIN TEXT---
{content}
---END TEXT---
```

**Event re-emission:**

```python
def _emit(self, source_event, event_type, data):
    evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
    self.notifyListeners(evt)
```

Parent chain preserved: the translated event's `sourceEvent` is the original untranslated event. Downstream consumers (including correlation rules using `source.` prefixes) get both versions in the chain.

**Volume caps — why the opts matter:**

- `max_events=20`: prevents a noisy scan with hundreds of `RAW_RIR_DATA` events from filling the gateway's 200-job queue.
- `max_content_length=15000`: per-event cap keeps individual prompts well under 200k (leaves room for the template wrapper).
- Both are per-scan, enforced during `finish()` only. If the 20 budget is exhausted, excess non-English events are silently dropped with a DEBUG log.

### Why `ROOT` as `watchedEvents` for the summary module

SpiderFoot's thread pool calls `finish()` only on modules whose `incomingEventQueue` is active. A module with empty `watchedEvents` gets no queue, so `finish()` isn't invoked during normal orchestration.

Watching `ROOT` guarantees:
1. The module is instantiated and its event queue is attached at scan start.
2. `finish()` is called during orchestrator cleanup.

The module's `handleEvent` short-circuits immediately on ROOT (only `finish()` does work). A couple of modules in the existing codebase (e.g. `sfp__stor_db`) use a similar defensive pattern.

### Shared infrastructure summary

| Layer | File | Purpose |
|---|---|---|
| Transport | `spiderfoot/ohdeere_client.py` (existing) | OAuth2 + HTTP. Unchanged. |
| LLM protocol | `spiderfoot/ohdeere_llm.py` (new) | Submit + poll + timeout. Stateless. |
| Summary application | `modules/sfp_ohdeere_llm_summary.py` (new) | Scan-end summarizer. Uses finish(). |
| Translate application | `modules/sfp_ohdeere_llm_translate.py` (new) | Content translator. Uses finish(). |

Each layer has one responsibility. The two modules share nothing except the helper — no inheritance, no mixins, no shared base class. Future LLM modules (adverse media, entity normalization) will plug in at the application layer the same way.

## Testing

### `test/unit/spiderfoot/test_ohdeere_llm.py` (~150 lines, 7 tests)

1. Happy path: submit → poll returns DONE → helper returns result string.
2. Multi-poll: first QUEUED, second RUNNING, third DONE. Asserts polling backoff.
3. Timeout: status stays RUNNING past `timeout_s` → raises `OhDeereLLMTimeout`.
4. FAILED: status returns FAILED with error → raises `OhDeereLLMFailure` with error message.
5. CANCELLED: status returns CANCELLED → raises `OhDeereLLMFailure("job cancelled")`.
6. Prompt truncation: 300k-char input → WARNING log + submit body is 200k chars.
7. Client disabled: helper raises `OhDeereClientError`.

All mock `OhDeereClient.get()`/`.post()` and `time.monotonic()` / `time.sleep()`.

### `test/unit/modules/test_sfp_ohdeere_llm_summary.py` (~220 lines, 10 tests)

1. `opts`/`optdescs` parity.
2. `watchedEvents=["ROOT"]`, `producedEvents=["DESCRIPTION_ABSTRACT"]`.
3. Silent no-op when client disabled.
4. Happy path: mocked `scanResultEvent` returns events; `run_prompt` returns a summary; one `DESCRIPTION_ABSTRACT` emitted matching the returned string.
5. Prompt construction: 3 event types with 30 events each → top-20 counts logic + per-type sampling @ `max_events_per_type=25`.
6. Duplicate `finish()` calls → one summary only (boolean guard).
7. `OhDeereLLMTimeout` → `errorState`, no emission, `self.error(...)`.
8. `OhDeereLLMFailure` → same.
9. `OhDeereClientError` → same.
10. Empty scan (no events) → emits static "No events..." abstract without calling `run_prompt`.

### `test/unit/modules/test_sfp_ohdeere_llm_translate.py` (~230 lines, 10 tests)

1. `opts`/`optdescs` parity.
2. `watchedEvents` / `producedEvents` shape.
3. Silent no-op when client disabled (no buffer appends either).
4. Non-English content → `run_prompt` called; translated event emitted as child of original.
5. English content → `run_prompt` NOT called; no emission.
6. `skip_english=False` → English content also translated (opt override verified).
7. `max_events=2` → only first 2 non-English processed; rest dropped with DEBUG.
8. `max_content_length=100` → `run_prompt` called with truncated input string.
9. `OhDeereLLMFailure` on first item → `errorState`, no further processing.
10. Duplicate `finish()` → one pass (guard).

### Full-suite verification

Current baseline after `sfp_ohdeere_notification`: 1451 passed + 35 skipped.

After this spec: **1478 passed + 35 skipped** (+7 helper + +10 summary + +10 translate).

Flake8 clean across all three new files.

### Integration smoke (manual, during implementation)

With `OHDEERE_CLIENT_ID` / `OHDEERE_CLIENT_SECRET` set and a running LLM gateway reachable:

```bash
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_llm_summary \
    2>&1 | tail -20
```

Expected: scan runs, `finish()` submits one job to the gateway, polls for 30-120s on gemma3:4b, emits a paragraph-style summary as `DESCRIPTION_ABSTRACT`.

A similar scan with `sfp_ohdeere_llm_translate` + a target that produces non-English `RAW_RIR_DATA` events exercises the translation path.

## Rollout

Six commits: three TDD failing-test pairs (helper, summary, translate), three implementation pairs. Dispatch order: helper first (pure infrastructure), then summary and translate in parallel (disjoint files).

Follow-ups (not in this spec):
- `CLAUDE.md` Module Inventory add both LLM modules to `FREE_NOAUTH_UNLIMITED`.
- `sfp_ohdeere_llm_adverse_media` — when Qwen 32B INT8 replaces gemma3:4b.
- `sfp_ohdeere_llm_entities` — cross-scan entity normalization. Deferred.
- Live smoke scan with real credentials against a real LLM gateway.
- Postgres storage migration (backlog task #45) — enables richer scan-level queries once LLM summaries accumulate.

## Follow-ups enabled

- Helper `spiderfoot/ohdeere_llm.py` becomes the foundation for every future LLM module. Adverse media and entity normalization modules become ~150-line specs on top of it.
- Post-scan `finish()`-hook pattern for LLM work (collect during scan, process at end) is now established. Matches the gateway's serial architecture cleanly and is the right shape for any future "bundled analysis" module.
- `DESCRIPTION_ABSTRACT` emitted by the summary becomes queryable in SpiderFoot's scan-results UI alongside all other scan data. When Postgres arrives, summaries across scans become cross-queryable for trend analysis.
