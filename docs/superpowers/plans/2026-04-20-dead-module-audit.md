# Dead-Module Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove modules requiring paid subscriptions (`COMMERCIAL_ONLY` / `PRIVATE_ONLY`) and modules whose underlying service is dead, acquired-and-paywalled, or has a punitive free tier. Target ~25-35 modules removed from the 233-module inventory.

**Architecture:** Three-tier execution. Tier 1 deletes 10 metadata-flagged paid modules directly (no research). Tier 2 dispatches parallel web-research subagents across 78 `FREE_AUTH_*` / `FREE_NOAUTH_LIMITED` candidates, produces a decisions table for user approval, then deletes the approved subset. Tier 3 appends the surviving module inventory to `CLAUDE.md` as an anti-regression fence.

**Tech Stack:** Standard Unix shell (`git rm --ignore-unmatch`), Python 3.12+ (for verification smoke tests), parallel subagent dispatch for Tier 2 research.

**Spec:** `docs/superpowers/specs/2026-04-20-dead-module-audit-design.md`.

---

## File Structure

- **Delete** (per module): `modules/sfp_<name>.py`, `test/unit/modules/test_sfp_<name>.py`, `test/integration/modules/test_sfp_<name>.py`.
- **Modify** `setup.cfg` — remove any `per-file-ignores` entries referencing deleted modules.
- **Create** `docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md` — the decisions table assembled from Tier 2 research (committed as audit history, used as the source of truth for Task 3).
- **Modify** `CLAUDE.md` — add a "Module inventory" section after Tier 3.

---

## Context for the implementer

- **Trust the metadata in Tier 1.** Each `modules/sfp_*.py` has a `meta.dataSource.model` field; the 10 modules flagged `COMMERCIAL_ONLY` (8) or `PRIVATE_ONLY` (2) come out in Tier 1 without research. The 8 + 2 = 10 count excludes `sfp_template.py`, which is a reference file that lists every model value as documentation and must not be deleted.
- **The 78 Tier 2 candidates** are the set `grep -lE "FREE_AUTH_LIMITED|FREE_AUTH_UNLIMITED|FREE_NOAUTH_LIMITED" modules/sfp_*.py | grep -v sfp_template`. This count was verified 2026-04-20.
- **Removal is filename-based.** `SpiderFootHelpers.loadModulesAsDict` enumerates `modules/sfp_*.py` at startup — deleting a file is enough to drop it from the UI, CLI `-M`, and scan orchestration. No hardcoded module name lists to edit anywhere.
- **Event-type registry survives.** `spiderfoot/event_types.py` is NOT modified in this plan. Orphaned event types stay; see spec Non-goals.
- **Correlation rules in `correlations/*.yaml` are not touched.** Rules reference event types, not module names; removed modules silently stop producing their event types and correlation queries return empty. Harmless.
- **Current baseline after Phase 1 item 1:** 1615 passed, 35 skipped via `./test/run`. After Tier 1 + Tier 2 deletions, the total passing count drops by (unit + integration tests per removed module). Each removed module typically has 1 unit test file with 5-20 test methods. Plan for a drop of ~200-400 test cases over both tiers.
- **Web-research workflow for Tier 2**: each subagent uses `WebFetch` against the service's homepage / pricing page / developer sign-up page. It does NOT create accounts, does NOT test API endpoints, does NOT attempt scraping. Research is bounded to what's on public pages.
- **Running tests:** `./test/run` for the full suite. Single module's test: `python3 -m pytest test/unit/modules/test_sfp_<name>.py -v`.
- **Flake8:** `python3 -m flake8 <files>`. Config in `setup.cfg`.

---

## Task 1: Tier 1 — bulk-remove COMMERCIAL_ONLY + PRIVATE_ONLY modules

**Files:**
- Delete: `modules/sfp_<name>.py` × 10
- Delete: `test/unit/modules/test_sfp_<name>.py` × 10
- Delete: `test/integration/modules/test_sfp_<name>.py` × 10
- Modify: `setup.cfg` (if any `per-file-ignores` entries reference these modules)

