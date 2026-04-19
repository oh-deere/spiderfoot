import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Union

from spiderfoot.event_types import EVENT_TYPES, EventType

_log = logging.getLogger("spiderfoot.event")

_EventTypeArg = Union[str, EventType]

# Fields whose value must remain a 0-100 int across the object's life.
# The dataclass-generated __init__ only runs validation once; test
# suite also exercises evt.confidence = bad_value etc. post-construction,
# so __setattr__ below re-runs validation on every assignment to these.
_VALIDATED_RANGE_FIELDS = frozenset({"confidence", "visibility", "risk"})


@dataclass(slots=True, eq=False)
class SpiderFootEvent:
    """SpiderFootEvent object representing identified data and associated metadata.

    Attributes:
        eventType: Event type, e.g. URL_FORM, RAW_DATA. Accepted as
            either ``str`` or ``EventType`` at construction; stored
            internally as whichever type the caller passed (``str``
            for unregistered types, ``EventType`` for registered ones).
            ``EventType`` is a ``str`` mixin, so string comparisons
            keep working either way.
        data: Event data, e.g. a URL, port number, webpage content.
        module: Module which produced this event.
        sourceEvent: The event that triggered this one (``None`` only
            for ``ROOT`` events).
        generated: Creation time in Unix seconds.
        confidence: 0-100, default 100.
        visibility: 0-100, default 100.
        risk: 0-100, default 0.
        sourceEventHash: SHA256 hash of ``sourceEvent`` (``"ROOT"`` for
            root events).
        moduleDataSource: Free-form tag describing the upstream data
            source. Mutable post-construction by modules.
        actualSource: Free-form pointer to the parent event's value.
            Mutable post-construction by modules.
        hash: SHA256 identity hash, or ``"ROOT"`` for root events.
    """

    eventType: _EventTypeArg
    data: str
    module: str
    sourceEvent: Optional["SpiderFootEvent"]
    generated: float = field(default_factory=time.time)
    confidence: int = 100
    visibility: int = 100
    risk: int = 0
    sourceEventHash: str = field(init=False, default="")
    moduleDataSource: Optional[str] = None
    actualSource: Optional[str] = None
    _id: str = field(init=False, repr=False, default="")

    def __post_init__(self) -> None:
        # --- eventType normalization + soft validation ---
        if not isinstance(self.eventType, str):
            raise TypeError(
                f"eventType is {type(self.eventType)}; expected str()"
            )
        if not self.eventType:
            raise ValueError("eventType is empty")

        normalized: _EventTypeArg
        try:
            normalized = EventType(str(self.eventType))
        except ValueError:
            _log.warning(
                "unknown eventType=%r emitted by module=%r",
                str(self.eventType), self.module,
            )
            normalized = str(self.eventType)
        self.eventType = normalized

        # --- data validation (existing behaviour, unchanged) ---
        if not isinstance(self.data, str):
            raise TypeError(f"data is {type(self.data)}; expected str()")
        if not self.data:
            raise ValueError(f"data is empty: '{self.data!s}'")

        # --- module validation (existing behaviour, unchanged) ---
        if not isinstance(self.module, str):
            raise TypeError(f"module is {type(self.module)}; expected str()")
        if not self.module and self.eventType != "ROOT":
            raise ValueError("module is empty")

        # Note: confidence/visibility/risk range checks run via
        # __setattr__ below (which fires during the dataclass-generated
        # __init__), so they're already validated by the time we reach
        # this point.

        # --- sourceEvent wiring + hash ---
        if self.eventType == "ROOT":
            self.sourceEvent = None
            self.sourceEventHash = "ROOT"
        else:
            if not isinstance(self.sourceEvent, SpiderFootEvent):
                raise TypeError(
                    f"sourceEvent is {type(self.sourceEvent)}; "
                    "expected SpiderFootEvent()"
                )
            self.sourceEventHash = self.sourceEvent.hash

        # --- identity ---
        self._id = (
            f"{self.eventType}{self.generated}{self.module}"
            f"{random.SystemRandom().randint(0, 99999999)}"
        )

        # --- soft data validation via registry hook ---
        if isinstance(self.eventType, EventType):
            entry = EVENT_TYPES.get(self.eventType)
            if entry is not None and entry.validator is not None:
                try:
                    ok = entry.validator(self.data)
                except Exception as exc:
                    _log.warning(
                        "validation failed for eventType=%s (validator "
                        "raised %s); event published anyway",
                        self.eventType, exc,
                    )
                else:
                    if not ok:
                        _log.warning(
                            "validation failed for eventType=%s data=%r; "
                            "event published anyway",
                            self.eventType, self.data,
                        )

    def __setattr__(self, name: str, value) -> None:
        # NB: use object.__setattr__ rather than super().__setattr__.
        # @dataclass(slots=True) rewrites the class after decoration, so
        # a zero-arg super() call captures the pre-rewrite class cell
        # and raises TypeError("obj is not an instance...").
        if name in _VALIDATED_RANGE_FIELDS:
            if not isinstance(value, int):
                raise TypeError(f"{name} is {type(value)}; expected int()")
            if not 0 <= value <= 100:
                raise ValueError(f"{name} value is {value}; expected 0 - 100")
        object.__setattr__(self, name, value)

    @property
    def hash(self) -> str:
        """Unique SHA256 hash of the event, or ``"ROOT"``.

        Returns:
            str: SHA256 hex digest, or ``"ROOT"`` for root events.
        """
        if self.eventType == "ROOT":
            return "ROOT"
        digest_str = self._id.encode("raw_unicode_escape")
        return hashlib.sha256(digest_str).hexdigest()

    def asDict(self) -> dict:
        """Event object as dictionary.

        Returns:
            dict: event as dictionary
        """
        evt = {
            "generated": int(self.generated),
            "type": str(self.eventType),
            "data": self.data,
            "module": self.module,
            "source": "",
        }
        if self.sourceEvent is not None and self.sourceEvent.data is not None:
            evt["source"] = self.sourceEvent.data
        return evt
