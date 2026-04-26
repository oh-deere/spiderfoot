# test_event_types.py
import unittest
from dataclasses import FrozenInstanceError

from spiderfoot.event_types import (
    EVENT_TYPES,
    EventType,
    EventTypeCategory,
    EventTypeDef,
)


class TestEventTypes(unittest.TestCase):

    def test_registry_has_expected_count(self):
        self.assertEqual(len(EVENT_TYPES), 173)

    def test_every_enum_member_has_registry_entry(self):
        missing = [e for e in EventType if e not in EVENT_TYPES]
        self.assertEqual(missing, [])

    def test_every_registry_entry_has_matching_enum_member(self):
        orphan_keys = [k for k in EVENT_TYPES if not isinstance(k, EventType)]
        self.assertEqual(orphan_keys, [])

    def test_defs_name_matches_enum_value(self):
        for enum_member, definition in EVENT_TYPES.items():
            self.assertEqual(enum_member.value, definition.name)

    def test_defs_are_frozen_instances(self):
        for definition in EVENT_TYPES.values():
            self.assertIsInstance(definition, EventTypeDef)
            with self.assertRaises(FrozenInstanceError):
                definition.name = "mutated"

    def test_category_distribution_matches_pre_refactor(self):
        counts = {cat: 0 for cat in EventTypeCategory}
        for d in EVENT_TYPES.values():
            counts[d.category] += 1
        self.assertEqual(counts[EventTypeCategory.DESCRIPTOR], 79)
        self.assertEqual(counts[EventTypeCategory.ENTITY], 58)
        self.assertEqual(counts[EventTypeCategory.DATA], 30)
        self.assertEqual(counts[EventTypeCategory.SUBENTITY], 5)
        self.assertEqual(counts[EventTypeCategory.INTERNAL], 1)

    def test_is_raw_distribution_matches_pre_refactor(self):
        raw_true = sum(1 for d in EVENT_TYPES.values() if d.is_raw)
        raw_false = sum(1 for d in EVENT_TYPES.values() if not d.is_raw)
        self.assertEqual(raw_true, 17)
        self.assertEqual(raw_false, 156)

    def test_root_event_is_internal_category(self):
        self.assertEqual(
            EVENT_TYPES[EventType.ROOT].category,
            EventTypeCategory.INTERNAL,
        )

    def test_event_type_is_string_compatible(self):
        # str-mixin contract: `EventType.INTERNET_NAME == "INTERNET_NAME"`
        # and ``str(EventType.INTERNET_NAME) == "INTERNET_NAME"`` must
        # both hold. This is the hinge on which all 892 module call
        # sites keep working unchanged.
        self.assertEqual(EventType.INTERNET_NAME, "INTERNET_NAME")
        self.assertEqual(str(EventType.INTERNET_NAME), "INTERNET_NAME")
        self.assertTrue(isinstance(EventType.INTERNET_NAME, str))

    def test_category_members_are_exactly_five(self):
        self.assertEqual(
            set(EventTypeCategory),
            {
                EventTypeCategory.DATA,
                EventTypeCategory.DESCRIPTOR,
                EventTypeCategory.ENTITY,
                EventTypeCategory.INTERNAL,
                EventTypeCategory.SUBENTITY,
            },
        )
