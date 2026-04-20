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

## Environment variables (runtime)

`sf.py` reads `SPIDERFOOT_DATA`, `SPIDERFOOT_LOGS`, `SPIDERFOOT_CACHE` for data/log/cache paths (see Dockerfile). Two additional env vars control the logging pipeline (see `spiderfoot/logger.py`):

- `SPIDERFOOT_LOG_FORMAT={json,text}` — deterministic override for the console formatter. When unset or set to anything else, the format is auto-selected: text when `sys.stdout.isatty()`, JSON otherwise. The shipped `Dockerfile` sets this to `json`.
- `SPIDERFOOT_LOG_FILES={true,false}` — when `false`, the two `TimedRotatingFileHandler` instances under `$SPIDERFOOT_LOGS` are not attached; stdout + the SQLite per-scan log become the only log destinations. The shipped `Dockerfile` sets this to `false` so Loki is the single authoritative log store. Default (unset) preserves the historical behavior for `./sf.py` runs from source.

The per-scan SQLite log (`SpiderFootSqliteLogHandler`) is not controlled by these vars — it's product functionality that feeds the scan UI's "Log" tab.

## Module inventory (audited 2026-04-20)

The dead-module audit (`docs/superpowers/specs/2026-04-20-dead-module-audit-design.md`) culled all `COMMERCIAL_ONLY` / `PRIVATE_ONLY` modules (Tier 1, commit `c50d7bca`) and all `FREE_AUTH_*` / `FREE_NOAUTH_LIMITED` modules whose services were dead, acquired-and-paywalled, or had punitive free tiers (Tier 2, commit `2755f83e`). 48 modules total were removed. The **182** surviving non-storage modules are listed below, grouped by their `meta.dataSource.model` classification.

**Policy:** New modules must fit one of the four `FREE_*` buckets. Modules requiring paid or private subscriptions (`COMMERCIAL_ONLY`, `PRIVATE_ONLY`) are rejected — the underlying services change hands too often and the maintenance burden outweighs the signal. Re-add a rejected category only if the user's scanning needs genuinely require it.

**Known gaps (backlog):**
- **Web search:** Both `sfp_bingsearch` (Microsoft retired the Bing Web Search API in 2025) and the Google Custom Search modules (`sfp_googlesearch`, `sfp_pastebin`) were removed. No surviving module queries a general-purpose web search engine. A replacement (self-hosted SearXNG, DuckDuckGo HTML scrape, or similar) is an open need for OSINT investigations that traverse search engines.
- **Orphaned event types:** A handful of event types in `spiderfoot/event_types.py` (e.g. `HASH_COMPROMISED`, `PHONE_NUMBER_COMPROMISED`) have no remaining producer after the audit. Deferred to a future registry-sweep spec; leaving them in costs nothing at runtime.

### FREE_NOAUTH_UNLIMITED (88)

- sfp_adguard_dns
- sfp_ahmia
- sfp_alienvaultiprep
- sfp_archiveorg
- sfp_arin
- sfp_azureblobstorage
- sfp_bgpview
- sfp_blockchain
- sfp_blocklistde
- sfp_botvrij
- sfp_callername
- sfp_cinsscore
- sfp_cleanbrowsing
- sfp_cleantalk
- sfp_cloudflaredns
- sfp_coinblocker
- sfp_commoncrawl
- sfp_crobat_api
- sfp_crt
- sfp_crxcavator
- sfp_cybercrimetracker
- sfp_debounce
- sfp_digitaloceanspace
- sfp_dns_for_family
- sfp_dnsdumpster
- sfp_dronebl
- sfp_duckduckgo
- sfp_emailformat
- sfp_emergingthreats
- sfp_etherscan
- sfp_flickr
- sfp_fortinet
- sfp_github
- sfp_google_tag_manager
- sfp_googleobjectstorage
- sfp_gravatar
- sfp_greensnow
- sfp_grep_app
- sfp_h1nobbdde
- sfp_hackertarget
- sfp_isc
- sfp_keybase
- sfp_maltiverse
- sfp_mnemonic
- sfp_multiproxy
- sfp_myspace
- sfp_onioncity
- sfp_onionsearchengine
- sfp_openbugbounty
- sfp_opendns
- sfp_opennic
- sfp_openphish
- sfp_openstreetmap
- sfp_phishstats
- sfp_phishtank
- sfp_psbdmp
- sfp_punkspider
- sfp_quad9
- sfp_reversewhois
- sfp_ripe
- sfp_robtex
- sfp_s3bucket
- sfp_searchcode
- sfp_skymem
- sfp_slideshare
- sfp_sorbs
- sfp_spamcop
- sfp_spamhaus
- sfp_stevenblack_hosts
- sfp_sublist3r
- sfp_surbl
- sfp_talosintel
- sfp_threatcrowd
- sfp_threatfox
- sfp_threatminer
- sfp_torch
- sfp_torexits
- sfp_trumail
- sfp_twitter
- sfp_uceprotect
- sfp_urlscan
- sfp_venmo
- sfp_voipbl
- sfp_vxvault
- sfp_wikileaks
- sfp_wikipediaedits
- sfp_yandexdns
- sfp_zoneh

