"""Synthetic adapter regressions; no Flask, credentials, or operational files."""

import copy
import tempfile
import unittest
from pathlib import Path

from engine.live_state_store import D1BridgeLiveStateStore


class D1BridgeFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.response = {}
        self.store = D1BridgeLiveStateStore(
            base_dir=str(self.root), data_dir=str(self.root / "data"),
            docs_dir=str(self.root / "docs"),
            bridge_client=lambda *_: copy.deepcopy(self.response),
        )

    def test_read_and_write_require_acknowledged_valid_resource_payload(self):
        for resource, valid in self.store.RESOURCE_DEFAULTS.items():
            for operation in ("read", "write"):
                for response in (
                    {}, {"ok": False, "payload": valid}, {"ok": "true", "payload": valid},
                    {"ok": True}, {"ok": True, "payload": None},
                    {"ok": True, "payload": []}, {"ok": True, "data": valid},
                ):
                    with self.subTest(resource=resource, operation=operation, response=response):
                        self.response = response
                        with self.assertRaises(RuntimeError):
                            self.call(resource, operation, valid)
                        self.assertEqual(list(self.root.iterdir()), [])
                self.response = {"ok": True, "payload": valid}
                self.assertEqual(self.call(resource, operation, valid), valid)

    def call(self, resource, operation, payload):
        def forbidden_fallback():
            self.fail("configured bridge must not fall back to files")
        if operation == "read":
            return self.store._bridge_read(resource, forbidden_fallback)
        return self.store._bridge_write(resource, payload, forbidden_fallback)

    def test_resource_collection_shape_is_required(self):
        for resource, malformed in (
            ("availability", {}), ("availability", {"months": []}),
            ("change_requests", {"requests": {}}),
            ("transactions", {"transactions": None}),
            ("supervisor_state", {"entries": "invalid"}),
            ("assignment_overlays", {"overlays": {}}),
            ("schedule_locked", {"shifts": None}),
        ):
            for operation in ("read", "write"):
                with self.subTest(resource=resource, operation=operation):
                    self.response = {"ok": True, "payload": malformed}
                    with self.assertRaises(RuntimeError):
                        self.call(resource, operation, malformed)

    def test_append_requires_explicit_success_and_transaction(self):
        transaction = {"id": "synthetic-1", "action_type": "regression"}
        for response in ({}, {"ok": False, "transaction": transaction}, {"ok": True},
                         {"ok": True, "transaction": []}):
            with self.subTest(response=response):
                self.response = response
                with self.assertRaises(RuntimeError):
                    self.store.append_transaction(transaction)
                self.assertEqual(list(self.root.iterdir()), [])
        self.response = {"ok": True, "transaction": transaction}
        self.assertEqual(self.store.append_transaction(transaction), transaction)

    def test_bridge_failure_propagates_without_writing_local_fallback(self):
        def unavailable(*_):
            raise RuntimeError("synthetic bridge unavailable")
        self.store.bridge_client = unavailable
        for operation in (self.store.read_availability,
                          lambda: self.store.write_availability({"months": {}}),
                          lambda: self.store.append_transaction({"id": "synthetic-1"})):
            with self.assertRaisesRegex(RuntimeError, "synthetic bridge unavailable"):
                operation()
        self.assertEqual(list(self.root.iterdir()), [])
