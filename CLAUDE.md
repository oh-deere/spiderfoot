# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope note

This directory is a checkout of the upstream `smicallef/spiderfoot` OSINT tool. It is **not** an OhDeere service — the Java 25 / Spring Boot 4 rules in the parent `../CLAUDE.md` do not apply here. This project targets **Python 3.7+** and is MIT-licensed.

## Common commands

Run the web UI (default dev target):

```
python3 ./sf.py -l 127.0.0.1:5001
```

Run a headless scan from the CLI (no web server): use `sf.py` with `-s TARGET` and module/type selectors. Useful flags: `-m mod1,mod2`, `-t TYPE1,TYPE2`, `-u {all,footprint,investigate,passive}`, `-x` (strict), `-o {tab,csv,json}`, `-M` to list modules, `-T` to list event types, `-C scanID` to run correlations against an existing scan.

Interactive CLI client against a running web server: `python3 ./sfcli.py -s http://127.0.0.1:5001/`.

Lint + unit/integration tests (mirrors CI — run from repo root):

```
./test/run
```

Full test run including module integration tests (hits third-party APIs, slow):

```
python3 -m pytest -n auto --dist loadfile --durations=5 --cov-report html --cov=. .
```

Run a single test file or test: `python3 -m pytest test/unit/test_spiderfoot.py` / `python3 -m pytest test/unit/test_spiderfoot.py::TestSpiderFoot::test_name`.

Lint only: `python3 -m flake8 . --count --show-source --statistics` (config in `setup.cfg`, max line length 120, plus flake8-bugbear/quotes/sfs/simplify plugins).

Acceptance tests (Robot Framework + headless browser) live in `test/acceptance/` and require the web server running on `:5001`; see `test/README.md`.

Install deps: `pip3 install -r requirements.txt`; for tests add `pip3 install -r test/requirements.txt`.

## Architecture

Entry points at the repo root are thin orchestrators; the reusable code lives in the `spiderfoot/` package and the plugins live in `modules/`.

- `sf.py` — main entry. Parses CLI args, loads every `modules/sfp_*.py` into a dict via `SpiderFootHelpers.loadModulesAsDict`, loads every `correlations/*.yaml` rule, initializes `SpiderFootDb` (SQLite at `$SPIDERFOOT_DATA/spiderfoot.db`, default under the user data dir), then either starts `SpiderFootWebUi` (CherryPy) via `start_web_server` or kicks off `SpiderFootScanner` from `sfscan.py`.
- `sfscan.py` — `SpiderFootScanner` builds a `SpiderFootTarget`, instantiates the selected module classes, wires them together via `SpiderFootThreadPool` and event queues, and drives the scan lifecycle. Modules run concurrently (default 3, `_maxthreads`). Post-scan, `SpiderFootCorrelator` runs the YAML rules against stored events.
- `sflib.py` — `SpiderFoot` class: shared HTTP/DNS/parsing helpers used by every module (fetch with proxy/SOCKS, cache, URL parsing, publicsuffix, etc.). Modules receive this as `self.sf`.
- `sfwebui.py` — CherryPy app exposing the scan/config/results UI and JSON endpoints. Uses Mako templates from `spiderfoot/templates/` and static assets from `spiderfoot/static/`.
- `sfcli.py` — standalone REPL that talks to the web UI's HTTP API; not used during in-process scans.

### Module plugin model (the key abstraction)

Every file in `modules/` named `sfp_*.py` defines a class that inherits from `SpiderFootPlugin` (see `spiderfoot/plugin.py`). Modules communicate only via a **publisher/subscriber event bus**:

- `watchedEvents()` returns the event types (e.g. `INTERNET_NAME`, `IP_ADDRESS`, `TCP_PORT_OPEN_BANNER`) the module consumes.
- `producedEvents()` returns the types it emits.
- `handleEvent(event)` is called by the scanner whenever a matching event is produced by any other module; the module calls `self.notifyListeners(SpiderFootEvent(...))` to publish.
- `setup(sf, userOpts)` receives the shared `SpiderFoot` helper and merged user/default options; `meta`, `opts`, `optdescs` on the class drive UI rendering and config persistence.

`sfp_template.py` is the reference — copy it when adding modules. Two storage sinks are special: `sfp__stor_db` (writes every event to SQLite) and `sfp__stor_stdout` (CLI output). Events form a parent chain (`event.sourceEvent`), which is what enables the `source.`, `child.`, `entity.` prefixes in correlation rules.

Module metadata fields that matter beyond description: `flags` (`apikey`, `slow`, `errorprone`, `invasive`, `tool`), `useCases` (`Footprint` / `Investigate` / `Passive`), and `categories` (see `sfp_template.py` for the allowed list). These drive module auto-selection when the user picks `-u` or a use case in the UI.

### Correlation engine

YAML files under `correlations/` are loaded at startup and validated by `SpiderFootCorrelator` (`spiderfoot/correlation.py`). Rules have `collections` → optional `aggregation` → optional `analysis` → `headline`. Results land in `tbl_scan_correlation_results` / `tbl_scan_correlation_results_events` in the same SQLite DB. Invalid YAML aborts startup — fix the rule or remove it. `correlations/README.md` has the full rule reference; `correlations/template.yaml` is the starting point for new rules.

### Data layout

SQLite schema lives entirely in `spiderfoot/db.py` (tables for scans, instances, events, config, correlation results). There are no migrations — `SpiderFootDb(init=True)` creates the schema if missing. Event-type metadata (including which types are "entities" for correlation `entity.` prefixing) is defined in the same file; consult it when adding new event types.

### Tests layout

- `test/unit/` — unit tests for `spiderfoot/` core and for each module (`test/unit/modules/`).
- `test/integration/` — integration tests for `sf.py`, `sfcli.py`, `sfwebui.py`; `test/integration/modules/` hits real third-party APIs and is excluded from the default `./test/run`.
- `test/acceptance/` — Robot Framework end-to-end tests against a live web server.
- `test/conftest.py` provides the `default_options` / `web_default_options` / `cli_default_options` fixtures most tests rely on and uses a separate `spiderfoot.test.db` file so tests don't touch real scan data.

## Conventions to follow

- When adding a module, register the `sfp_*.py` filename as the module name; the class inside must match the filename (the loader uses the filename, not the class). Start from `sfp_template.py` so the meta block is filled in correctly — the UI depends on it.
- Don't instantiate your own logger in a module. `SpiderFootPlugin` provides `self.debug/info/error` that attach the current `scanId`.
- Flake8 is enforced in CI on every PR and by `./test/run`; per-file exemptions are listed in `setup.cfg` (`per-file-ignores`).
