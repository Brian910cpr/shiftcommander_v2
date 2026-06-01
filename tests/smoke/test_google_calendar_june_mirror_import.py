import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_google_calendar_june_2026_mirror import (
    build_audit,
    file_sha256,
    parse_args,
    run,
)


def shift(date, label, role="DRIVER", assigned=None, assigned_name=None):
    open_name = f"OPEN {role}"
    return {
        "date": date,
        "label": label,
        "seats": [
            {
                "role": role,
                "seat_id": f"{date}:{label}:{role}:0",
                "assigned": assigned,
                "assigned_name": assigned_name if assigned_name is not None else open_name,
                "assignment_status": "ASSIGNED" if assigned else "OPEN",
            }
        ],
    }


class GoogleCalendarJuneMirrorImportTests(unittest.TestCase):
    def members(self):
        return {
            "members": [
                {"member_id": "163", "name": "AJ Smith", "first_name": "AJ", "last_name": "Smith"},
                {"member_id": "188", "name": "Brian Ennis", "first_name": "Brian", "last_name": "Ennis"},
            ]
        }

    def mirror(self):
        return {
            "build": {"month": "2026-06"},
            "shifts": [
                {
                    "date": "2026-06-03",
                    "label": "AM",
                    "seats": [
                        {
                            "role": "DRIVER",
                            "assigned": "163",
                            "assigned_name": "AJ Smith",
                            "seat_id": "2026-06-03:AM:DRIVER:0",
                            "calendar_uid": "aj-0603",
                        }
                    ],
                },
                {
                    "date": "2026-06-04",
                    "label": "PM",
                    "seats": [
                        {
                            "role": "DRIVER",
                            "assigned": "188",
                            "assigned_name": "Brian Ennis",
                            "seat_id": "2026-06-04:PM:DRIVER:0",
                            "calendar_uid": "brian-0604",
                        }
                    ],
                },
            ],
        }

    def test_audit_identifies_missing_open_seat_without_overwriting_conflict(self):
        schedule = {
            "shifts": [
                shift("2026-06-03", "AM"),
                shift("2026-06-04", "PM", assigned="163", assigned_name="AJ Smith"),
            ]
        }

        audit = build_audit(self.mirror(), schedule, self.members())
        summary = audit["summary"]

        self.assertEqual(summary["mirror_assignment_count"], 2)
        self.assertEqual(summary["missing_from_schedule_count"], 1)
        self.assertEqual(summary["schedule_differs_count"], 1)
        self.assertEqual(summary["high_confidence_write_candidates"], 1)
        self.assertEqual(summary["aj_smith_missing_dates"], ["2026-06-03"])

    def test_dry_run_writes_audit_but_does_not_change_schedule_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mirror_path = root / "mirror.json"
            schedule_path = root / "schedule.json"
            public_schedule_path = root / "public_schedule.json"
            members_path = root / "members.json"
            debug_dir = root / "debug"

            mirror_path.write_text(json.dumps(self.mirror()), encoding="utf-8")
            schedule_payload = {"shifts": [shift("2026-06-03", "AM"), shift("2026-06-04", "PM")]}
            schedule_path.write_text(json.dumps(schedule_payload), encoding="utf-8")
            public_schedule_path.write_text(json.dumps(schedule_payload), encoding="utf-8")
            members_path.write_text(json.dumps(self.members()), encoding="utf-8")

            before = (file_sha256(schedule_path), file_sha256(public_schedule_path))
            args = parse_args([
                "--dry-run",
                "--mirror", str(mirror_path),
                "--schedule", str(schedule_path),
                "--public-schedule", str(public_schedule_path),
                "--members", str(members_path),
                "--debug-dir", str(debug_dir),
            ])
            audit = run(args)
            after = (file_sha256(schedule_path), file_sha256(public_schedule_path))

            self.assertFalse(audit["schedule_hashes_changed"])
            self.assertEqual(before, after)
            self.assertTrue((debug_dir / "google_calendar_june_mirror_import_audit.json").exists())
            self.assertTrue((debug_dir / "google_calendar_june_mirror_import_summary.md").exists())

    def test_write_mode_fills_only_open_high_confidence_seats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mirror_path = root / "mirror.json"
            schedule_path = root / "schedule.json"
            public_schedule_path = root / "public_schedule.json"
            members_path = root / "members.json"
            debug_dir = root / "debug"

            mirror_path.write_text(json.dumps(self.mirror()), encoding="utf-8")
            schedule_payload = {
                "shifts": [
                    shift("2026-06-03", "AM"),
                    shift("2026-06-04", "PM", assigned="163", assigned_name="AJ Smith"),
                ]
            }
            schedule_path.write_text(json.dumps(schedule_payload), encoding="utf-8")
            public_schedule_path.write_text(json.dumps(schedule_payload), encoding="utf-8")
            members_path.write_text(json.dumps(self.members()), encoding="utf-8")

            args = parse_args([
                "--write",
                "--backup",
                "--mirror", str(mirror_path),
                "--schedule", str(schedule_path),
                "--public-schedule", str(public_schedule_path),
                "--members", str(members_path),
                "--debug-dir", str(debug_dir),
            ])
            audit = run(args)
            updated = json.loads(schedule_path.read_text(encoding="utf-8"))

            self.assertEqual(audit["applied_count"], 1)
            self.assertEqual(updated["shifts"][0]["seats"][0]["assigned"], "163")
            self.assertEqual(updated["shifts"][1]["seats"][0]["assigned"], "163")
            self.assertTrue(list(root.glob("schedule.*.bak.json")))
            self.assertTrue(list(root.glob("public_schedule.*.bak.json")))


if __name__ == "__main__":
    unittest.main()
