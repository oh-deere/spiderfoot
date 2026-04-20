# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_llm_translate
# Purpose:      Translate non-English content events (LEAKSITE_CONTENT,
#               DARKNET_MENTION_CONTENT, RAW_RIR_DATA) to English at scan
#               end via ohdeere-llm-gateway. Buffers during the scan,
#               filters with a stopword heuristic, translates surviving
#               items in finish(), re-emits with the same event type as
#               child events of the originals.
# Introduced:   2026-04-20
# Licence:      MIT
# -------------------------------------------------------------------------------

import re

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import OhDeereClientError, get_client
from spiderfoot.ohdeere_llm import (
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
    run_prompt,
)


_STOPWORDS = (
    "the", "and", "of", "to", "a", "in", "is", "for", "on",
    "that", "with", "as", "this", "by", "be",
)

_PROMPT_TEMPLATE = (
    "Translate the following text to English. Preserve technical terms, "
    "URLs, email addresses, IP addresses, and proper nouns as-is. If the "
    "text is already in English, return it unchanged. Do not add "
    "commentary, disclaimers, or notes about the translation — output "
    "only the translated text.\n\n"
    "---BEGIN TEXT---\n"
    "{content}\n"
    "---END TEXT---\n"
)


class sfp_ohdeere_llm_translate(SpiderFootPlugin):

    meta = {
        "name": "OhDeere LLM Translate",
        "summary": "Translate non-English content event data to English at "
                   "scan end using ohdeere-llm-gateway. Watches content-heavy "
                   "events, re-emits translated versions as child events.",
        "flags": [],
        "useCases": ["Investigate", "Passive"],
        "categories": ["Content Analysis"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/llm-gateway/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/llm-gateway/"],
            "description": "Self-hosted Ollama behind an async job queue. "
                           "Requires the OhDeere client-credentials token "
                           "with llm:query scope.",
        },
    }

    opts = {
        "llm_base_url": "https://llm.ohdeere.internal",
        "model": "gemma3:4b",
        "timeout_s": 120,
        "max_content_length": 15000,
        "max_events": 20,
        "skip_english": True,
    }

    optdescs = {
        "llm_base_url": "Base URL of the ohdeere-llm-gateway.",
        "model": "Ollama model tag (default gemma3:4b).",
        "timeout_s": "Per-translation wall-clock timeout in seconds.",
        "max_content_length": "Max characters to translate per event "
                              "(default 15000).",
        "max_events": "Max events to translate per scan (default 20).",
        "skip_english": "When True, skip events whose content already appears "
                        "English via a stopword heuristic (default True).",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._translated = False
        self._buffer = []
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"]

    def producedEvents(self):
        return ["LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"]

    def handleEvent(self, event):
        if self._client.disabled or self.errorState:
            return
        content = event.data or ""
        self._buffer.append((event, content))

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
                self.debug(
                    f"hit max_events={max_events}; dropping remainder"
                )
                break
            if skip_english and self._is_probably_english(content):
                continue
            truncated = content[:max_chars]
            prompt = _PROMPT_TEMPLATE.format(content=truncated)
            try:
                translated = run_prompt(
                    prompt,
                    base_url=self.opts["llm_base_url"].rstrip("/"),
                    model=self.opts["model"],
                    timeout_s=int(self.opts["timeout_s"]),
                )
            except OhDeereLLMTimeout as exc:
                self.error(f"OhDeere LLM translate timeout: {exc}")
                self.errorState = True
                return
            except OhDeereLLMFailure as exc:
                self.error(f"OhDeere LLM translate failed: {exc}")
                self.errorState = True
                return
            except OhDeereClientError as exc:
                self.error(f"OhDeere LLM translate request failed: {exc}")
                self.errorState = True
                return
            self._emit(source_event, source_event.eventType, translated)
            processed += 1

    def _is_probably_english(self, text):
        sample = text[:4000].lower()
        count = sum(
            len(re.findall(rf"\b{w}\b", sample)) for w in _STOPWORDS
        )
        return count >= 3

    def _emit(self, source_event, event_type, data):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_llm_translate class