The ten modules:
1. `sfp_c99` (COMMERCIAL_ONLY)
2. `sfp_dehashed` (COMMERCIAL_ONLY)
3. `sfp_haveibeenpwned` (COMMERCIAL_ONLY)
4. `sfp_seon` (COMMERCIAL_ONLY)
5. `sfp_sociallinks` (COMMERCIAL_ONLY)
6. `sfp_spur` (COMMERCIAL_ONLY)
7. `sfp_whoisology` (COMMERCIAL_ONLY)
8. `sfp_whoxy` (COMMERCIAL_ONLY)
9. `sfp_fsecure_riddler` (PRIVATE_ONLY)
10. `sfp_projectdiscovery` (PRIVATE_ONLY)

- [ ] **Step 1: Verify each module's meta flag matches the claim above**

Run:
```bash
for m in sfp_c99 sfp_dehashed sfp_haveibeenpwned sfp_seon sfp_sociallinks sfp_spur sfp_whoisology sfp_whoxy sfp_fsecure_riddler sfp_projectdiscovery; do
    flag=$(grep -oE "'model': \"(COMMERCIAL_ONLY|PRIVATE_ONLY)\"" "modules/${m}.py" 2>/dev/null || echo MISSING)
    echo "${m}: ${flag}"
done
```

Expected: each line shows either `'model': "COMMERCIAL_ONLY"` or `'model': "PRIVATE_ONLY"`. Any `MISSING` indicates the module's metadata has drifted since the spec was written — stop and escalate.

- [ ] **Step 2: Delete module files + tests (single `git rm` invocation)**

Run:
```bash
git rm --ignore-unmatch \
    modules/sfp_c99.py \
    modules/sfp_dehashed.py \
    modules/sfp_haveibeenpwned.py \
    modules/sfp_seon.py \
    modules/sfp_sociallinks.py \
    modules/sfp_spur.py \
    modules/sfp_whoisology.py \
    modules/sfp_whoxy.py \
    modules/sfp_fsecure_riddler.py \
    modules/sfp_projectdiscovery.py \
    test/unit/modules/test_sfp_c99.py \
    test/unit/modules/test_sfp_dehashed.py \
    test/unit/modules/test_sfp_haveibeenpwned.py \
    test/unit/modules/test_sfp_seon.py \
    test/unit/modules/test_sfp_sociallinks.py \
    test/unit/modules/test_sfp_spur.py \
    test/unit/modules/test_sfp_whoisology.py \
    test/unit/modules/test_sfp_whoxy.py \
    test/unit/modules/test_sfp_fsecure_riddler.py \
    test/unit/modules/test_sfp_projectdiscovery.py \
    test/integration/modules/test_sfp_c99.py \
    test/integration/modules/test_sfp_dehashed.py \
    test/integration/modules/test_sfp_haveibeenpwned.py \
    test/integration/modules/test_sfp_seon.py \
    test/integration/modules/test_sfp_sociallinks.py \
    test/integration/modules/test_sfp_spur.py \
    test/integration/modules/test_sfp_whoisology.py \
    test/integration/modules/test_sfp_whoxy.py \
    test/integration/modules/test_sfp_fsecure_riddler.py \
    test/integration/modules/test_sfp_projectdiscovery.py
```

Expected output: 30 `rm '<path>'` lines (one per deleted file). `--ignore-unmatch` suppresses errors on any path that doesn't exist (e.g. if a module never had an integration test).

Verify no unexpected files remain:
```bash
ls modules/sfp_c99.py modules/sfp_dehashed.py modules/sfp_haveibeenpwned.py modules/sfp_seon.py modules/sfp_sociallinks.py modules/sfp_spur.py modules/sfp_whoisology.py modules/sfp_whoxy.py modules/sfp_fsecure_riddler.py modules/sfp_projectdiscovery.py 2>&1 | head -5
```

Expected: each line reads `ls: modules/sfp_<name>.py: No such file or directory`.

- [ ] **Step 3: Clean up `setup.cfg` per-file-ignores**

