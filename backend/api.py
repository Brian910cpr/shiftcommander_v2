from flask import Flask, jsonify, request
from .storage import load_members, load_shifts, load_units, load_org_settings, save_org_settings

app = Flask(__name__)


def _format_display_name(member, pattern: str) -> str:
    initials = (member.first_name[:1] + member.last_name[:1]).upper()
    full_initials = (member.first_name[:1] + member.last_name[:2]).upper()  # XXX style
    number = member.member_number
    first = member.first_name
    last = member.last_name

    if pattern == "INITIALS_NUMBER":
        return f"{full_initials} {number}"
    if pattern == "INITIALS":
        return full_initials
    if pattern == "NUMBER":
        return number
    if pattern == "FIRST_LAST_NUMBER":
        return f"{first} {last} {number}"
    if pattern == "FIRST_NUMBER":
        return f"{first} {number}"
    if pattern == "LAST_NUMBER":
        return f"{last} {number}"
    if pattern == "FIRST":
        return first
    if pattern == "LAST":
        return last
    # fallback
    return f"{first} {last}"


@app.route("/api/public/wallboard")
def public_wallboard():
    members = {m.id: m for m in load_members() if m.active}
    shifts = load_shifts()
    units = {u.id: u for u in load_units()}
    settings = load_org_settings()
    tmpl = settings.display_templates.get("public")

    wallboard_items = []
    for s in shifts:
        unit = units.get(s.unit_id)
        for mid in s.assigned_member_ids:
            m = members.get(mid)
            if not m:
                continue
            display_name = _format_display_name(m, tmpl.pattern)
            wallboard_items.append({
                "shift_id": s.id,
                "date": s.date,
                "start": s.start,
                "end": s.end,
                "unit_name": unit.name if unit else s.unit_id,
                "member_display": display_name,
                "override_first_out": s.override_first_out_unit,
            })

    return jsonify({
        "org_name": settings.name,
        "items": wallboard_items,
        "rotation_order": settings.rotation_order,
    })


@app.route("/api/member/list")
def member_list():
    members = load_members()
    return jsonify([{
        "id": m.id,
        "first_name": m.first_name,
        "last_name": m.last_name,
        "member_number": m.member_number,
        "position_type": m.position_type,
        "expected_min_hours": m.expected_min_hours,
        "expected_max_hours": m.expected_max_hours,
        "points_balance": m.points_balance,
    } for m in members if m.active])


@app.route("/api/member/<member_id>/schedule")
def member_schedule(member_id):
    members = {m.id: m for m in load_members()}
    shifts = load_shifts()
    settings = load_org_settings()
    tmpl = settings.display_templates.get("member")

    member = members.get(member_id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    my_shifts = []
    for s in shifts:
        if member_id in s.assigned_member_ids:
            my_shifts.append({
                "shift_id": s.id,
                "date": s.date,
                "start": s.start,
                "end": s.end,
                "unit_id": s.unit_id,
            })

    return jsonify({
        "member": {
            "id": member.id,
            "display": _format_display_name(member, tmpl.pattern),
            "position_type": member.position_type,
            "expected_min_hours": member.expected_min_hours,
            "expected_max_hours": member.expected_max_hours,
            "points_balance": member.points_balance,
        },
        "shifts": my_shifts,
    })


@app.route("/api/manager/coverage")
def manager_coverage():
    members = {m.id: m for m in load_members()}
    shifts = load_shifts()
    units = {u.id: u for u in load_units()}
    settings = load_org_settings()
    tmpl = settings.display_templates.get("manager")

    rows = []
    for s in shifts:
        unit = units.get(s.unit_id)
        assigned = []
        for mid in s.assigned_member_ids:
            m = members.get(mid)
            if not m:
                continue
            assigned.append(_format_display_name(m, tmpl.pattern))
        rows.append({
            "shift_id": s.id,
            "date": s.date,
            "start": s.start,
            "end": s.end,
            "unit_name": unit.name if unit else s.unit_id,
            "assigned": assigned,
            "override_first_out": s.override_first_out_unit,
        })

    return jsonify({
        "rotation_order": settings.rotation_order,
        "rows": rows,
    })


@app.route("/api/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "GET":
        settings = load_org_settings()
        return jsonify({
            "id": settings.id,
            "name": settings.name,
            "self_scheduling_enabled": settings.self_scheduling_enabled,
            "ft_default_range": settings.ft_default_range,
            "pt_default_range": settings.pt_default_range,
            "vol_default_range": settings.vol_default_range,
            "rotation_order": settings.rotation_order,
            "display_templates": {
                k: {
                    "pattern": v.pattern,
                    "show_badges": v.show_badges,
                }
                for k, v in settings.display_templates.items()
            },
        })

    # POST: simple update for demo
    payload = request.json or {}
    settings = load_org_settings()

    if "self_scheduling_enabled" in payload:
        settings.self_scheduling_enabled = bool(payload["self_scheduling_enabled"])
    if "rotation_order" in payload:
        settings.rotation_order = list(payload["rotation_order"])
    if "display_templates" in payload:
        for key, val in payload["display_templates"].items():
            if key in settings.display_templates:
                dt = settings.display_templates[key]
                if "pattern" in val:
                    dt.pattern = val["pattern"]
                if "show_badges" in val:
                    dt.show_badges = bool(val["show_badges"])

    save_org_settings(settings)
    return jsonify({"status": "ok"})


@app.route("/api/manager/override_first_out", methods=["POST"])
def manager_override_first_out():
    payload = request.json or {}
    shift_id = payload.get("shift_id")
    unit_id = payload.get("unit_id")  # manual 1st-out unit or None to clear

    shifts = load_shifts()
    changed = False
    for s in shifts:
        if s.id == shift_id:
            s.override_first_out_unit = unit_id
            changed = True
            break

    if not changed:
        return jsonify({"error": "Shift not found"}), 404

    # persist back to disk
    from pathlib import Path
    import json
    from dataclasses import asdict
    data_dir = Path(__file__).resolve().parent.parent / "data"
    path = data_dir / "shifts.json"
    serializable = [asdict(s) for s in shifts]
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
