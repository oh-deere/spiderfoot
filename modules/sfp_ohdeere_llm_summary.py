# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_llm_summary
# Purpose:      Post-scan summarizer. Reads all scan events from SpiderFoot's
#               SQLite in finish(), builds a structured prompt, emits one
#               DESCRIPTION_ABSTRACT via the ohdeere-llm-gateway. Sixth
#               consumer of spiderfoot/ohdeere_client.py.
# Introduced:   2026-04-20
# Licence:      MIT
# -------------------------------------------------------------------------------

from collections import Counter, defaultdict

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import OhDeereClientError, get_client
from spiderfoot.ohdeere_llm import (
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
    run_prompt,
)


_PROMPT_TEMPLATE = (
    "You are summarizing an OSINT reconnaissance scan. Produce a concise, "
    "neutrally-worded summary (3-5 paragraphs) covering:\n"
    "- What the scan target was\n"
    "- Major entities discovered (domains, emails, people, companies)\n"
    "- Notable risk signals (malicious indicators, breach exposures, "
    "vulnerabilities)\n"
    "- Areas of uncertainty or where human review is warranted\n\n"
    "Do NOT draw legal conclusions or attribute intent. Use phrases like "
    "\"appears to\", \"was found to reference\", \"may be associated with\".\n\n"
    "Scan target: {target}\n"
    "Event counts by type:\n"
    "{type_counts}\n\n"
    "Representative events (max {max_per_type} per type):\n"
    "{event_samples}\n\n"
    "Summary:\n"
)


class sfp_ohdeere_llm_summary(SpiderFootPlugin):

    meta = {
        "name": "OhDeere LLM Summary",
        "summary": "Post-scan summarizer. Reads all events from the scan, "
                   "sends a structured prompt to ohdeere-llm-gateway, emits "
                   "one DESCRIPTION_ABSTRACT with the model's summary.",
        "flags": [],
        "useCases": ["Investigate", "Passive"],
        "categories": ["Content Analysis"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/llm-gateway/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/llm-gateway/"],
            "description": "Self-hosted Ollama behind an async job queue. "
                           "Requires the OhDeere client-credentials token "
                           "(OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET env "
                           "vars) with llm:query scope.",
        },
    }

    opts = {
        "llm_base_url": "https://llm.ohdeere.internal",
        "model": "gemma4:e4b",
        "timeout_s": 300,
        "max_events_per_type": 25,
    }

    optdescs = {
        "llm_base_url": "Base URL of the ohdeere-llm-gateway.",
        "model": "Ollama model tag (default gemma4:e4b). Upgrade to a larger "
                 "model for better summary quality.",
        "timeout_s": "Per-job wall-clock timeout in seconds (default 300).",
        "max_events_per_type": "Max representative events per event type in "
                               "the prompt (default 25).",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._summarized = False
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["ROOT"]

    def producedEvents(self):
        return ["DESCRIPTION_ABSTRACT"]

    def handleEvent(self, event):
        return

    def finish(self):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if self._summarized:
            return
        self._summarized = True

        scan_id = self.getScanId()
        db = self._get_db()
        events = db.scanResultEvent(scan_id)
        target = self._scan_target(scan_id, db)
        source_event = self._synthesize_root_event(target)

        if not events:
            self._emit(
                source_event,
                "DESCRIPTION_ABSTRACT",
                "No events were produced in this scan.",
            )
            return

        prompt = self._build_prompt(events, target)
        try:
            summary = run_prompt(
                prompt,
                base_url=self.opts["llm_base_url"].rstrip("/"),
                model=self.opts["model"],
                timeout_s=int(self.opts["timeout_s"]),
            )
        except OhDeereLLMTimeout as exc:
            self.error(f"OhDeere LLM summary timeout: {exc}")
            self.errorState = True
            return
        except OhDeereLLMFailure as exc:
            self.error(f"OhDeere LLM summary failed: {exc}")
            self.errorState = True
            return
        except OhDeereClientError as exc:
            self.error(f"OhDeere LLM summary request failed: {exc}")
            self.errorState = True
            return

        self._emit(source_event, "DESCRIPTION_ABSTRACT", summary)

    def _build_prompt(self, events, target):
        by_type = defaultdict(list)
        counts = Counter()
        for row in events:
            evt_type = row[4]
            counts[evt_type] += 1
            by_type[evt_type].append(row)

        top_types = [t for t, _ in counts.most_common(20)]
        type_counts_str = "\n".join(
            f"  {t}: {counts[t]}" for t in top_types
        )

        max_per_type = int(self.opts["max_events_per_type"])
        sample_lines = []
        for evt_type in top_types:
            rows = by_type[evt_type][:max_per_type]
            for row in rows:
                data = (row[1] or "")[:200]
                source_data = (row[2] or "")[:100]
                module = row[3]
                sample_lines.append(
                    f"[{evt_type}] {data} (from {module}; "
                    f"source: {source_data})"
                )

        prompt = _PROMPT_TEMPLATE.format(
            target=target,
            type_counts=type_counts_str,
            max_per_type=max_per_type,
            event_samples="\n".join(sample_lines),
        )
        if len(prompt) > 150_000:
            return prompt[:150_000]
        return prompt

    def _get_db(self):
        # __sfdb__ is not name-mangled (trailing __) and is the normal
        # production attribute set by SpiderFootPlugin.setDbh(). Tests may
        # inject via the ``_SpiderFootPlugin__sfdb__`` attribute, so fall
        # back to that when the primary slot is unset.
        db = getattr(self, "__sfdb__", None)
        if db is None:
            return getattr(self, "_SpiderFootPlugin__sfdb__", None)
        return db

    def _scan_target(self, scan_id, db=None):
        if db is None:
            db = self._get_db()
        try:
            info = db.scanInstanceGet(scan_id)
            if info and len(info) > 1 and info[1]:
                return info[1]
        except Exception:
            pass
        return "unknown target"

    def _synthesize_root_event(self, target):
        return SpiderFootEvent("ROOT", target, "", "")

    def _emit(self, source_event, event_type, data):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_llm_summary class
