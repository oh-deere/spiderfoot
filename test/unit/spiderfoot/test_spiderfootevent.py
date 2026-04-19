# test_spiderfootevent.py
import logging
import unittest

from spiderfoot import SpiderFootEvent
from spiderfoot.event_types import EventType


class TestSpiderFootEvent(unittest.TestCase):

    def test_init_root_event_should_create_event(self):
        event_data = 'example event data'
        module = 'example module'
        source_event = ''

        event_type = 'ROOT'
        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        self.assertIsInstance(evt, SpiderFootEvent)

    def test_init_nonroot_event_with_root_sourceEvent_should_create_event(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        source_event = SpiderFootEvent(event_type, event_data, module, source_event)

        event_type = 'example non-root event type'
        event_data = 'example event data'
        module = 'example module'
        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        self.assertIsInstance(evt, SpiderFootEvent)

    def test_init_argument_eventType_of_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        source_event = SpiderFootEvent(event_type, event_data, module, source_event)

        module = 'example module'

        invalid_types = [None, bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    SpiderFootEvent(invalid_type, event_data, module, source_event)

    def test_init_argument_eventType_with_empty_value_should_raise_ValueError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        source_event = SpiderFootEvent(event_type, event_data, module, source_event)

        event_type = ''
        module = 'example module'

        with self.assertRaises(ValueError):
            SpiderFootEvent(event_type, event_data, module, source_event)

    def test_init_argument_data_of_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        module = ''
        source_event = ''

        invalid_types = [None, bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    SpiderFootEvent(event_type, invalid_type, module, source_event)

    def test_init_argument_data_with_empty_value_should_raise_ValueError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        source_event = SpiderFootEvent(event_type, event_data, module, source_event)

        event_type = 'example event type'
        event_data = ''
        module = 'example module'

        with self.assertRaises(ValueError):
            SpiderFootEvent(event_type, event_data, module, source_event)

    def test_init_argument_module_of_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = SpiderFootEvent(event_type, event_data, module, "ROOT")

        event_type = 'example non-root event type'
        invalid_types = [None, bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    SpiderFootEvent(event_type, event_data, invalid_type, source_event)

    def test_init_argument_module_with_empty_value_should_raise_ValueError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        source_event = SpiderFootEvent(event_type, event_data, module, source_event)

        event_type = 'example event type'
        event_data = 'example event data'
        module = ''

        with self.assertRaises(ValueError):
            SpiderFootEvent(event_type, event_data, module, source_event)

    def test_init_argument_sourceEvent_of_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''

        event_type = 'example non-root event type'
        module = 'example module'
        invalid_types = [None, "", bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    SpiderFootEvent(event_type, event_data, module, invalid_type)

    def test_init_argument_confidence_of_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''

        invalid_types = [None, "", bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    evt = SpiderFootEvent(event_type, event_data, module, source_event)
                    evt.confidence = invalid_type

    def test_init_argument_confidence_invalid_value_should_raise_ValueError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''

        invalid_values = [-1, 101]
        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValueError):
                    evt = SpiderFootEvent(event_type, event_data, module, source_event)
                    evt.confidence = invalid_value

    def test_init_argument_visibility_of_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''

        invalid_types = [None, "", bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    evt = SpiderFootEvent(event_type, event_data, module, source_event)
                    evt.visibility = invalid_type

    def test_init_argument_visibility_invalid_value_should_raise_ValueError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''

        invalid_values = [-1, 101]
        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValueError):
                    evt = SpiderFootEvent(event_type, event_data, module, source_event)
                    evt.visibility = invalid_value

    def test_init_argument_risk_of_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''

        invalid_types = [None, "", bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    evt = SpiderFootEvent(event_type, event_data, module, source_event)
                    evt.risk = invalid_type

    def test_init_argument_risk_invalid_value_should_raise_ValueError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''

        invalid_values = [-1, 101]
        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValueError):
                    evt = SpiderFootEvent(event_type, event_data, module, source_event)
                    evt.risk = invalid_value

    def test_confidence_attribute_should_return_confidence_as_integer(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        confidence = 100

        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        evt.confidence = confidence

        self.assertEqual(confidence, evt.confidence)

    def test_confidence_attribute_setter_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        evt = SpiderFootEvent(event_type, event_data, module, source_event)

        invalid_types = [None, "", bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    evt.confidence = invalid_type

    def test_visibility_attribute_should_return_visibility_as_integer(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        visibility = 100

        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        evt.visibility = visibility

        self.assertEqual(visibility, evt.visibility)

    def test_visibility_attribute_setter_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        evt = SpiderFootEvent(event_type, event_data, module, source_event)

        invalid_types = [None, "", bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    evt.visibility = invalid_type

    def test_risk_attribute_should_return_risk_as_integer(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        risk = 100

        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        evt.risk = risk

        self.assertEqual(risk, evt.risk)

    def test_risk_attribute_setter_invalid_type_should_raise_TypeError(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        evt = SpiderFootEvent(event_type, event_data, module, source_event)

        invalid_types = [None, "", bytes(), list(), dict()]
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    evt.risk = invalid_type

    def test_actualSource_attribute_should_return_actual_source_as_string(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        evt = SpiderFootEvent(event_type, event_data, module, source_event)

        actual_source = 'example actual source'
        evt.actualSource = actual_source

        self.assertEqual(actual_source, evt.actualSource)

    def test_sourceEventHash_attribute_should_return_source_event_hash_as_string(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        evt = SpiderFootEvent(event_type, event_data, module, source_event)

        self.assertEqual("ROOT", evt.sourceEventHash)

    def test_moduleDataSource_attribute_should_return_module_data_source_as_string(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        evt = SpiderFootEvent(event_type, event_data, module, source_event)

        module_data_source = 'example module data source'
        evt.moduleDataSource = module_data_source

        self.assertEqual(module_data_source, evt.moduleDataSource)

    def test_asdict_root_event_should_return_event_as_a_dict(self):
        event_data = 'example event data'
        module = 'example module data'
        source_event = ''

        event_type = 'ROOT'
        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        evt_dict = evt.asDict()

        self.assertIsInstance(evt_dict, dict)
        self.assertEqual(evt_dict['type'], event_type)
        self.assertEqual(evt_dict['data'], event_data)
        self.assertEqual(evt_dict['module'], module)

    def test_asdict_nonroot_event_should_return_event_as_a_dict(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''
        source_event = SpiderFootEvent(event_type, event_data, module, source_event)

        event_type = 'example non-root event type'
        event_data = 'example event data'
        module = 'example_module'
        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        evt_dict = evt.asDict()

        self.assertIsInstance(evt_dict, dict)
        self.assertEqual(evt_dict['type'], event_type)
        self.assertEqual(evt_dict['data'], event_data)
        self.assertEqual(evt_dict['module'], module)

    def test_hash_attribute_root_event_should_return_root_as_a_string(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = ''
        source_event = ''

        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        evt_hash = evt.hash

        self.assertEqual('ROOT', evt_hash)

    def test_hash_attribute_nonroot_event_should_return_a_string(self):
        event_type = 'ROOT'
        event_data = 'example event data'
        module = 'example module'
        source_event = SpiderFootEvent(event_type, event_data, module, "ROOT")

        event_type = 'not ROOT'
        evt = SpiderFootEvent(event_type, event_data, module, source_event)
        evt_hash = evt.hash

        self.assertIsInstance(evt_hash, str)


class TestSpiderFootEventTypedRegistry(unittest.TestCase):

    def _root_source(self):
        return SpiderFootEvent("ROOT", "seed", "", "")

    def test_accepts_enum_event_type(self):
        root = self._root_source()
        evt = SpiderFootEvent(EventType.INTERNET_NAME, "example.com",
                              "test_mod", root)
        self.assertEqual(evt.eventType, "INTERNET_NAME")
        self.assertEqual(evt.eventType, EventType.INTERNET_NAME)
        self.assertIsInstance(evt.eventType, str)

    def test_accepts_str_event_type(self):
        root = self._root_source()
        evt = SpiderFootEvent("INTERNET_NAME", "example.com", "test_mod", root)
        self.assertEqual(evt.eventType, "INTERNET_NAME")
        self.assertEqual(evt.eventType, EventType.INTERNET_NAME)

    def test_str_and_enum_constructor_produce_equal_events(self):
        root = self._root_source()
        evt_str = SpiderFootEvent("INTERNET_NAME", "example.com", "m", root)
        evt_enum = SpiderFootEvent(EventType.INTERNET_NAME, "example.com", "m",
                                   root)
        self.assertEqual(evt_str.eventType, evt_enum.eventType)
        self.assertEqual(evt_str.data, evt_enum.data)
        self.assertEqual(evt_str.module, evt_enum.module)

    def test_unknown_event_type_warns_but_creates_event(self):
        root = self._root_source()
        with self.assertLogs("spiderfoot.event", level="WARNING") as cm:
            evt = SpiderFootEvent("NOT_A_REAL_TYPE", "x", "m", root)
        self.assertIsInstance(evt, SpiderFootEvent)
        self.assertEqual(evt.eventType, "NOT_A_REAL_TYPE")
        joined = "\n".join(cm.output).lower()
        self.assertIn("unknown eventtype", joined)

    def test_validator_failure_warns_but_creates_event(self):
        root = self._root_source()
        # Temporarily install a always-false validator on IP_ADDRESS.
        from spiderfoot.event_types import EVENT_TYPES, EventTypeDef
        original = EVENT_TYPES[EventType.IP_ADDRESS]
        EVENT_TYPES[EventType.IP_ADDRESS] = EventTypeDef(
            name=original.name,
            description=original.description,
            category=original.category,
            is_raw=original.is_raw,
            validator=lambda data: False,
        )
        try:
            with self.assertLogs("spiderfoot.event", level="WARNING") as cm:
                evt = SpiderFootEvent("IP_ADDRESS", "1.2.3.4", "m", root)
        finally:
            EVENT_TYPES[EventType.IP_ADDRESS] = original
        self.assertIsInstance(evt, SpiderFootEvent)
        self.assertEqual(evt.data, "1.2.3.4")
        joined = "\n".join(cm.output).lower()
        self.assertIn("validation failed", joined)

    def test_no_validator_means_no_warning(self):
        root = self._root_source()
        # INTERNET_NAME has validator=None on day 1. assertNoLogs was added
        # in Python 3.10.
        logger = logging.getLogger("spiderfoot.event")
        with self.assertNoLogs("spiderfoot.event", level="WARNING"):
            SpiderFootEvent("INTERNET_NAME", "example.com", "m", root)
        # Silence "unused" flake8 complaint about the logger handle.
        _ = logger