Run:
```bash
grep -nE "sfp_(c99|dehashed|haveibeenpwned|seon|sociallinks|spur|whoisology|whoxy|fsecure_riddler|projectdiscovery)" setup.cfg
```

If any lines match, use `Edit` to remove them from the `per-file-ignores` block. If no lines match (empty output), skip this step.

Expected state at 2026-04-20: no `setup.cfg` entries reference any of the ten modules — the audit confirmed zero hits. If that's still the case, skip the cleanup.

- [ ] **Step 4: Run the full test suite**

Run: `./test/run`

Expected: flake8 clean; pytest reports `X passed, 35 skipped` where `X < 1615`. The exact drop depends on how many tests each removed module's test files contained — there's no single expected number. What matters is:
- No test failures.
- No `ModuleNotFoundError` / `ImportError` in the output, which would indicate some non-deleted file imported one of the removed modules.

If you see an `ImportError` on a removed module name, something in the repo hard-referenced it (unlikely given filename-glob discovery, but possible in a correlation script or doc). Grep for the name and fix or escalate.

- [ ] **Step 5: Smoke-test the scanner starts without errors**

Run:
```bash
SPIDERFOOT_LOG_FORMAT=json timeout 15 python3 ./sf.py -M 2>&1 | head -5
```

Expected: JSON log lines listing available modules. None of the removed module names should appear in the output.

Follow-up verification:
```bash
SPIDERFOOT_LOG_FORMAT=json timeout 15 python3 ./sf.py -M 2>&1 | grep -E "(c99|dehashed|haveibeenpwned|seon|sociallinks|spur|whoisology|whoxy|fsecure_riddler|projectdiscovery)" || echo "clean — none of the removed modules appear in -M output"
```

Expected: `clean — none of the removed modules appear in -M output`.

- [ ] **Step 6: Commit**

```bash
git commit -m "$(cat <<'EOF'
modules: remove commercial + private-only modules (Tier 1)

Ten modules whose meta.dataSource.model is COMMERCIAL_ONLY or
PRIVATE_ONLY, removed as part of the dead-module audit spec at
docs/superpowers/specs/2026-04-20-dead-module-audit-design.md.

Removed (8 COMMERCIAL_ONLY + 2 PRIVATE_ONLY):
- sfp_c99, sfp_dehashed, sfp_haveibeenpwned, sfp_seon,
  sfp_sociallinks, sfp_spur, sfp_whoisology, sfp_whoxy
- sfp_fsecure_riddler, sfp_projectdiscovery

Each deletion covered the module file, its unit test, and its
integration test. setup.cfg had no per-file-ignores entries for
these modules, so no config changes were needed.

sfp_template.py is preserved — it is the new-module reference file
and includes every dataSource.model value as documentation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Tier 2 — dispatch parallel research + produce decisions table

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md`

This task does NOT delete any modules. It produces the decisions table and commits it. The user reviews the table; Task 3 executes the approved deletions in a separate commit.

- [ ] **Step 1: Get the Tier 2 candidate list**

Run:
```bash
grep -lE "FREE_AUTH_LIMITED|FREE_AUTH_UNLIMITED|FREE_NOAUTH_LIMITED" modules/sfp_*.py \
    | grep -v sfp_template \
    | sort > /tmp/tier2-candidates.txt
wc -l /tmp/tier2-candidates.txt
```

Expected: `78 /tmp/tier2-candidates.txt` (count was 78 at 2026-04-20). If the count is materially different, re-check whether Tier 1 was executed correctly — each removed Tier 1 file should reduce the total module count but not the FREE_* count.

- [ ] **Step 2: For each candidate, extract `meta.dataSource` fields the research will reference**

