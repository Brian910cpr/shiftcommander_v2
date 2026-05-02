import copy
import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.resolver import resolve  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures"
DEBUG_DIR = ROOT / "debug"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_debug(name: str):
    return json.loads((DEBUG_DIR / name).read_text(encoding="utf-8"))


def find_seat_audit(seat_id: str) -> dict:
    full_audit = load_debug("latest_run_full_audit.json")
    return next(row for row in full_audit["seat_audit"] if row["seat_id"] == seat_id)


def rotation_templates_payload() -> dict:
    return {
        "rotation_templates": [
            {
                "template_id": "rot_223_12h_relief",
                "cycle_length_days": 14,
                "anchor_date": None,
                "tracks": [
                    {"track_id": "A", "role": "day", "pattern_key": "pattern_1"},
                    {"track_id": "B", "role": "day", "pattern_key": "pattern_2"},
                    {"track_id": "C", "role": "night", "pattern_key": "pattern_1"},
                    {"track_id": "D", "role": "night", "pattern_key": "pattern_2"},
                ],
                "patterns": {
                    "pattern_1": ["ON", "ON", "OFF", "OFF", "ON", "ON", "ON", "OFF", "OFF", "ON", "ON", "OFF", "OFF", "OFF"],
                    "pattern_2": ["OFF", "OFF", "ON", "ON", "OFF", "OFF", "OFF", "ON", "ON", "OFF", "OFF", "ON", "ON", "ON"],
                },
            }
        ]
    }


def apply_shift_date(data: dict, target_date: str) -> None:
    for shift in data["shifts"]:
        shift["date"] = target_date


def apply_availability(data: dict, statuses: dict[str, str], label: str = "AM") -> None:
    shift_date = data["shifts"][0]["date"]
    month_key = shift_date[:7]
    months = {month_key: {}}
    for member in data["members"]:
        member_id = member["member_id"]
        status = statuses.get(member_id, "preferred")
        months[month_key].setdefault(member_id, {})[shift_date] = {label: status}
    data["availability"] = {"months": months}


def future_weekday_iso(weekday_abbrev: str, minimum_days: int = 45) -> str:
    target = weekday_abbrev.title()
    current = datetime.now(UTC).date() + timedelta(days=minimum_days)
    while current.strftime("%a") != target:
        current += timedelta(days=1)
    return current.isoformat()


class ResolverHardFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        if DEBUG_DIR.exists():
            for path in DEBUG_DIR.iterdir():
                if path.is_file():
                    path.unlink()

    def test_certification_eligibility_filter_blocks_illegal_driver(self) -> None:
        data = load_fixture("resolver_base.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {})
        for member in data["members"]:
            if member["member_id"] == "emt_driver":
                member["drive"]["120"] = False
        result = resolve(copy.deepcopy(data))
        driver_seat = result["shifts"][0]["seats"][0]
        self.assertNotIn("candidate_audit", driver_seat)
        seat_record = find_seat_audit(driver_seat["seat_id"])
        rejected = [row for row in seat_record["rejected_candidates"] if row.get("member_id") == "emt_driver"]
        self.assertTrue(rejected)
        self.assertEqual(rejected[0]["reason"], "role_cert_block")

    def test_availability_block_rejects_dns_candidate(self) -> None:
        data = load_fixture("resolver_base.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {"emt_driver": "do_not_schedule"})
        result = resolve(copy.deepcopy(data))
        driver_seat = result["shifts"][0]["seats"][0]
        seat_record = find_seat_audit(driver_seat["seat_id"])
        rejected = [row for row in seat_record["rejected_candidates"] if row.get("member_id") == "emt_driver"]
        self.assertTrue(rejected)
        self.assertTrue(str(rejected[0]["reason"]).startswith("availability_dns:"))

    def test_lock_protection_preserves_valid_existing_assignment(self) -> None:
        data = load_fixture("resolver_preserved_assignment.json")
        apply_shift_date(data, datetime.now(UTC).date().isoformat())
        apply_availability(data, {})
        result = resolve(copy.deepcopy(data))
        driver_seat = result["shifts"][0]["seats"][0]
        self.assertTrue(driver_seat["locked"])
        self.assertEqual(driver_seat["assigned"], "emt_driver")
        self.assertTrue(driver_seat["preserved_existing_assignment"])

    def test_duplicate_assignment_prevention_blocks_second_core_assignment(self) -> None:
        data = load_fixture("resolver_base.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {"emt_driver": "do_not_schedule", "als_secondary": "do_not_schedule", "ncld_driver": "do_not_schedule"})
        result = resolve(copy.deepcopy(data))
        attendant_seat = result["shifts"][0]["seats"][1]
        seat_record = find_seat_audit(attendant_seat["seat_id"])
        rejected = [row for row in seat_record["rejected_candidates"] if row.get("member_id") == "als_primary"]
        self.assertTrue(rejected)
        self.assertEqual(rejected[0]["reason"], "double_booked_same_shift")
        self.assertEqual(attendant_seat["assigned"], "emt_attendant")

    def test_illegal_staffing_filter_blocks_second_als_core_assignment(self) -> None:
        data = load_fixture("resolver_base.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {"emt_driver": "do_not_schedule", "ncld_driver": "do_not_schedule"})
        result = resolve(copy.deepcopy(data))
        attendant_seat = result["shifts"][0]["seats"][1]
        seat_record = find_seat_audit(attendant_seat["seat_id"])
        rejected = [row for row in seat_record["rejected_candidates"] if row.get("member_id") == "als_secondary"]
        self.assertTrue(rejected)
        self.assertEqual(rejected[0]["reason"], "als_als_pair_block")
        self.assertEqual(attendant_seat["assigned"], "emt_attendant")

    def test_preserved_assignment_revalidation_selects_legal_alternative_and_writes_debug(self) -> None:
        data = load_fixture("resolver_preserved_assignment.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {})
        result = resolve(copy.deepcopy(data))
        attendant_seat = result["shifts"][0]["seats"][1]
        self.assertEqual(attendant_seat["assigned"], "emt_attendant")
        self.assertFalse(attendant_seat["preserved_existing_assignment"])
        self.assertIn("selection_statement", attendant_seat)
        self.assertNotIn("candidate_audit", attendant_seat)

        seat_record = find_seat_audit(attendant_seat["seat_id"])
        preserve_audit = [row for row in seat_record["rejected_candidates"] if row.get("member_id") == "ncld_driver" and row.get("reason") == "role_cert_block"]
        self.assertTrue(preserve_audit)
        self.assertEqual(preserve_audit[0]["reason"], "role_cert_block")

        self.assertTrue((DEBUG_DIR / "latest_run_summary.json").exists())
        self.assertTrue((DEBUG_DIR / "latest_run_full_audit.json").exists())
        self.assertTrue((DEBUG_DIR / "latest_run_failures.json").exists())
        self.assertTrue((DEBUG_DIR / "latest_run_supervisor_cards.json").exists())
        self.assertTrue((DEBUG_DIR / "latest_run_debug.txt").exists())

    def test_fallback_cannot_bypass_hard_legality(self) -> None:
        data = load_fixture("resolver_reserve_fallback.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {"normal_unavailable": "do_not_schedule", "reserve_legal": "do_not_schedule", "reserve_illegal": "preferred"})
        result = resolve(copy.deepcopy(data))
        seat = result["shifts"][0]["seats"][0]
        self.assertIsNone(seat.get("assigned"))
        self.assertEqual(seat.get("fallback_reason"), "no_legal_candidates_in_reserve_pass")
        self.assertFalse(seat.get("fallback_used"))

    def test_integrated_fallback_debug_shows_stage_and_flag(self) -> None:
        data = load_fixture("resolver_reserve_fallback.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {"normal_unavailable": "do_not_schedule", "reserve_legal": "preferred", "reserve_illegal": "preferred"})
        result = resolve(copy.deepcopy(data))
        seat = result["shifts"][0]["seats"][0]
        self.assertEqual(seat.get("assigned"), "reserve_legal")
        self.assertTrue(seat.get("fallback_used"))
        self.assertEqual(seat.get("decision_stage"), "initial_core")

        full_audit = load_debug("latest_run_full_audit.json")
        seat_record = next(row for row in full_audit["seat_audit"] if row["seat_id"] == seat["seat_id"])
        self.assertTrue(seat_record["fallback_used"])
        self.assertEqual(seat_record["fallback_reason"], "no_legal_candidates_in_normal_pass")
        self.assertEqual(seat_record["decision_stage"], "initial_core")

    def test_later_pass_cannot_revive_immutable_rejection(self) -> None:
        data = load_fixture("resolver_multipass_review.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        data["settings"]["restricted_pairings"] = []
        for member in data["members"]:
            if member["member_id"] == "driver_a":
                member["scheduler"] = {"avoid_with": ["attendant_b"]}
        shift_date = data["shifts"][0]["date"]
        month_key = shift_date[:7]
        data["availability"] = {
            "months": {
                month_key: {
                    "driver_a": {shift_date: {"AM": "preferred"}},
                    "attendant_b": {shift_date: {"AM": "preferred"}},
                    "attendant_c": {shift_date: {"AM": "preferred"}}
                }
            }
        }
        result = resolve(copy.deepcopy(data))
        attendant_seat = result["shifts"][0]["seats"][1]
        self.assertEqual(attendant_seat.get("assigned"), "attendant_c")
        self.assertTrue(attendant_seat.get("later_pass_reviewed"))

        seat_record = find_seat_audit(attendant_seat["seat_id"])
        stages = [row["stage"] for row in seat_record.get("pass_sequence", [])]
        self.assertIn("initial_core", stages)
        self.assertIn("review_reset", stages)
        self.assertIn("post_review_core", stages)
        missing_rejections = [row for row in seat_record["rejected_candidates"] if row.get("member_id") == "attendant_missing"]
        self.assertGreaterEqual(len(missing_rejections), 2)
        self.assertTrue(all(str(row.get("reason")).startswith("availability_missing:") for row in missing_rejections))

    def test_rotation_is_explicitly_suppressed_when_daily_map_is_missing(self) -> None:
        data = load_fixture("resolver_base.json")
        apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
        apply_availability(data, {})
        data["settings"]["rotation_223"] = {"cycle_anchor_date": "2026-04-01"}
        for member in data["members"]:
            if member["member_id"] == "emt_driver":
                member["rotation"] = {"pair": "AC", "role": "A"}
        result = resolve(copy.deepcopy(data))
        seat = result["shifts"][0]["seats"][0]
        full_audit = load_debug("latest_run_full_audit.json")
        seat_record = next(row for row in full_audit["seat_audit"] if row["seat_id"] == seat["seat_id"])
        self.assertEqual(seat_record["rotation_status"], "inactive_no_calendar")
        self.assertFalse(seat_record["rotation_score_applied"])
        self.assertFalse(seat_record["rotation_match"])
        self.assertIn("rotation_bonus_disabled:missing_rotation_template", seat_record["missing_data_assumptions"])

    def test_explicit_published_lock_preserves_assigned_member(self) -> None:
        data = load_fixture("resolver_base.json")
        target_date = (datetime.now(UTC).date() + timedelta(days=45)).isoformat()
        apply_shift_date(data, target_date)
        apply_availability(data, {})
        data["schedule_locked"] = {
            "build": {"source": "test_published_schedule"},
            "shifts": [
                {
                    "date": target_date,
                    "label": "AM Shift",
                    "seats": [
                        {"role": "DRIVER", "assigned_name": "EMT Driver", "locked": True}
                    ],
                }
            ],
        }
        result = resolve(copy.deepcopy(data))
        seat = result["shifts"][0]["seats"][0]
        self.assertTrue(seat["locked"])
        self.assertEqual(seat["lock_source"], "explicit")
        self.assertEqual(seat["assigned"], "emt_driver")
        self.assertTrue(seat["preserved_existing_assignment"])

    def test_explicit_empty_locked_seat_remains_empty(self) -> None:
        data = load_fixture("resolver_base.json")
        target_date = (datetime.now(UTC).date() + timedelta(days=45)).isoformat()
        apply_shift_date(data, target_date)
        apply_availability(data, {})
        data["schedule_locked"] = {
            "build": {"source": "test_published_schedule"},
            "shifts": [
                {
                    "date": target_date,
                    "label": "AM Shift",
                    "seats": [
                        {"role": "DRIVER", "locked": True}
                    ],
                }
            ],
        }
        result = resolve(copy.deepcopy(data))
        seat = result["shifts"][0]["seats"][0]
        self.assertTrue(seat["locked"])
        self.assertEqual(seat["lock_source"], "explicit")
        self.assertIsNone(seat.get("assigned"))
        self.assertTrue(seat.get("display_open_alert"))

    def test_rotation_calendar_applies_real_match_bonus_when_template_exists(self) -> None:
        data = load_fixture("resolver_base.json")
        target_date = future_weekday_iso("Mon")
        apply_shift_date(data, target_date)
        apply_availability(data, {})
        data["settings"]["rotation_223"] = {"cycle_anchor_date": target_date}
        data["rotation_templates"] = rotation_templates_payload()
        for member in data["members"]:
            if member["member_id"] == "emt_driver":
                member["rotation"] = {"pair": "AC", "role": "A"}
                member["preferences"] = {
                    **member.get("preferences", {}),
                    "shift_preference": {
                        "style": "rotation_223_relief",
                        "rotation_template_id": "rot_223_12h_relief",
                        "rotation_track": "A",
                    },
                }
        result = resolve(copy.deepcopy(data))
        full_audit = load_debug("latest_run_full_audit.json")
        driver_seat = result["shifts"][0]["seats"][0]
        seat_record = next(row for row in full_audit["seat_audit"] if row["seat_id"] == driver_seat["seat_id"])
        winning_candidate = next(row for row in seat_record["legal_candidates_remaining"] if row["member_id"] == "emt_driver")
        self.assertEqual(seat_record["rotation_status"], "active_on_pattern")
        self.assertTrue(seat_record["rotation_match"])
        self.assertTrue(seat_record["rotation_score_applied"])
        self.assertEqual(winning_candidate["score_breakdown"]["rotation_status"], "active_on_pattern")
        self.assertTrue(winning_candidate["score_breakdown"]["rotation_match"])
        self.assertTrue(winning_candidate["score_breakdown"]["rotation_score_applied"])

    def test_als_is_not_wasted_when_higher_priority_als_seat_is_open(self) -> None:
        data = load_fixture("resolver_base.json")
        target_date = future_weekday_iso("Mon")
        apply_shift_date(data, target_date)
        data["settings"]["day_rules"]["Mon"] = {"AM": "ALS", "PM": "ALS"}
        apply_availability(data, {
            "emt_driver": "do_not_schedule",
            "ncld_driver": "do_not_schedule",
            "emt_attendant": "preferred",
        })
        result = resolve(copy.deepcopy(data))
        driver_seat = result["shifts"][0]["seats"][0]
        attendant_seat = result["shifts"][0]["seats"][1]
        self.assertIsNone(driver_seat.get("assigned"))
        self.assertEqual(attendant_seat.get("assigned"), "als_primary")
        seat_record = find_seat_audit(driver_seat["seat_id"])
        driver_rejections = [row for row in seat_record["rejected_candidates"] if row.get("member_id") == "als_primary"]
        self.assertTrue(driver_rejections)
        self.assertEqual(driver_rejections[0]["reason"], "als_reserved_for_higher_priority_seat")

    def test_permissive_missing_day_rule_is_now_logged_as_explicit_assumption(self) -> None:
        data = load_fixture("resolver_base.json")
        target_date = "2026-06-05"
        apply_shift_date(data, target_date)
        apply_availability(data, {})
        data["settings"]["day_rules"].pop("Fri", None)
        result = resolve(copy.deepcopy(data))
        seat = result["shifts"][0]["seats"][0]
        full_audit = load_debug("latest_run_full_audit.json")
        seat_record = next(row for row in full_audit["seat_audit"] if row["seat_id"] == seat["seat_id"])
        self.assertEqual(seat.get("assigned"), "emt_driver")
        self.assertIn("missing_day_rule:Fri_AM:treated_as_non_als", seat_record["missing_data_assumptions"])


if __name__ == "__main__":
    unittest.main()
