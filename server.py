import json
import os
from datetime import datetime, UTC
from flask import Flask, request, jsonify, send_from_directory, redirect

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DEBUG_DIR = os.path.join(BASE_DIR, "debug")

MEMBERS_FILE = os.path.join(DATA_DIR, "members.json")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.json")
SCHEDULE_FILE = os.path.join(DATA_DIR, "schedule.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
AVAILABILITY_FILE = os.path.join(DATA_DIR, "availability.json")
INFERRED_PREFERENCES_FILE = os.path.join(DATA_DIR, "inferred_preferences.json")
SCHEDULE_LOCKED_FILE = os.path.join(DATA_DIR, "schedule_locked.json")
ROTATION_TEMPLATES_FILE = os.path.join(DATA_DIR, "rotation_templates.json")


# =========================
# UTILS
# =========================

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def now_iso():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# =========================
# LOADERS / NORMALIZERS
# =========================

def load_members_payload():
    data = load_json(MEMBERS_FILE, {"members": []})
    return normalize_members_payload(data)


def load_members():
    return load_members_payload().get("members", [])


def infer_rotation_from_legacy(member):
    prefs = member.get("preferences", {}) if isinstance(member, dict) else {}
    shift_pref = prefs.get("shift_preference", {}) if isinstance(prefs, dict) else {}
    track = str(shift_pref.get("rotation_track") or "").strip().upper()
    if not track:
        return None
    pair = "AC" if track in ("A", "C") else "BD" if track in ("B", "D") else None
    if not pair:
        return None
    return {
        "pair": pair,
        "role": track
    }


def normalize_member_rotation(member):
    if not isinstance(member, dict):
        return member

    rotation = member.get("rotation")
    if not isinstance(rotation, dict):
        rotation = infer_rotation_from_legacy(member) or {}
    pair = str(rotation.get("pair") or "").strip().upper()
    role = str(rotation.get("role") or "").strip().upper()

    if role and pair not in ("AC", "BD"):
        pair = "AC" if role in ("A", "C") else "BD" if role in ("B", "D") else ""

    if pair not in ("AC", "BD") or role not in ("A", "B", "C", "D"):
        member["rotation"] = None
    else:
        member["rotation"] = {"pair": pair, "role": role}

    prefs = member.setdefault("preferences", {}) if isinstance(member, dict) else {}
    if not isinstance(prefs, dict):
        prefs = {}
        member["preferences"] = prefs
    shift_pref = prefs.setdefault("shift_preference", {})
    if not isinstance(shift_pref, dict):
        shift_pref = {}
        prefs["shift_preference"] = shift_pref

    if member["rotation"]:
        role = member["rotation"]["role"]
        shift_pref["rotation_track"] = role
        shift_pref["rotation_role"] = "day" if role in ("A", "B") else "night"
        shift_pref["relief_partner_track"] = {"A": "C", "B": "D", "C": "A", "D": "B"}[role]
        shift_pref.setdefault("rotation_template_id", "rot_223_12h_relief")
        shift_pref.setdefault("shift_length_hours", 12)
        if not shift_pref.get("style") or shift_pref.get("style") == "availability_based":
            shift_pref["style"] = "rotation_223_relief"
    else:
        shift_pref.setdefault("rotation_track", None)
        shift_pref.setdefault("rotation_role", None)
        shift_pref.setdefault("relief_partner_track", None)

    return member


def normalize_members_payload(payload):
    if isinstance(payload, list):
        payload = {"members": payload}
    elif not isinstance(payload, dict):
        payload = {"members": []}
    members = payload.get("members", [])
    if not isinstance(members, list):
        members = []
    payload["members"] = [normalize_member_rotation(m) for m in members]
    return payload


def save_members_payload(payload):
    payload = normalize_members_payload(payload)
    save_json(MEMBERS_FILE, payload)


def load_shifts():
    data = load_json(SHIFTS_FILE, [])
    if isinstance(data, dict):
        if "shifts" in data and isinstance(data["shifts"], list):
            return data["shifts"]
        return []
    if isinstance(data, list):
        return data
    return []


def save_shifts_file(shifts):
    save_json(SHIFTS_FILE, shifts)


def load_settings():
    data = load_json(SETTINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def load_availability_payload():
    data = load_json(AVAILABILITY_FILE, {"months": {}})
    if not isinstance(data, dict):
        return {"months": {}}
    months = data.get("months", {})
    if not isinstance(months, dict):
        data["months"] = {}
    return data


def save_availability_payload(payload):
    if not isinstance(payload, dict):
        payload = {"months": {}}
    months = payload.get("months", {})
    if not isinstance(months, dict):
        payload["months"] = {}
    save_json(AVAILABILITY_FILE, payload)


# =========================
# STATIC FILE ROUTES
# =========================

@app.route("/")
def root():
    return redirect("/docs/supervisor.html")


@app.route("/docs")
def docs_root():
    return redirect("/docs/supervisor.html")


@app.route("/docs/<path:path>")
def serve_docs(path):
    return send_from_directory(DOCS_DIR, path)


@app.route("/data/<path:path>")
def serve_data(path):
    return send_from_directory(DATA_DIR, path)


@app.route("/debug/<path:path>")
def serve_debug(path):
    return send_from_directory(DEBUG_DIR, path)


@app.route("/wallboard")
def wallboard_shortcut():
    return redirect("/docs/wallboard.html")


@app.route("/supervisor")
def supervisor_shortcut():
    return redirect("/docs/supervisor.html")


@app.route("/member")
def member_shortcut():
    return redirect("/docs/member.html")


# =========================
# MEMBERS
# =========================

@app.route("/api/members", methods=["GET"])
def get_members():
    return jsonify(load_members_payload())


@app.route("/api/members", methods=["POST"])
def save_members():
    incoming = request.get_json(silent=True)

    if incoming is None:
        return jsonify({"error": "No JSON body provided"}), 400

    if isinstance(incoming, list):
        payload = {"members": incoming}
    elif isinstance(incoming, dict):
        if "members" in incoming and isinstance(incoming["members"], list):
            payload = incoming
        else:
            payload = {"members": []}
    else:
        return jsonify({"error": "Invalid payload shape"}), 400

    save_members_payload(payload)
    return jsonify({"status": "ok", "count": len(payload.get("members", []))})


# =========================
# AVAILABILITY
# =========================

@app.route("/api/availability", methods=["GET"])
def get_availability():
    return jsonify(load_availability_payload())


@app.route("/api/availability", methods=["POST"])
def save_availability():
    incoming = request.get_json(silent=True)
    if not isinstance(incoming, dict):
        return jsonify({"error": "Availability payload must be an object"}), 400

    if "months" not in incoming or not isinstance(incoming.get("months"), dict):
        return jsonify({"error": "Availability payload must contain a months object"}), 400

    save_availability_payload(incoming)
    return jsonify({"status": "ok"})


# =========================
# SHIFTS
# =========================

@app.route("/api/shifts", methods=["GET"])
def get_shifts():
    return jsonify(load_shifts())


@app.route("/api/shifts", methods=["POST"])
def save_shifts():
    incoming = request.get_json(silent=True)

    if incoming is None:
        return jsonify({"error": "No JSON body provided"}), 400

    if isinstance(incoming, dict) and "shifts" in incoming:
        shifts = incoming.get("shifts", [])
    elif isinstance(incoming, list):
        shifts = incoming
    else:
        return jsonify({"error": "Invalid shifts payload"}), 400

    if not isinstance(shifts, list):
        return jsonify({"error": "Shifts must be a list"}), 400

    save_shifts_file(shifts)
    return jsonify({"status": "ok", "count": len(shifts)})


# =========================
# SETTINGS
# =========================

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())


@app.route("/api/settings", methods=["POST"])
def save_settings():
    settings = request.get_json(silent=True)
    if not isinstance(settings, dict):
        return jsonify({"error": "Settings must be an object"}), 400

    save_json(SETTINGS_FILE, settings)
    return jsonify({"status": "ok"})


# =========================
# SHIFT BUILDER
# =========================

def run_shift_builder():
    from engine.shift_builder import build_shift_skeletons

    members = load_members()
    settings = load_settings()
    availability = load_availability_payload()

    shifts = build_shift_skeletons(
        members=members,
        settings=settings,
        availability_payload=availability,
    )
    save_shifts_file(shifts)
    return shifts


# =========================
# RESOLVER
# =========================

def run_resolver():
    from engine.resolver import resolve

    members = load_members()
    shifts = load_shifts()
    settings = load_settings()
    availability = load_availability_payload()
    schedule_locked = load_json(SCHEDULE_LOCKED_FILE, {})
    rotation_templates = load_json(ROTATION_TEMPLATES_FILE, {})

    ctx = {
        "members": members,
        "shifts": shifts,
        "settings": settings,
        "availability": availability,
        "schedule_locked": schedule_locked,
        "rotation_templates": rotation_templates,
        "build": {
            "generated_at": now_iso()
        }
    }

    result = resolve(ctx)
    save_json(SCHEDULE_FILE, result)
    return result


# =========================
# GENERATE SCHEDULE
# =========================

@app.route("/api/generate", methods=["POST"])
def generate_schedule():
    built_shifts = run_shift_builder()
    result = run_resolver()

    shift_count = len(built_shifts) if isinstance(built_shifts, list) else 0

    if isinstance(result, dict):
        result["build_stats"] = {"shift_count": shift_count}

    return jsonify(result)


@app.route("/api/build_shifts", methods=["POST"])
def build_shifts_only():
    built_shifts = run_shift_builder()
    shift_count = len(built_shifts) if isinstance(built_shifts, list) else 0
    return jsonify({
        "status": "ok",
        "shift_count": shift_count,
        "shifts": built_shifts
    })


# =========================
# GET SCHEDULE (API)
# =========================

@app.route("/api/schedule", methods=["GET"])
def get_schedule_api():
    return jsonify(load_json(SCHEDULE_FILE, {}))


# =========================
# HEALTH CHECK
# =========================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "time": now_iso()
    })


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