Run:
```bash
python3 <<'PYEOF'
import re
from pathlib import Path

with open("/tmp/tier2-candidates.txt") as f:
    paths = [line.strip() for line in f if line.strip()]

rows = []
for p in paths:
    src = Path(p).read_text()
    name = Path(p).stem  # sfp_<name>
    # Extract summary, website, model from the meta block
    summary = re.search(r"'summary':\s*\"([^\"]+)\"", src)
    website = re.search(r"'website':\s*\"([^\"]+)\"", src)
    model = re.search(r"'model':\s*\"(FREE_\w+)\"", src)
    api_hint = re.search(r"'apiKeyInstructions':\s*\[\s*\"([^\"]+)\"", src)
    rows.append({
        "module": name,
        "summary": summary.group(1) if summary else "",
        "website": website.group(1) if website else "",
        "model": model.group(1) if model else "?",
        "sign_up_url": api_hint.group(1) if api_hint else "",
    })

for r in rows:
    print(f"{r['module']}\t{r['model']}\t{r['website']}\t{r['summary']}")
PYEOF
```

Pipe the output to `/tmp/tier2-metadata.tsv`:
```bash
python3 ... | tee /tmp/tier2-metadata.tsv | head -3
```

This TSV is the seed for the research subagents — each subagent needs `module`, `website`, and `summary` to know what service to look up.

- [ ] **Step 3: Split the candidate list into 5 chunks for parallel dispatch**

Run:
```bash
split -n l/5 -a 1 -d /tmp/tier2-metadata.tsv /tmp/tier2-chunk-
ls -la /tmp/tier2-chunk-*
wc -l /tmp/tier2-chunk-*
```

Expected: 5 chunk files (`tier2-chunk-0` through `tier2-chunk-4`), each with ~15-16 rows. Total rows must equal the candidate count (78 at 2026-04-20).

- [ ] **Step 4: Dispatch 5 parallel research subagents**

Using the `Agent` tool with `subagent_type: general-purpose`, dispatch **5 subagents in parallel** (single message, 5 `Agent` tool-use blocks). Each subagent receives one chunk file and produces a partial markdown table.

Prompt template for each subagent (substitute `{CHUNK_PATH}` per dispatch):

```
You are researching a batch of SpiderFoot modules to determine whether their
upstream service is still usable with a free tier.

Working directory: /Users/olahjort/Projects/OhDeere/spiderfoot
Chunk file: {CHUNK_PATH}

## Input format (TSV)

Each line of the chunk file has: module<TAB>model<TAB>website<TAB>summary.

## Your job

For EACH line in the chunk, classify the module into exactly one bucket:

- DEAD: homepage 404s, DNS gone, or "service shut down" banner
- ACQUIRED: absorbed into a paid product; the ex-free API is gone
- PAYWALLED: free tier was removed since the module was written
- PUNITIVE-FREE: free tier exists but is <100 requests/month (not useful)
- USABLE-FREE: free tier works and gives >=1000 requests/month (or similar)

## Research method

For each module:
1. WebFetch the `website` URL. If 404/timeout → DEAD.
2. WebFetch `<website>/pricing` or the service's pricing page. Look for:
   - Free tier exists? Row-bound?
   - Sign-up blocked by paid plan? PAYWALLED.
3. If acquired — e.g., Clearbit is listed as "now part of HubSpot" — ACQUIRED.
4. If service explicitly advertises only commercial plans → PAYWALLED.
5. Otherwise USABLE-FREE.

Do NOT create accounts. Do NOT test endpoints. Rely only on public pages.

## Output format (markdown)

Produce ONLY a markdown table with one row per module. No preamble.

| Module | Service | Bucket | Evidence URL | Verdict | Notes |
|---|---|---|---|---|---|
| sfp_example | Example Inc | USABLE-FREE | https://example.com/pricing | keep | 10k req/mo free |

- Module: the sfp_<name> identifier from the chunk.
- Service: human-readable name (from the summary or the website's brand).
- Bucket: one of the 5 above, exact spelling.
- Evidence URL: the page that justifies the classification.
- Verdict: "keep" for USABLE-FREE, "remove" for the other four.
- Notes: one sentence with the key fact (e.g., "250 req/day free", "shut down 2023").

Include EVERY module from the chunk. If you cannot determine a bucket confidently,
mark Bucket=UNKNOWN and Verdict=keep and explain in Notes — the user will override.

## Constraints

- No code changes. No file edits. Research and reporting only.
- Wall-clock budget: ~5 minutes. If a fetch is slow, move on and mark UNKNOWN.
```