### FREE_NOAUTH_LIMITED (5)

- sfp_abstractapi
- sfp_botscout
- sfp_comodo
- sfp_gleif
- sfp_stackoverflow

### FREE_AUTH_UNLIMITED (9)

- sfp_abusech
- sfp_apple_itunes
- sfp_circllu
- sfp_dnsgrep
- sfp_googlesafebrowsing
- sfp_honeypot
- sfp_hybrid_analysis
- sfp_leakix
- sfp_wigle

### FREE_AUTH_LIMITED (26)

- sfp_abuseipdb
- sfp_abusix
- sfp_adblock
- sfp_alienvault
- sfp_builtwith
- sfp_censys
- sfp_certspotter
- sfp_fullcontact
- sfp_fullhunt
- sfp_googlemaps
- sfp_hostio
- sfp_iknowwhatyoudownload
- sfp_ipapico
- sfp_ipapicom
- sfp_ipinfo
- sfp_ipqualityscore
- sfp_ipregistry
- sfp_koodous
- sfp_metadefender
- sfp_nameapi
- sfp_networksdb
- sfp_pulsedive
- sfp_securitytrails
- sfp_socialprofiles
- sfp_virustotal
- sfp_xforce

### UNKNOWN / not classified (54)

These modules do not declare a `meta.dataSource.model` (they are local analysis/processing modules — regex extractors, DNS helpers, sslcert, spider, portscan, and the `sfp_tool_*` wrappers around external CLI tools — not external API integrations). They are out of scope for the FREE_* policy but are listed here so future contributors can confirm at a glance that a new module without a `model` field is similarly local in nature.

- sfp_accounts
- sfp_base64
- sfp_binstring
- sfp_bitcoin
- sfp_company
- sfp_cookie
- sfp_countryname
- sfp_creditcard
- sfp_crossref
- sfp_customfeed
- sfp_dnsbrute
- sfp_dnscommonsrv
- sfp_dnsneighbor
- sfp_dnsraw
- sfp_dnsresolve
- sfp_dnszonexfer
- sfp_email
- sfp_errors
- sfp_ethereum
- sfp_filemeta
- sfp_hashes
- sfp_hosting
- sfp_iban
- sfp_intfiles
- sfp_junkfiles
- sfp_names
- sfp_pageinfo
- sfp_pgp
- sfp_phone
- sfp_portscan_tcp
- sfp_similar
- sfp_social
- sfp_spider
- sfp_sslcert
- sfp_strangeheaders
- sfp_subdomain_takeover
- sfp_tldsearch
- sfp_tool_cmseek
- sfp_tool_dnstwist
- sfp_tool_nbtscan
- sfp_tool_nmap
- sfp_tool_nuclei
- sfp_tool_onesixtyone
- sfp_tool_retirejs
- sfp_tool_snallygaster
- sfp_tool_testsslsh
- sfp_tool_trufflehog
- sfp_tool_wafw00f
- sfp_tool_wappalyzer
- sfp_tool_whatweb
- sfp_webanalytics
- sfp_webframework
- sfp_webserver
- sfp_whois

## Conventions to follow

- When adding a module, register the `sfp_*.py` filename as the module name; the class inside must match the filename (the loader uses the filename, not the class). Start from `sfp_template.py` so the meta block is filled in correctly — the UI depends on it.
- Don't instantiate your own logger in a module. `SpiderFootPlugin` provides `self.debug/info/error` that attach the current `scanId`.
- Flake8 is enforced in CI on every PR and by `./test/run`; per-file exemptions are listed in `setup.cfg` (`per-file-ignores`).
