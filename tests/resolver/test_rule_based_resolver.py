import copy
import unittest

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.rule_based_resolver import resolve_rule_based  # noqa: E402


TODAY = "2026-05-18"
FAR = "2026-06-22"
NEAR = "2026-05-25"


def member(mid, cert, employment="PT", drive=True, can_attend=True, can_drive=True):
    return {
        "member_id": mid,
        "name": mid.replace("_", " ").title(),
        "active": True,
        "cert": cert,
        "ops_cert": cert,
        "raw_cert": cert,
        "employment": {"status": employment, "pay_type": "hourly"},
        "drive": {"120": drive},
        "can_attend": can_attend,
        "can_drive": can_drive,
        "qualifications": [cert, "DRIVER"] if drive else [cert],
    }


def base_payload(date_iso=FAR, label="AM", seats=None):
    return {
        "current_date": TODAY,
        "settings": {
            "default_unit": "120",
            "resolver_rules": {
                "late_fill_window_days": 14,
                "interest_cycle_days": 3,
                "duty_crew_patterns": ["SAT_AM", "SAT_PM", "SUN_AM"],
            },
        },
        "members": [],
        "shifts": [
            {
                "date": date_iso,
                "label": label,
                "unit": "120",
                "seats": seats or [
                    {"role": "ATTENDANT", "hours": 12},
                    {"role": "DRIVER", "hours": 12},
                ],
            }
        ],
        "availability": {"months": {date_iso[:7]: {}}},
        "hour_totals": {},
    }


def set_availability(data, mid, date_iso, label, state):
    data["availability"]["months"].setdefault(date_iso[:7], {}).setdefault(mid, {}).setdefault(date_iso, {})[label] = state


def first_seat(result, role):
    return next(seat for seat in result["shifts"][0]["seats"] if seat["role"] == role)


def notice_for(result, mid):
    return next(row for row in result["notification_eligibility"] if row["member_id"] == mid)