After all 5 subagents complete, collect their tables.

- [ ] **Step 5: Merge the partial tables**

Concatenate the 5 markdown tables into one master table, sorted alphabetically by module. Create the combined file:

```bash
cat > docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md <<'EOF'
# Tier 2 dead-module audit — decisions

**Audit date:** 2026-04-20
**Researched by:** parallel subagent dispatch across 78 FREE_AUTH_* / FREE_NOAUTH_LIMITED modules.
**Reviewer:** [user marks up any `keep`/`remove` overrides inline before Task 3 executes]

## Bucket definitions

- **DEAD** — DNS gone, 404, or explicit shut-down notice.
- **ACQUIRED** — absorbed into a paid product; ex-free API unavailable.
- **PAYWALLED** — free tier removed since the module was written.
- **PUNITIVE-FREE** — free tier exists but <100 requests/month.
- **USABLE-FREE** — free tier works, >=1000 requests/month (or similar).

Verdict is `keep` for USABLE-FREE and UNKNOWN (reviewer overrides if needed), `remove` for the other four buckets.

## Decisions

| Module | Service | Bucket | Evidence URL | Verdict | Notes |
|---|---|---|---|---|---|
EOF
```

Then append the merged rows (paste each subagent's rows, skip each table's header), sorted alphabetically. The Write or Edit tool can do this in a single file write.

- [ ] **Step 6: Commit the decisions table (no deletions yet)**

```bash
git add docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md
git commit -m "$(cat <<'EOF'
docs: add Tier 2 dead-module audit decisions

Research output for the 78 FREE_AUTH_* / FREE_NOAUTH_LIMITED
candidate modules identified in the dead-module-audit spec. Each
module classified into one of five buckets (DEAD, ACQUIRED,
PAYWALLED, PUNITIVE-FREE, USABLE-FREE) with an evidence URL.

This commit is decision-only; no modules are deleted. Task 3 of
the plan executes the approved removals after user review.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7: Pause for user approval**

Stop here and report to the user:
> "Tier 2 decisions table committed at `docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md`. Please review the verdicts. Any changes — override `remove` to `keep` or vice versa — edit the file inline and tell me to continue. Once you're happy, Task 3 executes the deletions based on the `remove` verdicts in the committed table."

Do not proceed to Task 3 until the user explicitly approves.

---

## Task 3: Tier 2 — execute approved deletions

**Files:**
- Delete: `modules/sfp_<name>.py` × N (one per `remove` verdict in the decisions table)
- Delete: `test/unit/modules/test_sfp_<name>.py` × N
- Delete: `test/integration/modules/test_sfp_<name>.py` × N
- Modify: `setup.cfg` (if any `per-file-ignores` entries reference these modules)

This task executes after the user approves Task 2's decisions table. The set of modules removed here is whatever has `Verdict = remove` in the committed `tier2-decisions.md`.

- [ ] **Step 1: Extract the approved removal list from the committed decisions table**

Run:
```bash
python3 <<'PYEOF'
import re
from pathlib import Path

text = Path("docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md").read_text()
# Parse markdown table rows: | sfp_foo | Service | BUCKET | url | remove | notes |
row_re = re.compile(r"^\|\s*(sfp_\w+)\s*\|[^|]*\|\s*([A-Z_-]+)\s*\|[^|]*\|\s*(remove|keep)\s*\|", re.MULTILINE)
matches = row_re.findall(text)
remove = [m for m in matches if m[2] == "remove"]
keep = [m for m in matches if m[2] == "keep"]

print(f"remove: {len(remove)}")
print(f"keep: {len(keep)}")
print(f"total: {len(matches)}")
for name, bucket, _ in remove:
    print(f"  {name}\t{bucket}")

# Write the approved removals to a file for the next step
with open("/tmp/tier2-removals.txt", "w") as f:
    for name, _, _ in remove:
        f.write(f"{name}\n")
