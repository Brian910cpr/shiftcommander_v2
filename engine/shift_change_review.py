"""Dry-run shift change request validation.

This module validates drop coverage, named replacement, and two-way swap
requests without mutating schedule data. The assigned member remains responsible
until a separate approval/apply workflow exists and succeeds.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine.open_shift_bid_review import (
    AVAILABLE,
    PREFER,
    availability_for,
    candidate_record,
    cert_matches_seat,
    has_rest_warning,
    has_schedule_conflict,
    is_open_seat,
    member_cert,
    member_id,
    member_name,
    parse_date,
    review_open_seat_bid,
    seat_role,
    shift_label,
)


VALID_REQUEST_TYPES = {"drop_coverage_request", "named_replacement", "two_way_swap"}
VALID_STATUSES = {
    "draft",
    "pending",
    "pending_acceptance",
    "pending_bids",
    "pending_supervisor_review",
    "approved",
    "declined",
    "cancelled",
    "expired",
    "applied",
}


def base_result(
    decision: str,
    reasons: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    requires_acceptance: bool = False,
    requires_supervisor: bool = True,
) -> Dict[str, Any]:
    return {
        "decision": decision,
        "can_apply_now": False,
        "requires_acceptance": requires_acceptance,
        "requires_supervisor": requires_supervisor,
        "reasons": reasons or [],
        "warnings": warnings or [],
        "candidate_summary": [],
        "coverage_before": {},
        "coverage_after": {},
    }


def denied(reason: str, warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    return base_result("denied", [reason], warnings, requires_acceptance=False, requires_supervisor=True)


def member_index(members: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {member_id(member): member for member in members if isinstance(member, dict) and member_id(member)}


def shift_matches_assignment(shift: Dict[str, Any], assignment: Dict[str, Any]) -> bool:
    return (
        str(shift.get("date") or shift.get("shift_date") or "")[:10] == str(assignment.get("date") or "")[:10]
        and shift_label(shift) == str(assignment.get("period") or assignment.get("label") or "").strip().upper()
    )


def seat_key_for(shift: Dict[str, Any], seat: Dict[str, Any], index: int) -> str:
    explicit = str(seat.get("seat_id") or seat.get("seat_key") or "").strip()
    if explicit:
        return explicit
    return f"{str(shift.get('date') or '')[:10]}:{shift_label(shift)}:{seat_role(seat) or 'SEAT'}:{index}"


def find_assignment_seat(schedule: Dict[str, Any], assignment: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[int]]:
    wanted_key = str(assignment.get("seat_key") or assignment.get("seat_id") or "").strip()
    wanted_role = str(assignment.get("role") or "").strip().upper()
    wanted_member = str(assignment.get("member_id") or "").strip()
    for shift in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        if not isinstance(shift, dict) or not shift_matches_assignment(shift, assignment):
            continue
        for index, seat in enumerate(shift.get("seats", []) if isinstance(shift.get("seats"), list) else []):
            key = seat_key_for(shift, seat, index)
            role_match = not wanted_role or seat_role(seat) == wanted_role
            key_match = bool(wanted_key and key == wanted_key)
            member_match = bool(wanted_member and str(seat.get("assigned") or "").strip() == wanted_member)
            if key_match or (role_match and member_match):
                return shift, seat, index
    return None, None, None


def assignment_snapshot(shift: Dict[str, Any], seat: Dict[str, Any], index: Optional[int] = None) -> Dict[str, Any]:
    return {
        "seat_key": seat_key_for(shift, seat, index or 0),
        "date": str(shift.get("date") or shift.get("shift_date") or "")[:10],
        "period": shift_label(shift),
        "role": seat_role(seat),
        "member_id": str(seat.get("assigned") or "").strip() or None,
        "member_name": seat.get("assigned_name"),
        "cert": seat.get("cert"),
        "assignment_status": seat.get("assignment_status"),
    }


def confirmation_for(request: Dict[str, Any], member_id_value: str) -> bool:
    confirmations = request.get("member_confirmations")
    if not isinstance(confirmations, list):
        return False
    for row in confirmations:
        if not isinstance(row, dict):
            continue
        if str(row.get("member_id") or "").strip() != member_id_value:
            continue
        state = str(row.get("status") or row.get("state") or row.get("decision") or "").strip().lower()
        if state in {"accepted", "confirmed", "approved", "yes"}:
            return True
    return False


def temporary_open_seat(seat: Dict[str, Any]) -> Dict[str, Any]:
    clone = deepcopy(seat)
    clone["assigned"] = None
    clone["assigned_name"] = f"OPEN {seat_role(seat)}".strip()
    clone["assignment_status"] = "OPEN"
    clone["locked"] = False
    clone["supervisor_review"] = False
    clone["structural_driver_coverage"] = False
    return clone


def evaluate_member_for_seat(schedule: Dict[str, Any], shift: Dict[str, Any], seat: Dict[str, Any], member: Dict[str, Any]) -> Dict[str, Any]:
    record = candidate_record(schedule, shift, seat, member, PREFER)
    cert = member_cert(member)
    role = seat_role(seat)
    hard_reasons = []
    if role == "ATTENDANT" and cert in {"EMR", "NCLD"}:
        hard_reasons.append("attendant_requires_als")
    if role != "DRIVER" and cert == "NCLD":
        hard_reasons.append("ncld_driver_only")
    if role == "ATTENDANT" and not cert_matches_seat(member, seat):
        hard_reasons.append("replacement_lacks_required_attendant_cert")
    if role == "DRIVER" and not cert_matches_seat(member, seat):
        hard_reasons.append("replacement_lacks_required_driver_cert")
    if "schedule_conflict" in record["warnings"]:
        hard_reasons.append("replacement_has_direct_conflict")
    record["hard_reasons"] = hard_reasons
    return record


def coverage_after_for_replacement(shift: Dict[str, Any], seat: Dict[str, Any], member: Dict[str, Any]) -> Dict[str, Any]:
    after = assignment_snapshot(shift, seat)
    after.update({
        "member_id": member_id(member),
        "member_name": member_name(member),
        "cert": member_cert(member),
        "assignment_status": "DRY_RUN_REPLACEMENT",
    })
    return after


def decide_replacement(candidate: Dict[str, Any], accepted: bool, requires_acceptance: bool) -> Dict[str, Any]:
    hard_reasons = candidate.get("hard_reasons", [])
    if hard_reasons:
        return base_result(
            "denied",
            hard_reasons,
            candidate.get("warnings", []),
            requires_acceptance=requires_acceptance and not accepted,
            requires_supervisor=True,
        )
    if requires_acceptance and not accepted:
        return base_result(
            "supervisor_review",
            ["replacement_not_accepted"],
            candidate.get("warnings", []),
            requires_acceptance=True,
            requires_supervisor=True,
        )
    warnings = candidate.get("warnings", [])
    review_warnings = [warning for warning in warnings if warning not in {"wrong_cert"}]
    if review_warnings:
        return base_result(
            "supervisor_review",
            ["replacement_has_review_warnings"],
            review_warnings,
            requires_acceptance=False,
            requires_supervisor=True,
        )
    return base_result(
        "eligible_for_auto_approval",
        [],
        [],
        requires_acceptance=False,
        requires_supervisor=False,
    )


def validate_request_shell(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    request_type = request.get("type")
    if request_type not in VALID_REQUEST_TYPES:
        return denied("unsupported_request_type")
    status = request.get("status", "draft")
    if status not in VALID_STATUSES:
        return denied("unsupported_request_status")
    if any(key in request for key in ("assignment_patch", "schedule_patch", "mutations", "clear_seat")):
        return denied("request_attempts_direct_schedule_mutation")
    if not isinstance(request.get("original_assignment"), dict):
        return denied("missing_original_assignment")
    return None


def review_drop_coverage_request(
    schedule: Dict[str, Any],
    members: Iterable[Dict[str, Any]],
    availability: Dict[str, Any],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    assignment = request["original_assignment"]
    shift, seat, index = find_assignment_seat(schedule, assignment)
    if not shift or not seat:
        return denied("missing_original_shift_or_seat")
    if not str(seat.get("assigned") or "").strip():
        return denied("original_shift_would_be_uncovered")

    overlay_seat = temporary_open_seat(seat)
    bid_overlay = request.get("bid_overlay") if isinstance(request.get("bid_overlay"), dict) else {}
    bid_result = review_open_seat_bid(
        schedule,
        members,
        availability,
        shift,
        overlay_seat,
        as_of=request.get("created_at"),
        bid_due_at=bid_overlay.get("bid_due_at"),
    )
    result = base_result("supervisor_review", ["coverage_request_preserves_original_assignment"], requires_acceptance=False, requires_supervisor=True)
    result["candidate_summary"] = bid_result.get("candidates", [])
    result["coverage_before"] = assignment_snapshot(shift, seat, index)
    result["coverage_after"] = assignment_snapshot(shift, seat, index)
    result["bid_overlay"] = {
        "opens_for_bidding": bool(bid_overlay.get("opens_for_bidding", True)),
        "bid_due_at": bid_overlay.get("bid_due_at"),
        "seat_key": result["coverage_before"]["seat_key"],
    }
    if bid_result.get("decision") == "auto_assign":
        result["warnings"].append("replacement_candidate_available_but_requires_approval")
    elif bid_result.get("reason"):
        result["warnings"].append(bid_result["reason"])
    return result


def review_named_replacement(
    schedule: Dict[str, Any],
    members: Iterable[Dict[str, Any]],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    members_by_id = member_index(members)
    assignment = request["original_assignment"]
    shift, seat, index = find_assignment_seat(schedule, assignment)
    if not shift or not seat:
        return denied("missing_original_shift_or_seat")
    original_member_id = str(seat.get("assigned") or "").strip()
    if not original_member_id:
        return denied("original_shift_would_be_uncovered")
    replacement_id = str(request.get("requested_replacement_member_id") or "").strip()
    replacement = members_by_id.get(replacement_id)
    if replacement is None:
        return denied("missing_replacement_member")

    candidate = evaluate_member_for_seat(schedule, shift, seat, replacement)
    accepted = confirmation_for(request, replacement_id)
    result = decide_replacement(candidate, accepted=accepted, requires_acceptance=True)
    result["candidate_summary"] = [candidate]
    result["coverage_before"] = assignment_snapshot(shift, seat, index)
    result["coverage_after"] = coverage_after_for_replacement(shift, seat, replacement)
    return result


def review_two_way_swap(
    schedule: Dict[str, Any],
    members: Iterable[Dict[str, Any]],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    members_by_id = member_index(members)
    original = request["original_assignment"]
    target = request.get("target_assignment")
    if not isinstance(target, dict):
        return denied("missing_target_assignment")
    shift_a, seat_a, index_a = find_assignment_seat(schedule, original)
    shift_b, seat_b, index_b = find_assignment_seat(schedule, target)
    if not shift_a or not seat_a or not shift_b or not seat_b:
        return denied("missing_original_or_target_shift_or_seat")
    member_a_id = str(seat_a.get("assigned") or "").strip()
    member_b_id = str(seat_b.get("assigned") or "").strip()
    member_a = members_by_id.get(member_a_id)
    member_b = members_by_id.get(member_b_id)
    if not member_a or not member_b:
        return denied("missing_swap_member")

    candidate_a_to_b = evaluate_member_for_seat(schedule, shift_b, seat_b, member_a)
    candidate_b_to_a = evaluate_member_for_seat(schedule, shift_a, seat_a, member_b)
    accepted_a = confirmation_for(request, member_a_id)
    accepted_b = confirmation_for(request, member_b_id)

    hard_reasons = candidate_a_to_b.get("hard_reasons", []) + candidate_b_to_a.get("hard_reasons", [])
    warnings = list(dict.fromkeys(candidate_a_to_b.get("warnings", []) + candidate_b_to_a.get("warnings", [])))
    if hard_reasons:
        decision = base_result(
            "denied",
            list(dict.fromkeys(hard_reasons)),
            warnings,
            requires_acceptance=not (accepted_a and accepted_b),
            requires_supervisor=True,
        )
    elif not (accepted_a and accepted_b):
        decision = base_result(
            "supervisor_review",
            ["swap_requires_both_member_confirmations"],
            warnings,
            requires_acceptance=True,
            requires_supervisor=True,
        )
    elif warnings:
        decision = base_result(
            "supervisor_review",
            ["swap_has_review_warnings"],
            warnings,
            requires_acceptance=False,
            requires_supervisor=True,
        )
    else:
        decision = base_result(
            "eligible_for_auto_approval",
            [],
            [],
            requires_acceptance=False,
            requires_supervisor=False,
        )

    decision["candidate_summary"] = [
        {"direction": "original_to_target", **candidate_a_to_b},
        {"direction": "target_to_original", **candidate_b_to_a},
    ]
    decision["coverage_before"] = {
        "original": assignment_snapshot(shift_a, seat_a, index_a),
        "target": assignment_snapshot(shift_b, seat_b, index_b),
    }
    after_original = coverage_after_for_replacement(shift_a, seat_a, member_b)
    after_target = coverage_after_for_replacement(shift_b, seat_b, member_a)
    decision["coverage_after"] = {"original": after_original, "target": after_target}
    return decision


def review_shift_change_request(
    schedule: Dict[str, Any],
    members: Iterable[Dict[str, Any]],
    availability: Optional[Dict[str, Any]],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    shell_error = validate_request_shell(request)
    if shell_error:
        return shell_error
    request_type = request["type"]
    availability_payload = availability if isinstance(availability, dict) else {}
    if request_type == "drop_coverage_request":
        return review_drop_coverage_request(schedule, members, availability_payload, request)
    if request_type == "named_replacement":
        return review_named_replacement(schedule, members, request)
    if request_type == "two_way_swap":
        return review_two_way_swap(schedule, members, request)
    return denied("unsupported_request_type")
