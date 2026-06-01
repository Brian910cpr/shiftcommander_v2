import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_server_module():
    spec = importlib.util.spec_from_file_location("shiftcommander_server_june_seed", ROOT / "server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class JuneAvailabilitySeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()

    def setUp(self):
        self.originals = {
            "load_availability_payload": self.server.load_availability_payload,
            "load_schedule_payload": self.server.load_schedule_payload,
            "load_google_calendar_june_mirror_payload": self.server.load_google_calendar_june_mirror_payload,
            "member_record_by_id": self.server.member_record_by_id,
            "save_availability_payload": self.server.save_availability_payload,
            "record_live_beta_transaction": self.server.record_live_beta_transaction,
            "member_availability_edit_start_date": self.server.member_availability_edit_start_date,
        }

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(self.server, name, value)

    def install_fixture(self, availability=None):
        member = {"member_id": "m1", "name": "Alice Adams", "ops_cert": "EMT"}
        schedule = {
            "shifts": [
                {
                    "date": "2026-06-03",
                    "label": "AM",
                    "seats": [{"role": "ATTENDANT", "assigned": "m1", "assigned_name": "Alice Adams"}],
                },
                {
                    "date": "2026-06-03",
                    "label": "PM",
                    "seats": [{"role": "DRIVER", "assigned": "other", "assigned_name": "Other Member"}],
                },
            ]
        }
        saved_payloads = []
        transactions = []

        self.server.load_availability_payload = lambda: availability or {"months": {}}
        self.server.load_schedule_payload = lambda: schedule
        self.server.member_record_by_id = lambda member_id: member if str(member_id) == "m1" else None
        self.server.save_availability_payload = lambda payload: saved_payloads.append(payload)
        self.server.record_live_beta_transaction = lambda *args, **kwargs: transactions.append({"args": args, "kwargs": kwargs})
        self.server.member_availability_edit_start_date = lambda: date(2026, 6, 1)
        return saved_payloads, transactions

    def test_extract_member_availability_seeds_june_from_calendar_mirror(self):
        self.install_fixture()

        payload = self.server.extract_member_availability("m1")
        entries = {(row["date"], row["period"]): row for row in payload["entries"]}

        self.assertEqual(entries[("2026-06-03", "AM")]["member_intent"], "prefer")
        self.assertEqual(entries[("2026-06-03", "PM")]["member_intent"], "do_not")
        self.assertEqual(entries[("2026-06-03", "AM")]["source"], "google_calendar_mirror")
        self.assertEqual(entries[("2026-06-03", "AM")]["logic_mode"], "mirror_only")
        self.assertTrue(entries[("2026-06-03", "AM")]["availability_seeded"])
        self.assertEqual(entries[("2026-06-03", "AM")]["seed_type"], "assigned_schedule_to_availability")
        self.assertFalse(entries[("2026-06-03", "AM")]["member_submitted"])
        self.assertTrue(entries[("2026-06-03", "AM")]["transactions_live"])

    def test_june_member_edit_records_seeded_before_state(self):
        saved_payloads, transactions = self.install_fixture()

        saved = self.server.save_member_availability_entries(
            "m1",
            [{"date": "2026-06-03", "period": "PM", "member_intent": "available"}],
            actor_member_id="m1",
        )

        self.assertEqual(saved[0]["member_submitted"], True)
        self.assertEqual(saved[0]["previous_seeded_value"], "do_not_schedule")
        self.assertEqual(saved_payloads[0]["months"]["2026-06"]["m1"]["2026-06-03"]["PM"], "available")
        self.assertEqual(transactions[0]["kwargs"]["before"]["availability_value"], "do_not_schedule")
        self.assertEqual(transactions[0]["kwargs"]["before"]["source"], "google_calendar_mirror")
        self.assertEqual(transactions[0]["kwargs"]["before"]["seed_type"], "assigned_schedule_to_availability")
        self.assertEqual(transactions[0]["kwargs"]["after"]["availability_value"], "available")
        self.assertTrue(transactions[0]["kwargs"]["after"]["member_submitted"])

    def test_schedule_payload_overlays_june_from_google_calendar_mirror(self):
        self.server.load_google_calendar_june_mirror_payload = lambda: {
            "build": {"source": "google_calendar_mirror", "feed_status": "ok"},
            "shifts": [
                {"date": "2026-06-03", "label": "AM", "source": "google_calendar_mirror", "logic_mode": "mirror_only", "seats": []}
            ],
        }

        payload = self.server.schedule_with_june_calendar_mirror({
            "build": {"source": "base"},
            "shifts": [
                {"date": "2026-06-03", "label": "AM", "source": "june_forming_import"},
                {"date": "2026-07-01", "label": "AM", "source": "shiftcommander"},
            ],
        })

        self.assertEqual([shift["date"] for shift in payload["shifts"]], ["2026-07-01", "2026-06-03"])
        self.assertEqual(payload["shifts"][1]["source"], "google_calendar_mirror")
        self.assertEqual(payload["build"]["june_calendar_mirror"]["feed_status"], "ok")

    def test_ical_parser_expands_daily_events_and_applies_overrides(self):
        ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:aemt
DTSTART;TZID=America/New_York:20260617T060000
DTEND;TZID=America/New_York:20260617T180000
RRULE:FREQ=DAILY
SUMMARY:AEMT
END:VEVENT
BEGIN:VEVENT
UID:aemt
RECURRENCE-ID;TZID=America/New_York:20260618T060000
DTSTART;TZID=America/New_York:20260618T060000
DTEND;TZID=America/New_York:20260618T180000
SUMMARY:Lynnsey
END:VEVENT
END:VCALENDAR
"""
        payload = self.server.build_june_calendar_mirror_payload(
            ics,
            members_payload=[{"member_id": "186", "name": "Lynnsey Benson", "ops_cert": "ALS"}],
        )
        shifts = {(shift["date"], shift["label"]): shift for shift in payload["shifts"]}

        self.assertEqual(shifts[("2026-06-17", "AM")]["seats"][0]["assigned_name"], "AEMT")
        self.assertEqual(shifts[("2026-06-18", "AM")]["seats"][0]["assigned"], "186")
        self.assertEqual(shifts[("2026-06-18", "AM")]["source"], "google_calendar_mirror")


if __name__ == "__main__":
    unittest.main()