PYEOF
```

Expected: a list printed with count. The count must be `len(matches) == 78` (total Tier 2 candidates — every module has a row and a verdict). If not, the decisions file is malformed; stop and ask the user to fix it.

Save the count. It determines how many file deletions are about to happen.

- [ ] **Step 2: Delete the approved modules + tests**

Run (substitute `$N` from step 1's file):
```bash
# Build the deletion command from /tmp/tier2-removals.txt
mapfile -t removals < /tmp/tier2-removals.txt
paths=()
for name in "${removals[@]}"; do
    paths+=("modules/${name}.py")
    paths+=("test/unit/modules/test_${name}.py")
    paths+=("test/integration/modules/test_${name}.py")
done
git rm --ignore-unmatch "${paths[@]}"
echo "Deleted: ${#removals[@]} modules, up to $((3 * ${#removals[@]})) files"
```

Expected: the output lists `rm '<path>'` for each existing file. `--ignore-unmatch` silently skips integration tests that never existed.

- [ ] **Step 3: Clean up `setup.cfg` per-file-ignores**

For each removed module name, check and remove any matching lines:
```bash
for name in "${removals[@]}"; do
    grep -n "${name}" setup.cfg || true
done
```

If any lines matched, use `Edit` to remove them individually from `setup.cfg`. Otherwise skip.

- [ ] **Step 4: Run the full test suite**

Run: `./test/run`

Expected: pytest reports `X passed, 35 skipped` where `X` is the post-Tier-1 count minus all Tier 2 tests. Flake8 clean. No test failures. No `ImportError` for any removed module.

- [ ] **Step 5: Smoke-test scanner**

Run:
```bash
SPIDERFOOT_LOG_FORMAT=json timeout 15 python3 ./sf.py -M 2>&1 | head -5
```

Expected: JSON output listing remaining modules. None of the Tier 2 removals should appear.

- [ ] **Step 6: Commit**

```bash
git commit -m "$(cat <<'EOF'
modules: remove dead / paywalled modules (Tier 2)

Applies the removal verdicts from the Tier 2 decisions table at
docs/superpowers/specs/2026-04-20-dead-module-audit-tier2-decisions.md
(approved 2026-04-20). Each removed module's upstream service was
classified as DEAD, ACQUIRED, PAYWALLED, or PUNITIVE-FREE during
the audit.

Deleted N modules (see decisions table for per-module evidence).
Each deletion covered the module file, its unit test, and its
integration test.

Surviving modules retain the USABLE-FREE classification and go
into the Module Inventory section added to CLAUDE.md in Task 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Substitute `N` with the actual count of removed modules. Update the commit message before running the `git commit` — do not commit with the literal `N` placeholder.

---

## Task 4: Tier 3 — document the surviving module inventory in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Generate the surviving module inventory**

Run:
```bash
python3 <<'PYEOF'
import re
from pathlib import Path

surviving = sorted(Path("modules").glob("sfp_*.py"))
surviving = [p for p in surviving if p.stem not in ("sfp__stor_db", "sfp__stor_stdout", "sfp_template")]

buckets = {"FREE_NOAUTH_UNLIMITED": [], "FREE_NOAUTH_LIMITED": [],
           "FREE_AUTH_UNLIMITED": [], "FREE_AUTH_LIMITED": []}
unknown = []
for p in surviving:
    src = p.read_text()
    m = re.search(r"'model':\s*\"(FREE_\w+|COMMERCIAL_ONLY|PRIVATE_ONLY)\"", src)
    if m and m.group(1) in buckets:
        buckets[m.group(1)].append(p.stem)
    else:
        unknown.append(p.stem)

total = sum(len(v) for v in buckets.values()) + len(unknown)
print(f"Total surviving non-storage modules: {total}")
for name, items in buckets.items():
    print(f"\n## {name} ({len(items)})")
    for m in items:
        print(f"- {m}")
if unknown:
    print(f"\n## UNKNOWN / not classified ({len(unknown)})")
    for m in unknown:
        print(f"- {m}")
PYEOF
```