class RuleBasedResolverDoctrineTests(unittest.TestCase):
    def test_no_rotation_authorized_aemts_are_hard_held_against_ot(self):
        data = base_payload()
        data["members"] = [member("ft_aemt", "AEMT", "FT"), member("pt_aemt", "AEMT", "PT")]
        data["hour_totals"] = {"ft_aemt": 40, "pt_aemt": 24}
        set_availability(data, "ft_aemt", FAR, "AM", "PREFER")
        set_availability(data, "pt_aemt", FAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        self.assertFalse(attendant.get("assigned"))
        self.assertIn("OPEN ATTENDANT", attendant["assigned_name"])

    def test_rotation_authorized_aemt_can_take_expected_rotation_ot(self):
        data = base_payload()
        data["members"] = [member("ft_aemt", "AEMT", "FT")]
        data["hour_totals"] = {"ft_aemt": 40}
        data["rotation_authorizations"] = [{"member_id": "ft_aemt", "status": "approved", "expected_rotation_ot_allowance": 12}]
        data["rotation_claims"] = [{"member_id": "ft_aemt", "date": FAR, "label": "AM", "role": "ATTENDANT", "status": "approved"}]
        set_availability(data, "ft_aemt", FAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        self.assertEqual(attendant["assigned"], "ft_aemt")
        self.assertEqual(attendant["ot_classification"], "expected_rotation_ot")

    def test_aemt_do_not_creates_open_attendant_seat(self):
        data = base_payload()
        data["members"] = [member("ft_aemt", "AEMT", "FT")]
        data["rotation_authorizations"] = [{"member_id": "ft_aemt", "status": "approved"}]
        data["rotation_claims"] = [{"member_id": "ft_aemt", "date": FAR, "label": "AM", "role": "ATTENDANT", "status": "approved"}]
        set_availability(data, "ft_aemt", FAR, "AM", "DO_NOT")

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        self.assertFalse(attendant.get("assigned"))
        self.assertTrue(any(row["reason"] == "availability_do_not" for row in attendant["rejected_candidates"]))

    def test_emt_fallback_fills_attendant_before_driver_selection(self):
        data = base_payload(seats=[{"role": "DRIVER", "hours": 12}, {"role": "ATTENDANT", "hours": 12}])
        data["members"] = [member("emt_bridge", "EMT", "PT"), member("ncld_driver", "NCLD", "PT")]
        set_availability(data, "emt_bridge", FAR, "AM", "PREFER")
        set_availability(data, "ncld_driver", FAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "emt_bridge")
        self.assertEqual(first_seat(result, "DRIVER")["assigned"], "ncld_driver")
        self.assertEqual(first_seat(result, "ATTENDANT")["resolver_phase"], "PHASE_2")
        self.assertEqual(first_seat(result, "DRIVER")["resolver_phase"], "PHASE_4")

    def test_emt_plus_emt_basic_crew_assigns_anchor_and_driver_when_no_als_available(self):
        data = base_payload(seats=[{"role": "DRIVER", "hours": 12}, {"role": "ATTENDANT", "hours": 12}])
        data["members"] = [member("emt_anchor", "EMT", "PT"), member("emt_driver", "EMT", "PT"), member("aemt_unset", "AEMT", "PT")]
        set_availability(data, "emt_anchor", FAR, "AM", "PREFER")
        set_availability(data, "emt_driver", FAR, "AM", "AVAILABLE")

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        driver = first_seat(result, "DRIVER")
        self.assertEqual(attendant["assigned"], "emt_anchor")
        self.assertEqual(driver["assigned"], "emt_driver")
        self.assertEqual(attendant["cert"], "EMT")
        self.assertEqual(driver["cert"], "EMT")
        self.assertEqual(attendant["resolver_phase"], "PHASE_2")
        self.assertEqual(driver["resolver_phase"], "PHASE_4")
        self.assertNotEqual(attendant["assigned"], "aemt_unset")
        self.assertIn("aemt_unset", attendant["candidate_list_considered"])

    def test_may_rollout_sticky_assignment_survives_resolver_run(self):
        data = base_payload()
        data["members"] = [member("may_visible", "AEMT", "PT"), member("other_aemt", "AEMT", "PT")]
        set_availability(data, "other_aemt", FAR, "AM", "PREFER")
        data["rollout_import"] = {
            "may_sticky_assignments": [
                {
                    "date": FAR,
                    "label": "AM",
                    "role": "ATTENDANT",
                    "member_id": "may_visible",
                }
            ]
        }

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        self.assertEqual(attendant["assigned"], "may_visible")
        self.assertTrue(attendant["preserved_existing_assignment"])
        self.assertTrue(attendant["rollout_sticky"])
        self.assertEqual(attendant["resolver_bucket"], "preserved_rollout_import")
        self.assertEqual(attendant["assignment_reason"], "Preserved from physical May wallboard rollout import.")
        self.assertNotEqual(attendant["assigned"], "other_aemt")

    def test_may_rollout_sticky_assignment_overrides_stale_do_not(self):
        data = base_payload()
        data["members"] = [member("visible_driver", "EMT", "PT")]
        set_availability(data, "visible_driver", FAR, "AM", "DO_NOT")
        data["rollout_import"] = {
            "may_sticky_assignments": [
                {
                    "date": FAR,
                    "label": "AM",
                    "role": "DRIVER",
                    "member_id": "visible_driver",
                }
            ]
        }

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertEqual(driver["assigned"], "visible_driver")
        self.assertTrue(driver["rollout_sticky"])
        self.assertFalse(driver["supervisor_review"])

    def test_may_rollout_open_seat_stays_open_for_interest_collection(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("emt_pickup", "EMT", "PT")]
        set_availability(data, "emt_pickup", NEAR, "AM", "PREFER")
        data["rollout_import"] = {
            "may_open_seats": [
                {
                    "date": NEAR,
                    "label": "AM",
                    "role": "DRIVER",
                }
            ]
        }

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertFalse(driver.get("assigned"))
        self.assertFalse(driver["locked"])
        self.assertTrue(driver["rollout_open"])
        self.assertTrue(driver["actionable_open_shift"])
        self.assertEqual(driver["open_reason"], "Preserved open during rollout import; available for open-shift workflow after rollout.")
        self.assertTrue(driver["interest_collecting"])
        self.assertIn("DRIVER", {row["seat_type"] for row in result["open_seats"]})

    def test_may_rollout_open_seat_can_fill_after_interest_request(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("aemt_anchor", "AEMT", "PT"), member("emt_pickup", "EMT", "PT")]
        data["published_schedule_state"] = {
            "shifts": [{"date": NEAR, "label": "AM", "seats": [{"role": "ATTENDANT", "assigned": "aemt_anchor", "published": True}]}]
        }
        data["rollout_import"] = {
            "may_open_seats": [{"date": NEAR, "label": "AM", "role": "DRIVER"}]
        }
        data["open_shift_requests"] = [{"member_id": "emt_pickup", "date": NEAR, "label": "AM", "role": "DRIVER", "response": "PREFER"}]

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertEqual(driver["assigned"], "emt_pickup")
        self.assertEqual(driver["resolver_phase"], "PHASE_6")
        self.assertTrue(driver["rollout_open"])

    def test_supervisor_assignment_can_fill_prior_rollout_open_seat(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("aemt_anchor", "AEMT", "PT"), member("emt_override", "EMT", "PT")]
        data["assignments"] = [
            {"date": NEAR, "label": "AM", "role": "ATTENDANT", "member_id": "aemt_anchor", "published": True},
            {"date": NEAR, "label": "AM", "role": "DRIVER", "member_id": "emt_override", "published": True},
        ]
        data["rollout_import"] = {
            "may_open_seats": [{"date": NEAR, "label": "AM", "role": "DRIVER"}]
        }

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertEqual(driver["assigned"], "emt_override")
        self.assertTrue(driver["preserved_existing_assignment"])
        self.assertFalse(driver.get("rollout_open", False))

    def test_adr_zipper_is_disabled_and_simulation_only_by_default(self):
        data = base_payload()
        data["members"] = [member("emt_anchor", "EMT", "PT"), member("emt_driver", "EMT", "PT")]
        set_availability(data, "emt_anchor", FAR, "AM", "PREFER")
        set_availability(data, "emt_driver", FAR, "AM", "AVAILABLE")

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertFalse(result["adr_zipper"]["enabled"])
        self.assertTrue(result["adr_zipper"]["simulation_only"])
        self.assertFalse(result["adr_zipper"]["production_override"])
        self.assertEqual(result["build"]["summary"]["adr_zipper_24_compression_candidates"], 0)
        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "emt_anchor")
        self.assertEqual(first_seat(result, "DRIVER")["assigned"], "emt_driver")

    def test_adr_zipper_fairness_uses_oldest_last_24_compression_date_not_member_order(self):
        data = base_payload()
        data["settings"]["resolver_rules"].update({
            "adr_zipper_enabled": True,
            "adr_zipper_simulation_only": True,
            "adr_zipper_allow_24_compression": True,
        })
        data["shifts"] = [
            {"date": FAR, "label": "AM", "unit": "120", "hours": 12, "seats": [{"role": "ATTENDANT", "hours": 12}, {"role": "DRIVER", "hours": 12}]},
            {"date": FAR, "label": "PM", "unit": "120", "hours": 12, "seats": [{"role": "ATTENDANT", "hours": 12}, {"role": "DRIVER", "hours": 12}]},
        ]
        newer = member("newer_emt", "EMT", "PT")
        older = member("older_emt", "EMT", "PT")
        newer.update({"hire_date": "2026-01-01", "last_24_compression_awarded_at": "2026-05-01", "preferences": {"allows_24h": True}})
        older.update({"hire_date": "2025-01-01", "last_24_compression_awarded_at": "2026-01-01", "preferences": {"allows_24h": True}})
        data["members"] = [newer, older]
        for mid in ["newer_emt", "older_emt"]:
            set_availability(data, mid, FAR, "AM", "PREFER")
            set_availability(data, mid, FAR, "PM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        ledger = result["adr_zipper"]["fairness_ledger"]
        self.assertEqual(ledger[0]["member_id"], "older_emt")
        self.assertEqual(ledger[0]["last_24_compression_awarded_at"], "2026-01-01")
        candidates = result["adr_zipper"]["compression_candidates"]
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["member_id"], "older_emt")
        self.assertTrue(all(row["simulation_only"] for row in candidates))
        self.assertTrue(all(row["would_modify_schedule"] is False for row in candidates))

    def test_adr_zipper_simulation_respects_member_staffing_system_assignment(self):
        data = base_payload()
        data["settings"]["resolver_rules"].update({
            "adr_zipper_enabled": True,
            "adr_zipper_simulation_only": True,
            "adr_zipper_allow_24_compression": True,
        })
        data["shifts"] = [
            {"date": FAR, "label": "AM", "unit": "120", "hours": 12, "seats": [{"role": "ATTENDANT", "hours": 12}, {"role": "DRIVER", "hours": 12}]},
            {"date": FAR, "label": "PM", "unit": "120", "hours": 12, "seats": [{"role": "ATTENDANT", "hours": 12}, {"role": "DRIVER", "hours": 12}]},
        ]
        zipper_emt = member("zipper_emt", "EMT", "PT")
        standard_emt = member("standard_emt", "EMT", "PT")
        zipper_emt.update({"last_24_compression_awarded_at": "2026-03-01", "preferences": {"allows_24h": True}, "staffing_system": {"active_system": "adr_emt_zipper"}})
        standard_emt.update({"last_24_compression_awarded_at": "2026-01-01", "preferences": {"allows_24h": True}, "staffing_system": {"active_system": "standard_12_hour"}})
        data["members"] = [standard_emt, zipper_emt]
        for mid in ["standard_emt", "zipper_emt"]:
            set_availability(data, mid, FAR, "AM", "PREFER")
            set_availability(data, mid, FAR, "PM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        candidate_ids = {row["member_id"] for row in result["adr_zipper"]["compression_candidates"]}
        self.assertIn("zipper_emt", candidate_ids)
        self.assertNotIn("standard_emt", candidate_ids)
        ledger = {row["member_id"]: row["staffing_system"] for row in result["adr_zipper"]["fairness_ledger"]}
        self.assertEqual(ledger["standard_emt"], "standard_12_hour")

    def test_solo_emt_anchor_inside_14_days_leaves_driver_open(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("emt_bridge", "EMT", "PT")]
        set_availability(data, "emt_bridge", NEAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "emt_bridge")
        self.assertTrue(first_seat(result, "ATTENDANT")["solo_emt_anchor_applied"])
        self.assertFalse(first_seat(result, "DRIVER").get("assigned"))
        self.assertIn("OPEN DRIVER", first_seat(result, "DRIVER")["assigned_name"])

    def test_assigned_als_member_is_normalized_to_attendant_and_blocks_solo_emt_anchor(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("als_member", "AEMT", "PT"), member("emt_member", "EMT", "PT")]
        data["published_schedule_state"] = {
            "shifts": [
                {
                    "date": NEAR,
                    "label": "AM",
                    "seats": [
                        {"role": "ATTENDANT", "assigned": "emt_member", "published": True},
                        {"role": "DRIVER", "assigned": "als_member", "published": True},
                    ],
                }
            ]
        }

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        driver = first_seat(result, "DRIVER")
        self.assertEqual(attendant["assigned"], "als_member")
        self.assertEqual(attendant["cert"], "AEMT")
        self.assertEqual(driver["assigned"], "emt_member")
        self.assertEqual(driver["cert"], "EMT")
        self.assertFalse(attendant["solo_emt_anchor_applied"])
        self.assertFalse(driver["solo_emt_anchor_applied"])
        self.assertIn("ALS/AEMT/Paramedic-qualified member normalized to ATTENDANT display order", result["shifts"][0]["resolver"]["notes"])

    def test_ncld_completes_crew_as_driver_not_attendant(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("emt_bridge", "EMT", "PT"), member("ncld_driver", "NCLD", "PT")]
        set_availability(data, "emt_bridge", NEAR, "AM", "PREFER")
        set_availability(data, "ncld_driver", NEAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "emt_bridge")
        self.assertEqual(first_seat(result, "DRIVER")["assigned"], "ncld_driver")
        self.assertNotEqual(first_seat(result, "ATTENDANT")["assigned"], "ncld_driver")

    def test_aemt_reclaims_attendant_if_valid_and_emt_returns_to_driver(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("emt_bridge", "EMT", "PT"), member("aemt_reclaim", "AEMT", "PT")]
        set_availability(data, "emt_bridge", NEAR, "AM", "PREFER")
        data["open_shift_requests"] = [{"member_id": "aemt_reclaim", "date": NEAR, "label": "AM", "role": "ATTENDANT", "response": "PREFER"}]

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "aemt_reclaim")
        self.assertEqual(first_seat(result, "DRIVER")["assigned"], "emt_bridge")
        self.assertTrue(first_seat(result, "ATTENDANT")["aemt_reclaim_attempted"])

    def test_aemt_reclaim_failure_restores_emt_as_attendant(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("emt_bridge", "EMT", "PT"), member("aemt_reclaim", "AEMT", "PT")]
        set_availability(data, "emt_bridge", NEAR, "AM", "PREFER")
        set_availability(data, "aemt_reclaim", NEAR, "AM", "DO_NOT")
        data["open_shift_requests"] = [{"member_id": "aemt_reclaim", "date": NEAR, "label": "AM", "role": "ATTENDANT", "response": "PREFER"}]

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "emt_bridge")
        self.assertFalse(first_seat(result, "DRIVER").get("assigned"))
        self.assertTrue(first_seat(result, "ATTENDANT")["aemt_reclaim_attempted"])
        self.assertTrue(first_seat(result, "ATTENDANT")["aemt_reclaim_restored"])

    def test_weekend_duty_crew_seats_display_duty_open_behavior(self):
        data = base_payload(date_iso="2026-06-20", label="AM")
        data["members"] = [member("aemt", "AEMT", "PT")]
        set_availability(data, "aemt", "2026-06-20", "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertTrue(driver["duty_crew"])
        self.assertTrue(driver["volunteer_crew_driver"])
        self.assertTrue(driver["structural_driver_coverage"])
        self.assertEqual(driver["assigned_name"], "Volunteer Crew Driver")
        self.assertEqual(driver["assignment_status"], "STRUCTURAL_COVERAGE")
        self.assertEqual(result["build"]["summary"]["duty_crew_seats_filled"], 1)
        self.assertEqual(result["build"]["summary"]["duty_crew_seats_open"], 0)
        self.assertEqual(result["shifts"][0]["crew_status"], "Complete")

    def test_saturday_pm_default_uses_volunteer_crew_driver_coverage(self):
        data = base_payload(date_iso="2026-06-20", label="PM")

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertTrue(driver["structural_driver_coverage"])
        self.assertEqual(driver["assigned_name"], "Volunteer Crew Driver")
        self.assertEqual(result["shifts"][0]["crew_status"], "Open Attendant")

    def test_sunday_am_default_uses_volunteer_crew_driver_coverage(self):
        data = base_payload(date_iso="2026-06-21", label="AM")

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertTrue(driver["structural_driver_coverage"])
        self.assertEqual(driver["assigned_name"], "Volunteer Crew Driver")
        self.assertEqual(result["build"]["summary"]["open_driver_seats"], 0)

    def test_weekday_solo_emt_anchor_still_shows_open_driver(self):
        data = base_payload(date_iso=NEAR, label="AM")
        data["members"] = [member("emt_bridge", "EMT", "PT")]
        set_availability(data, "emt_bridge", NEAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertFalse(driver.get("structural_driver_coverage"))
        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "emt_bridge")
        self.assertEqual(driver["assigned_name"], "OPEN DRIVER")

    def test_all_shifts_volunteer_crew_driver_toggle_covers_weekday_driver(self):
        data = base_payload(date_iso="2026-06-22", label="AM")
        data["settings"]["resolver_rules"]["volunteer_crew_driver_all_shifts"] = True
        data["members"] = [member("aemt", "AEMT", "PT")]
        set_availability(data, "aemt", "2026-06-22", "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertTrue(driver["structural_driver_coverage"])
        self.assertEqual(driver["assigned_name"], "Volunteer Crew Driver")
        self.assertEqual(result["shifts"][0]["crew_status"], "Complete")

    def test_volunteer_crew_driver_does_not_replace_preserved_named_driver(self):
        data = base_payload(date_iso="2026-06-20", label="AM")
        data["members"] = [member("aemt", "AEMT", "PT"), member("emt_driver", "EMT", "PT")]
        set_availability(data, "aemt", "2026-06-20", "AM", "PREFER")
        set_availability(data, "emt_driver", "2026-06-20", "AM", "PREFER")
        data["published_schedule_state"] = {
            "shifts": [{"date": "2026-06-20", "label": "AM", "seats": [{"role": "DRIVER", "assigned": "emt_driver", "published": True}]}]
        }

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertEqual(driver["assigned"], "emt_driver")
        self.assertEqual(driver["assigned_name"], "Emt Driver")

    def test_structurally_affixed_volunteer_crew_driver_replaces_named_driver_seat(self):
        data = base_payload(date_iso="2026-06-20", label="AM")
        data["settings"]["resolver_rules"]["volunteer_crew_driver_structurally_affixed"] = True
        data["members"] = [member("aemt", "AEMT", "PT"), member("emt_driver", "EMT", "PT")]
        set_availability(data, "aemt", "2026-06-20", "AM", "PREFER")
        set_availability(data, "emt_driver", "2026-06-20", "AM", "PREFER")
        data["published_schedule_state"] = {
            "shifts": [{"date": "2026-06-20", "label": "AM", "seats": [{"role": "DRIVER", "assigned": "emt_driver", "published": True}]}]
        }

        result = resolve_rule_based(copy.deepcopy(data))

        driver = first_seat(result, "DRIVER")
        self.assertFalse(driver.get("assigned"))
        self.assertEqual(driver["assigned_name"], "Volunteer Crew Driver")
        self.assertEqual(driver["assignment_status"], "STRUCTURAL_COVERAGE")

    def test_late_fill_removes_ot_restriction_only_after_non_ot_fails(self):
        data = base_payload(date_iso=NEAR)
        data["members"] = [member("ft_aemt", "AEMT", "FT")]
        data["hour_totals"] = {"ft_aemt": 40}
        set_availability(data, "ft_aemt", NEAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        self.assertEqual(attendant["assigned"], "ft_aemt")
        self.assertEqual(attendant["resolver_bucket"], "late_attendant_additional_ot")
        self.assertTrue(any(row["reason"] == "additional_ot_blocked" for row in attendant["rejected_candidates"]))

    def test_unset_not_auto_assigned_but_receives_open_shift_notice(self):
        data = base_payload()
        data["members"] = [member("unset_emt", "EMT", "PT")]

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertFalse(first_seat(result, "ATTENDANT").get("assigned"))
        self.assertTrue(notice_for(result, "unset_emt")["eligible_for_open_shift_notice"])

    def test_do_not_not_auto_assigned_and_no_open_shift_notice(self):
        data = base_payload()
        data["members"] = [member("do_not_emt", "EMT", "PT")]
        set_availability(data, "do_not_emt", FAR, "AM", "DO_NOT")

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertFalse(first_seat(result, "ATTENDANT").get("assigned"))
        self.assertFalse(notice_for(result, "do_not_emt")["eligible_for_open_shift_notice"])

    def test_driver_resolution_waits_until_attendant_resolution_is_complete(self):
        data = base_payload(seats=[{"role": "DRIVER", "hours": 12}, {"role": "ATTENDANT", "hours": 12}])
        data["members"] = [member("emt_bridge", "EMT", "PT"), member("emr_driver", "EMR", "PT")]
        set_availability(data, "emt_bridge", FAR, "AM", "PREFER")
        set_availability(data, "emr_driver", FAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        self.assertEqual(first_seat(result, "ATTENDANT")["assigned"], "emt_bridge")
        self.assertEqual(first_seat(result, "DRIVER")["assigned"], "emr_driver")

    def test_published_locked_assignment_is_preserved(self):
        data = base_payload()
        data["members"] = [member("aemt_locked", "AEMT", "PT")]
        set_availability(data, "aemt_locked", FAR, "AM", "PREFER")
        data["published_schedule_state"] = {
            "shifts": [{"date": FAR, "label": "AM", "seats": [{"role": "ATTENDANT", "assigned": "aemt_locked", "published": True}]}]
        }
        data["locks"] = [{"date": FAR, "label": "AM", "role": "ATTENDANT", "member_id": "aemt_locked", "locked": True}]

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        self.assertEqual(attendant["assigned"], "aemt_locked")
        self.assertTrue(attendant["locked"])
        self.assertTrue(attendant["preserved_existing_assignment"])

    def test_additional_ot_blocked_until_escalation(self):
        data = base_payload()
        data["members"] = [member("ft_aemt", "AEMT", "FT")]
        data["hour_totals"] = {"ft_aemt": 40}
        set_availability(data, "ft_aemt", FAR, "AM", "PREFER")

        result = resolve_rule_based(copy.deepcopy(data))

        attendant = first_seat(result, "ATTENDANT")
        self.assertFalse(attendant.get("assigned"))
        self.assertTrue(any(row["reason"] in {"additional_ot_blocked", "outside_bucket_rules"} for row in attendant["rejected_candidates"]))


if __name__ == "__main__":
    unittest.main()