Capture the output — this is the core of the `CLAUDE.md` addition. Note the `total` so you can include it in the section.

- [ ] **Step 2: Append the Module Inventory section to `CLAUDE.md`**

Open `CLAUDE.md` and locate the "Environment variables (runtime)" section. Add a new section **before** the "Conventions to follow" section (which is always last).

Use the Edit tool to insert this block (fill in the module lists from Step 1's output; keep the `## FREE_NOAUTH_UNLIMITED (N)` headings exactly as printed):

```markdown
## Module inventory (audited 2026-04-20)

Dead-module audit — `docs/superpowers/specs/2026-04-20-dead-module-audit-design.md` — culled all `COMMERCIAL_ONLY` / `PRIVATE_ONLY` modules and all `FREE_AUTH_*` / `FREE_NOAUTH_LIMITED` modules whose services were dead, acquired-and-paywalled, or had punitive free tiers. The surviving modules are listed below, grouped by their `meta.dataSource.model` classification. Every addition after this date must fit one of the four FREE_* buckets; `COMMERCIAL_ONLY` / `PRIVATE_ONLY` modules are rejected on principle.

### FREE_NOAUTH_UNLIMITED (N)

[paste the bucket members from Step 1]

### FREE_NOAUTH_LIMITED (N)

[paste]

### FREE_AUTH_UNLIMITED (N)

[paste]

### FREE_AUTH_LIMITED (N)

[paste]

Total surviving non-storage modules: N.
```

Replace every `N` and every `[paste]` with the actual numbers and lists from Step 1.

- [ ] **Step 3: Verify `CLAUDE.md` still makes sense**

Run:
```bash
python3 -c "
import re
text = open('CLAUDE.md').read()
assert 'Module inventory (audited 2026-04-20)' in text, 'Section missing'
assert '## Conventions to follow' in text, 'Section deleted accidentally'
# Check ordering: Module inventory must appear before Conventions
inv_pos = text.index('Module inventory (audited 2026-04-20)')
conv_pos = text.index('Conventions to follow')
assert inv_pos < conv_pos, 'Module inventory must come before Conventions'
print('CLAUDE.md structure OK')
"
```

Expected: `CLAUDE.md structure OK`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document surviving module inventory after dead-module audit

Adds a Module Inventory section to CLAUDE.md listing the N
modules that survived the 2026-04-20 dead-module audit, grouped
by meta.dataSource.model. Acts as an anti-regression fence —
any future module PR that doesn't fit one of the four FREE_*
buckets gets flagged during review.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Replace `N` with the actual module count from Step 1 before running.

---

## Task 5: Final verification

- [ ] **Step 1: Confirm total test count delta is reasonable**

Run: `./test/run`

Expected: flake8 clean; pytest passes. The count dropped from 1615 baseline to whatever's left after all tier deletions. Document the final count so we have a reference for the next cull.

- [ ] **Step 2: Final smoke scan against a benign target**

Run:
```bash
rm -f /tmp/sf-final-smoke.log
SPIDERFOOT_LOG_FORMAT=json timeout 45 python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve 2>/tmp/sf-final-smoke.log || true
echo "--- events produced ---"
grep -c '"logger": "spiderfoot' /tmp/sf-final-smoke.log
echo "--- import errors ---"
grep -iE "ImportError|ModuleNotFoundError" /tmp/sf-final-smoke.log || echo "(none)"
rm -f /tmp/sf-final-smoke.log
```

Expected: positive event count, `(none)` for import errors.

- [ ] **Step 3: Verify the Phase 1 item 1 invariants still hold**

Run: `python3 -m pytest test/unit/spiderfoot/test_event_types.py test/unit/spiderfoot/test_spiderfootevent.py -v`

Expected: all 32+ tests pass (this is the typed-event-model foundation we're standing on; its invariants must not regress).

- [ ] **Step 4: Report completion**

Summary: three implementation commits landed — Tier 1 (10 modules), Tier 2 (N modules), Tier 3 (`CLAUDE.md` inventory). Total modules removed: M. Total tests removed: T. Final module count: 233 − M.
