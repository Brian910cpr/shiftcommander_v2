import json
import os
import base64
import hashlib
import hmac
import secrets
import shutil
import time
from datetime import datetime, timedelta, UTC
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, redirect, session, render_template_string, Response

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "shiftcommander-local-dev-secret-key"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

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
SUPERVISOR_STATE_FILE = os.path.join(DATA_DIR, "supervisor_state.json")
AUTH_USERS_FILE = os.path.join(DATA_DIR, "auth_users.json")
TEST_MEMBER_LOGIN = {
    "username": "test",
    "password": "test",
    "member_id": "180",
}
BUILD_CODE = "SC-BUILD-2026-05-04-ONLINE-AUTH-QT-001"
EMPTY_SCHEDULE_BYTES = b'{"build":{"generated_at":null,"summary":{"total_seats":0,"filled_seats":0,"unfilled_seats":0}},"shifts":[]}\n'


def env_flag(name, default=False):
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def parse_csv_env(name, default_values):
    raw = str(os.environ.get(name) or "").strip()
    values = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()] if raw else list(default_values)
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


SC_QUICK_TEST_MODE = env_flag("SC_QUICK_TEST_MODE", False)
SC_ALLOWED_ORIGINS = parse_csv_env(
    "SC_ALLOWED_ORIGINS",
    [
        "https://adr-fr.org",
        "https://www.adr-fr.org",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
        "http://127.0.0.1:8001",
        "http://localhost:8001",
    ],
)
SC_PUBLIC_BASE_URL = str(os.environ.get("SC_PUBLIC_BASE_URL") or "").strip().rstrip("/")
SC_FLASK_DEBUG = env_flag("FLASK_DEBUG", False)


@app.before_request
def handle_api_options_preflight():
    if request.method == "OPTIONS" and request.path.startswith("/api/"):
        return ("", 204)


@app.after_request
def apply_cors_headers(response):
    origin = allowed_request_origin()
    if request.path.startswith("/api/"):
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.add("Vary", "Origin")
    return response


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
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(temp_path, path)


def fast_json_file_response(path, empty_payload=EMPTY_SCHEDULE_BYTES):
    started = time.perf_counter()
    source = "file"
    status = 200
    try:
        if not os.path.exists(path) or os.path.getsize(path) <= 0:
            payload = empty_payload
            source = "empty"
        else:
            with open(path, "rb") as f:
                payload = f.read()
    except OSError as error:
        payload = empty_payload
        source = f"fallback:{error.__class__.__name__}"
        status = 200

    elapsed_ms = (time.perf_counter() - started) * 1000
    response = Response(payload, status=status, mimetype="application/json")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-ShiftCommander-Source"] = source
    response.headers["X-ShiftCommander-Read-Ms"] = f"{elapsed_ms:.1f}"
    response.headers["X-ShiftCommander-Bytes"] = str(len(payload))
    if elapsed_ms > 500:
        app.logger.warning("/api/schedule slow read %.1fms source=%s bytes=%s", elapsed_ms, source, len(payload))
    return response


def now_iso():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def hash_password(password):
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password, stored_hash):
    try:
        scheme, salt_b64, digest_b64 = str(stored_hash or "").split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("utf-8"))
        expected = base64.b64decode(digest_b64.encode("utf-8"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def env_supervisor_password():
    return str(os.environ.get("SUPERVISOR_PASSWORD") or "").strip()


def env_override_password():
    return str(os.environ.get("OVERRIDE_PASSWORD") or "").strip()


def load_auth_users():
    data = load_json(AUTH_USERS_FILE, {"supervisor": {}, "members": {}})
    if not isinstance(data, dict):
        data = {"supervisor": {}, "members": {}}
    if not isinstance(data.get("supervisor"), dict):
        data["supervisor"] = {}
    if not isinstance(data.get("members"), dict):
        data["members"] = {}
    return data


def save_auth_users(data):
    if not isinstance(data, dict):
        data = {"supervisor": {}, "members": {}}
    data.setdefault("supervisor", {})
    data.setdefault("members", {})
    save_json(AUTH_USERS_FILE, data)


def sync_auth_members():
    auth_users = load_auth_users()
    members = load_members_payload().get("members", [])
    current_ids = {str(member.get("member_id", member.get("id"))) for member in members if member.get("member_id", member.get("id")) not in (None, "")}
    for member_id in current_ids:
        auth_users["members"].setdefault(
            member_id,
            {"password_hash": None, "must_change_password": True, "updated_at": None},
        )
    stale = [member_id for member_id in auth_users["members"] if member_id not in current_ids]
    for member_id in stale:
        auth_users["members"].pop(member_id, None)
    save_auth_users(auth_users)
    return auth_users


def current_auth():
    role = session.get("auth_role")
    if role == "supervisor":
        return {"authenticated": True, "role": "supervisor", "member_id": None}
    if role == "member":
        return {
            "authenticated": True,
            "role": "member",
            "member_id": str(session.get("member_id") or "").strip() or None,
        }
    return {"authenticated": False, "role": None, "member_id": None}


def auth_json_error(message, status_code=401):
    return jsonify({"error": message}), status_code


def quick_test_mode_enabled():
    return SC_QUICK_TEST_MODE


def current_public_base_url():
    if SC_PUBLIC_BASE_URL:
        return SC_PUBLIC_BASE_URL
    return str(request.host_url or "").strip().rstrip("/")


def allowed_request_origin():
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    if not origin:
        return None
    host_origin = str(request.host_url or "").strip().rstrip("/")
    if origin == host_origin or origin in SC_ALLOWED_ORIGINS:
        return origin
    return None


def login_redirect(role_name):
    next_path = request.path
    if request.query_string:
        next_path = f"{next_path}?{request.query_string.decode('utf-8')}"
    if role_name == "member":
        return redirect(f"/login.html?next={next_path}")
    return redirect(f"/login/{role_name}?next={next_path}")


def require_role(role_name):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            auth = current_auth()
            if not auth["authenticated"]:
                if request.path.startswith("/api/"):
                    return auth_json_error("Authentication required", 401)
                return login_redirect(role_name)
            if role_name == "supervisor" and auth["role"] != "supervisor":
                return auth_json_error("Supervisor access required", 403) if request.path.startswith("/api/") else redirect("/member")
            if role_name == "member" and auth["role"] not in {"member", "supervisor"}:
                return auth_json_error("Member access required", 403) if request.path.startswith("/api/") else redirect("/login.html")
            return func(*args, **kwargs)
        return wrapped
    return decorator


def current_member_record():
    auth = current_auth()
    member_id = auth.get("member_id")
    if not member_id:
        return None
    return next((member for member in load_members() if str(member.get("member_id", member.get("id"))) == member_id), None)


def member_record_by_id(member_id):
    member_id = str(member_id or "").strip()
    if not member_id:
        return None
    return next((member for member in load_members() if str(member.get("member_id", member.get("id"))) == member_id), None)


def start_member_session(member_id):
    session.clear()
    session["auth_role"] = "member"
    session["member_id"] = str(member_id or "").strip()


def start_supervisor_session():
    session.clear()
    session["auth_role"] = "supervisor"


def member_login_success_payload(member_id, redirect_to="/member"):
    member = member_record_by_id(member_id)
    return {
        "status": "ok",
        "authenticated": True,
        "role": "member",
        "member_id": str(member_id or "").strip(),
        "member_name": (member or {}).get("name") or f"Member {member_id}",
        "redirect": redirect_to,
        # Existing Flask session cookie remains authoritative. This token is a client-side marker.
        "session_token": f"member:{member_id}:{secrets.token_hex(8)}",
    }


def default_quick_test_member_id():
    active_members = [member for member in load_members() if member.get("active", True)]
    preferred = next((member for member in active_members if str(member.get("member_id", member.get("id"))) == TEST_MEMBER_LOGIN["member_id"]), None)
    if preferred:
        return str(preferred.get("member_id", preferred.get("id")))
    if active_members:
        first = active_members[0]
        return str(first.get("member_id", first.get("id")))
    members = load_members()
    if members:
        first = members[0]
        return str(first.get("member_id", first.get("id")))
    return None


def requested_member_id(payload=None):
    values = []
    if isinstance(payload, dict):
        values.extend([payload.get("member_id"), payload.get("selected_member_id")])
    values.extend([request.args.get("member_id"), request.args.get("selected_member_id")])
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def resolve_member_request_member(payload=None):
    if quick_test_mode_enabled():
        member_id = requested_member_id(payload) or default_quick_test_member_id()
        member = member_record_by_id(member_id)
        if member is None:
            return None, None, auth_json_error("Quick Test member record not found", 404)
        return str(member_id), member, None
    auth = current_auth()
    member_id = str(auth.get("member_id") or "").strip()
    if auth.get("role") != "member" or not member_id:
        return None, None, auth_json_error("Authentication required", 401)
    member = current_member_record()
    if member is None:
        return None, None, auth_json_error("Member record not found", 404)
    return member_id, member, None


def login_page_html(role_name, next_url=""):
    title = "Supervisor Login" if role_name == "supervisor" else "Member Login"
    intro = "Supervisor password required." if role_name == "supervisor" else "Use your member ID and password."
    member_field = """
      <label for="member_id">Member ID</label>
      <input id="member_id" name="member_id" autocomplete="username" required />
    """ if role_name == "member" else ""
    return render_template_string(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{{ title }}</title>
  <style>
    body{margin:0;min-height:100vh;display:grid;place-items:center;background:#08111f;color:#eef4ff;font-family:Arial,Helvetica,sans-serif}
    .card{width:min(420px,92vw);background:#0f1b2d;border:1px solid #243754;border-radius:20px;padding:22px;box-shadow:0 18px 40px rgba(0,0,0,.35)}
    h1{margin:0 0 8px;font-size:30px}
    p{margin:0 0 18px;color:#a7b8d8;line-height:1.45}
    form{display:grid;gap:12px}
    label{font-size:12px;font-weight:800;color:#a7b8d8;text-transform:uppercase;letter-spacing:.06em}
    input{height:42px;border-radius:12px;border:1px solid #243754;background:#16243a;color:#eef4ff;padding:0 12px}
    button{height:44px;border-radius:12px;border:1px solid rgba(143,125,255,.45);background:rgba(143,125,255,.18);color:#eef4ff;font-weight:900;cursor:pointer}
    .error{min-height:20px;color:#ffb6b6;font-size:14px}
  </style>
</head>
<body>
  <div class="card">
    <h1>{{ title }}</h1>
    <p>{{ intro }}</p>
    <form method="post" action="/api/auth/login">
      <input type="hidden" name="role" value="{{ role_name }}" />
      <input type="hidden" name="next" value="{{ next_url }}" />
      {{ member_field|safe }}
      <div>
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required />
      </div>
      <button type="submit">Sign In</button>
      <div class="error">{% if error %}{{ error }}{% endif %}</div>
    </form>
  </div>
</body>
</html>
        """,
        title=title,
        intro=intro,
        role_name=role_name,
        next_url=next_url,
        member_field=member_field,
        error=request.args.get("error", ""),
    )


def start_of_week_iso(date_value):
    dt = datetime.fromisoformat(str(date_value)[:10]).date()
    monday = dt - timedelta(days=dt.weekday())
    return monday.isoformat()


def normalize_shift_label(label):
    raw = str(label or "").strip().upper()
    if raw in {"AM", "AM SHIFT"}:
        return "AM"
    if raw in {"PM", "PM SHIFT"}:
        return "PM"
    return raw


def seat_identity_from_shift(shift, seat, index):
    date = str(shift.get("date") or "").strip()
    label = normalize_shift_label(shift.get("label"))
    role = str(seat.get("role") or "").strip().upper()
    seat_id = str(seat.get("seat_id") or "").strip()
    unit = str(shift.get("unit") or seat.get("unit") or "").strip()
    return {
        "seat_key": seat_id or f"{date}|{label}|{role}|{index}",
        "date": date,
        "label": label,
        "role": role,
        "unit": unit,
        "seat_index": index,
    }


def load_supervisor_state():
    data = load_json(SUPERVISOR_STATE_FILE, {"entries": [], "updated_at": None})
    if not isinstance(data, dict):
        data = {"entries": [], "updated_at": None}
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    data["entries"] = entries
    return data


def save_supervisor_state(payload):
    if not isinstance(payload, dict):
        payload = {"entries": [], "updated_at": now_iso()}
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    payload["entries"] = entries
    payload["updated_at"] = now_iso()
    save_json(SUPERVISOR_STATE_FILE, payload)


def index_supervisor_entries(state):
    indexed = {}
    for entry in state.get("entries", []):
        seat_key = str(entry.get("seat_key") or "").strip()
        if seat_key:
            indexed[seat_key] = entry
    return indexed


def upsert_supervisor_entry(state, entry):
    indexed = index_supervisor_entries(state)
    indexed[entry["seat_key"]] = entry
    state["entries"] = list(indexed.values())
    return state


def remove_supervisor_entry(state, seat_key):
    state["entries"] = [entry for entry in state.get("entries", []) if str(entry.get("seat_key") or "").strip() != seat_key]
    return state


def find_schedule_seat(schedule_payload, seat_key):
    for shift in schedule_payload.get("shifts", []):
        seats = shift.get("seats", [])
        for index, seat in enumerate(seats):
            identity = seat_identity_from_shift(shift, seat, index)
            if identity["seat_key"] == seat_key:
                assigned_member_id = str(seat.get("assigned") or "").strip() or None
                assigned_name = str(seat.get("assigned_name") or "").strip() or None
                return {
                    **identity,
                    "assigned_member_id": assigned_member_id,
                    "assigned_name": assigned_name,
                    "shift": shift,
                    "seat": seat,
                }
    return None


def clear_schedule_seat(schedule_payload, seat_key):
    for shift in schedule_payload.get("shifts", []):
        for index, seat in enumerate(shift.get("seats", [])):
            identity = seat_identity_from_shift(shift, seat, index)
            if identity["seat_key"] != seat_key:
                continue
            seat["assigned"] = None
            if "assigned_name" in seat:
                seat["assigned_name"] = None
            seat["display_open_alert"] = True
            seat["preserved_existing_assignment"] = False
            seat["fallback_used"] = False
            seat["fallback_reason"] = "supervisor_opened_seat"
            return True
    return False


def build_schedule_locked_from_state(schedule_payload, state):
    indexed = index_supervisor_entries(state)
    locked_shifts = []
    by_shift = {}

    for shift in schedule_payload.get("shifts", []):
        for index, seat in enumerate(shift.get("seats", [])):
            identity = seat_identity_from_shift(shift, seat, index)
            entry = indexed.get(identity["seat_key"])
            if not entry:
                continue

            state_name = str(entry.get("state") or "").strip().upper()
            if state_name not in {"DISPLAYED_FROZEN", "SUPERVISOR_LOCKED"}:
                continue

            shift_key = f"{identity['date']}|{identity['label']}|{identity['unit']}"
            target = by_shift.get(shift_key)
            if target is None:
                target = {
                    "shift_key": shift_key,
                    "date": identity["date"],
                    "label": f"{identity['label']} Shift" if identity["label"] in {"AM", "PM"} else identity["label"],
                    "unit": identity["unit"],
                    "seats": [],
                    "resolver": {"notes": []},
                }
                by_shift[shift_key] = target
                locked_shifts.append(target)

            seat_payload = {
                "seat_code": identity["role"][:1] if identity["role"] else str(identity["seat_index"]),
                "role": identity["role"],
                "locked": True,
                "source": "supervisor_state",
                "state": state_name,
            }
            if entry.get("assigned_name"):
                seat_payload["assigned_name"] = entry["assigned_name"]
            target["seats"].append(seat_payload)

    return {
        "build": {
            "generated_at": now_iso(),
            "source": "supervisor_state",
            "description": "Explicit displayed and supervisor-locked seats preserved by supervisor workflow",
            "shift_count": len(locked_shifts),
        },
        "shifts": locked_shifts,
    }


def persist_schedule_locked_from_state(schedule_payload, state):
    save_json(SCHEDULE_LOCKED_FILE, build_schedule_locked_from_state(schedule_payload, state))


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
    sync_auth_members()


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


def iso_today():
    return datetime.now(UTC).date()


def parse_iso_date(value):
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def normalized_availability_state(value):
    raw = str(value or "").strip().upper().replace(" ", "_")
    aliases = {
        "PREFERED": "PREFERRED",
        "PREFERRED": "PREFERRED",
        "AVAILABLE": "AVAILABLE",
        "AVAILIBLE": "AVAILABLE",
        "AVAILABLE_": "AVAILABLE",
        "DO_NOT_SCHEDULE": "DO_NOT_SCHEDULE",
        "DNS": "DO_NOT_SCHEDULE",
        "UNAVAILABLE": "DO_NOT_SCHEDULE",
        "BLOCK": "DO_NOT_SCHEDULE",
        "BLOCKED": "DO_NOT_SCHEDULE",
        "NO": "DO_NOT_SCHEDULE",
        "BLANK": "BLANK",
        "": "BLANK",
    }
    return aliases.get(raw, raw)


def is_declared_availability_intent(value):
    return normalized_availability_state(value) in {"PREFERRED", "AVAILABLE", "DO_NOT_SCHEDULE"}


def availability_backup_path(path):
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    directory = os.path.dirname(path)
    filename = os.path.basename(path)
    stem, ext = os.path.splitext(filename)
    return os.path.join(directory, f"{stem}.backup.{stamp}{ext or '.json'}")


def backup_json_file(path):
    backup_path = availability_backup_path(path)
    shutil.copy2(path, backup_path)
    return backup_path


def summarize_future_availability_intent(payload, today=None):
    today = today or iso_today()
    summary = {
        "future_dates_with_declared_intent": 0,
        "future_month_entries_with_declared_intent": 0,
        "members_with_future_declared_intent": 0,
        "pattern_members_with_declared_intent": 0,
        "pattern_entries_with_declared_intent": 0,
    }
    member_ids = set()

    months = payload.get("months", {})
    if isinstance(months, dict):
        for month_bucket in months.values():
            if not isinstance(month_bucket, dict):
                continue
            for member_id, member_bucket in month_bucket.items():
                if not isinstance(member_bucket, dict):
                    continue
                member_has_future = False
                for date_iso, day_entry in member_bucket.items():
                    date_obj = parse_iso_date(date_iso)
                    if not date_obj or date_obj <= today or not isinstance(day_entry, dict):
                        continue
                    day_has_intent = False
                    for label in ("AM", "PM"):
                        if is_declared_availability_intent(day_entry.get(label)):
                            summary["future_month_entries_with_declared_intent"] += 1
                            day_has_intent = True
                            member_has_future = True
                    if day_has_intent:
                        summary["future_dates_with_declared_intent"] += 1
                if member_has_future:
                    member_ids.add(str(member_id))

    patterns = payload.get("patterns_by_member", {})
    if isinstance(patterns, dict):
        for member_id, pattern_payload in patterns.items():
            if not isinstance(pattern_payload, dict):
                continue
            member_pattern_entries = 0
            for key in (
                "preferred_shift_types",
                "preferred",
                "available_shift_types",
                "available",
                "do_not_schedule_shift_types",
                "do_not_schedule",
                "dns",
            ):
                value = pattern_payload.get(key)
                if isinstance(value, list):
                    member_pattern_entries += sum(1 for item in value if str(item).strip())
            explicit = pattern_payload.get("statuses")
            if isinstance(explicit, dict):
                member_pattern_entries += sum(1 for value in explicit.values() if is_declared_availability_intent(value))
            if member_pattern_entries:
                summary["pattern_members_with_declared_intent"] += 1
                summary["pattern_entries_with_declared_intent"] += member_pattern_entries

    summary["members_with_future_declared_intent"] = len(member_ids)
    return summary


def clear_future_availability_intent(payload, today=None):
    today = today or iso_today()
    if not isinstance(payload, dict):
        payload = {"months": {}}

    summary = {
        "future_dates_cleared": 0,
        "future_month_entries_cleared": 0,
        "members_affected": 0,
        "pattern_members_cleared": 0,
        "pattern_entries_cleared": 0,
        "blank_state": "blank",
    }
    affected_members = set()

    months = payload.get("months", {})
    if not isinstance(months, dict):
        payload["months"] = {}
        months = payload["months"]

    for month_key, month_bucket in months.items():
        if not isinstance(month_bucket, dict):
            continue
        for member_id, member_bucket in month_bucket.items():
            if not isinstance(member_bucket, dict):
                continue
            member_changed = False
            for date_iso, day_entry in member_bucket.items():
                date_obj = parse_iso_date(date_iso)
                if not date_obj or date_obj <= today or not isinstance(day_entry, dict):
                    continue
                day_changed = False
                for label in ("AM", "PM"):
                    if is_declared_availability_intent(day_entry.get(label)):
                        day_entry[label] = "blank"
                        summary["future_month_entries_cleared"] += 1
                        day_changed = True
                        member_changed = True
                if day_changed:
                    summary["future_dates_cleared"] += 1
            if member_changed:
                affected_members.add(str(member_id))

    patterns = payload.get("patterns_by_member", {})
    if isinstance(patterns, dict):
        for member_id, pattern_payload in patterns.items():
            if not isinstance(pattern_payload, dict):
                continue
            member_pattern_changes = 0
            for key in (
                "preferred_shift_types",
                "preferred",
                "available_shift_types",
                "available",
                "do_not_schedule_shift_types",
                "do_not_schedule",
                "dns",
            ):
                value = pattern_payload.get(key)
                if isinstance(value, list) and value:
                    member_pattern_changes += sum(1 for item in value if str(item).strip())
                    pattern_payload[key] = []
            explicit = pattern_payload.get("statuses")
            if isinstance(explicit, dict):
                explicit_changes = 0
                for pattern_key, raw_status in list(explicit.items()):
                    if is_declared_availability_intent(raw_status):
                        explicit[pattern_key] = "blank"
                        explicit_changes += 1
                member_pattern_changes += explicit_changes
            if member_pattern_changes:
                summary["pattern_members_cleared"] += 1
                summary["pattern_entries_cleared"] += member_pattern_changes
                affected_members.add(str(member_id))

    summary["members_affected"] = len(affected_members)
    summary["remaining"] = summarize_future_availability_intent(payload, today=today)
    summary["resolver_fallback"] = {
        "shift_builder_uses": "explicit months date entries only",
        "resolver_uses": "exact months entries first, then patterns_by_member fallback",
        "fallback_source": "availability.json patterns_by_member and derived statuses",
    }
    return payload, summary


def member_roster_payload():
    roster = []
    for member in load_members():
        roster.append(
            {
                "member_id": str(member.get("member_id", member.get("id"))),
                "name": member.get("name") or f"Member {member.get('member_id', member.get('id'))}",
                "ops_cert": member.get("ops_cert") or member.get("cert") or member.get("raw_cert"),
                "birthday": member.get("birthday"),
                "birthday_mmdd": member.get("birthday_mmdd"),
            }
        )
    return roster


def extract_member_availability(member_id):
    payload = load_availability_payload()
    filtered = {"months": {}, "patterns_by_member": {}}
    for month_key, month_bucket in payload.get("months", {}).items():
        if not isinstance(month_bucket, dict):
            continue
        member_bucket = month_bucket.get(member_id)
        if isinstance(member_bucket, dict):
            filtered["months"][month_key] = {member_id: member_bucket}
    patterns = payload.get("patterns_by_member", {})
    if isinstance(patterns, dict) and isinstance(patterns.get(member_id), dict):
        filtered["patterns_by_member"][member_id] = patterns[member_id]
    return filtered


def apply_member_profile_update(member, payload):
    employment = member.setdefault("employment", {}) if isinstance(member, dict) else {}
    preferences = member.setdefault("preferences", {}) if isinstance(member, dict) else {}
    scheduler = member.setdefault("scheduler", {}) if isinstance(member, dict) else {}
    shift_preference = preferences.setdefault("shift_preference", {})

    if "preferred_weekly_hour_cap" in payload:
        value = payload.get("preferred_weekly_hour_cap")
        employment["preferred_weekly_hour_cap"] = None if value in (None, "") else float(value)
    if "ampm" in payload:
        preferences["ampm"] = str(payload.get("ampm") or "no_preference")
    if "shift24" in payload:
        preferences["shift24"] = str(payload.get("shift24") or "no_preference")
    if "swap_strategy" in payload:
        shift_preference["swap_strategy"] = str(payload.get("swap_strategy") or "allow")
    if "shift_style" in payload:
        shift_preference["style"] = str(payload.get("shift_style") or "prn_only")
    if "rotation_track" in payload:
        track = str(payload.get("rotation_track") or "").strip().upper() or None
        shift_preference["rotation_track"] = track
        shift_preference["rotation_role"] = "day" if track in {"A", "B"} else "night" if track in {"C", "D"} else None
        shift_preference["relief_partner_track"] = {"A": "C", "B": "D", "C": "A", "D": "B"}.get(track)
        member["rotation"] = {"pair": "AC" if track in {"A", "C"} else "BD", "role": track} if track in {"A", "B", "C", "D"} else None
    if "avoid_with" in payload:
        scheduler["avoid_with"] = [str(value) for value in payload.get("avoid_with", []) if str(value).strip()]


def apply_member_availability_update(member_id, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("months"), dict):
        raise ValueError("Availability payload must contain a months object")

    full_payload = load_availability_payload()
    cutoff_date = datetime.now(UTC).date() + timedelta(days=14)

    for month_key, month_bucket in payload["months"].items():
        if not isinstance(month_bucket, dict):
            continue
        member_bucket = month_bucket.get(member_id, {})
        if not isinstance(member_bucket, dict):
            continue
        for date_iso, day_entry in member_bucket.items():
            try:
                date_obj = datetime.fromisoformat(str(date_iso)[:10]).date()
            except ValueError:
                continue
            if date_obj < cutoff_date:
                raise ValueError("Availability within the next 2 weeks is locked for member editing")
            full_payload.setdefault("months", {}).setdefault(month_key, {}).setdefault(member_id, {})
            if isinstance(day_entry, dict):
                full_payload["months"][month_key][member_id][date_iso] = day_entry

    save_availability_payload(full_payload)


# =========================
# STATIC FILE ROUTES
# =========================

@app.route("/")
def root():
    auth = current_auth()
    if auth["role"] == "supervisor":
        return redirect("/docs/supervisor.html")
    if auth["role"] == "member":
        return redirect("/docs/member.html")
    return redirect("/login/supervisor")


@app.route("/docs")
def docs_root():
    return redirect("/")


@app.route("/docs/<path:path>")
def serve_docs(path):
    lowered = str(path or "").lower()
    if lowered == "supervisor.html" and current_auth()["role"] != "supervisor":
        return login_redirect("supervisor")
    if lowered == "member.html" and not quick_test_mode_enabled() and current_auth()["role"] not in {"member", "supervisor"}:
        return login_redirect("member")
    return send_from_directory(DOCS_DIR, path)


@app.route("/debug/<path:path>")
def serve_debug(path):
    return send_from_directory(DEBUG_DIR, path)


@app.route("/wallboard")
def wallboard_shortcut():
    return redirect("/docs/wallboard.html")


@app.route("/supervisor")
def supervisor_shortcut():
    if current_auth()["role"] != "supervisor":
        return login_redirect("supervisor")
    return redirect("/docs/supervisor.html")


@app.route("/member")
def member_shortcut():
    if not quick_test_mode_enabled() and current_auth()["role"] not in {"member", "supervisor"}:
        return login_redirect("member")
    return redirect("/docs/member.html")


@app.route("/login")
def login_shortcut():
    next_url = request.args.get("next", "/member")
    return redirect(f"/login.html?next={next_url}")


@app.route("/login.html")
def login_html_page():
    return send_from_directory(DOCS_DIR, "login.html")


@app.route("/login/supervisor")
def login_supervisor_page():
    return login_page_html("supervisor", request.args.get("next", "/docs/supervisor.html"))


@app.route("/login/member")
def login_member_page():
    next_url = request.args.get("next", "/member")
    return redirect(f"/login.html?next={next_url}")


# =========================
# AUTH
# =========================

@app.route("/api/auth/session", methods=["GET"])
def auth_session():
    auth = current_auth()
    payload = {
        "authenticated": auth["authenticated"],
        "role": auth["role"],
        "member_id": auth["member_id"],
        "quick_test_mode": quick_test_mode_enabled(),
        "auth_mode": "quick_test" if quick_test_mode_enabled() and not auth["authenticated"] else "real_login",
        "build_code": BUILD_CODE,
        "public_base_url": current_public_base_url(),
    }
    if auth["role"] == "member":
        member = current_member_record()
        if member:
            payload["member_name"] = member.get("name") or f"Member {auth['member_id']}"
    return jsonify(payload)


@app.route("/api/login", methods=["POST"])
def api_login():
    payload = request.get_json(silent=True) or request.form or {}
    username = str(payload.get("username") or payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "").strip()
    next_url = str(payload.get("next") or "/member").strip() or "/member"
    if username != TEST_MEMBER_LOGIN["username"] or password != TEST_MEMBER_LOGIN["password"]:
        return auth_json_error("Invalid credentials", 401)
    member = member_record_by_id(TEST_MEMBER_LOGIN["member_id"])
    if not member:
        return auth_json_error("Configured test member is missing", 500)
    start_member_session(TEST_MEMBER_LOGIN["member_id"])
    response = member_login_success_payload(TEST_MEMBER_LOGIN["member_id"], next_url)
    response["build_code"] = BUILD_CODE
    response["auth_mode"] = "real_login"
    response["quick_test_mode"] = quick_test_mode_enabled()
    return jsonify(response)


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json(silent=True) if request.is_json else request.form
    role = str(payload.get("role") or "").strip().lower()
    password = str(payload.get("password") or "").strip()
    next_url = str(payload.get("next") or "").strip()
    sync_auth_members()
    auth_users = load_auth_users()

    if role == "supervisor":
        stored_hash = auth_users.get("supervisor", {}).get("password_hash")
        valid = (
            (stored_hash and verify_password(password, stored_hash))
            or (env_supervisor_password() and hmac.compare_digest(password, env_supervisor_password()))
            or (env_override_password() and hmac.compare_digest(password, env_override_password()))
        )
        if not valid:
            if request.is_json:
                return auth_json_error("Invalid supervisor password", 401)
            return redirect("/login/supervisor?error=Invalid+password")
        start_supervisor_session()
        if request.is_json:
            return jsonify({"status": "ok", "role": "supervisor"})
        return redirect(next_url or "/docs/supervisor.html")

    if role == "member":
        member_id = str(payload.get("member_id") or "").strip()
        if not member_id or not password:
            if request.is_json:
                return auth_json_error("member_id and password are required", 400)
            return redirect("/login/member?error=Missing+credentials")
        member_entry = auth_users.get("members", {}).get(member_id)
        if member_entry is None:
            if request.is_json:
                return auth_json_error("Unknown member account", 404)
            return redirect("/login/member?error=Unknown+member")
        stored_hash = member_entry.get("password_hash")
        if not stored_hash or not verify_password(password, stored_hash):
            if request.is_json:
                return auth_json_error("Invalid member password", 401)
            return redirect("/login/member?error=Invalid+credentials")
        start_member_session(member_id)
        if request.is_json:
            response = member_login_success_payload(member_id, next_url or "/member")
            response["build_code"] = BUILD_CODE
            response["auth_mode"] = "real_login"
            response["quick_test_mode"] = quick_test_mode_enabled()
            return jsonify(response)
        return redirect(next_url or "/docs/member.html")

    return auth_json_error("Unsupported login role", 400) if request.is_json else redirect("/login/member?error=Unsupported+role")


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth/change_password", methods=["POST"])
@require_role("member")
def auth_change_password():
    payload = request.get_json(silent=True) or {}
    current_password = str(payload.get("current_password") or "")
    new_password = str(payload.get("new_password") or "")
    confirm_password = str(payload.get("confirm_password") or "")
    if not current_password or not new_password or not confirm_password:
        return auth_json_error("All password fields are required", 400)
    if new_password != confirm_password:
        return auth_json_error("New password and confirmation do not match", 400)
    if len(new_password) < 8:
        return auth_json_error("New password must be at least 8 characters", 400)

    auth = current_auth()
    auth_users = load_auth_users()
    if auth["role"] == "supervisor":
        stored_hash = auth_users.get("supervisor", {}).get("password_hash")
        valid = (
            (stored_hash and verify_password(current_password, stored_hash))
            or (env_supervisor_password() and hmac.compare_digest(current_password, env_supervisor_password()))
            or (env_override_password() and hmac.compare_digest(current_password, env_override_password()))
        )
        if not valid:
            return auth_json_error("Current password is incorrect", 400)
        auth_users["supervisor"]["password_hash"] = hash_password(new_password)
        auth_users["supervisor"]["updated_at"] = now_iso()
        save_auth_users(auth_users)
        return jsonify({"status": "ok"})

    member_id = auth["member_id"]
    member_entry = auth_users.get("members", {}).get(member_id, {})
    stored_hash = member_entry.get("password_hash")
    if not stored_hash or not verify_password(current_password, stored_hash):
        return auth_json_error("Current password is incorrect", 400)
    member_entry["password_hash"] = hash_password(new_password)
    member_entry["must_change_password"] = False
    member_entry["updated_at"] = now_iso()
    auth_users["members"][member_id] = member_entry
    save_auth_users(auth_users)
    return jsonify({"status": "ok"})


@app.route("/api/change-password", methods=["POST"])
@require_role("member")
def auth_change_password_alias():
    return auth_change_password()


@app.route("/api/auth/reset_member_password", methods=["POST"])
@require_role("supervisor")
def auth_reset_member_password():
    payload = request.get_json(silent=True) or {}
    member_id = str(payload.get("member_id") or "").strip()
    new_password = str(payload.get("new_password") or "").strip()
    if not member_id or not new_password:
        return auth_json_error("member_id and new_password are required", 400)
    if len(new_password) < 8:
        return auth_json_error("Temporary password must be at least 8 characters", 400)
    auth_users = sync_auth_members()
    if member_id not in auth_users.get("members", {}):
        return auth_json_error("Unknown member account", 404)
    auth_users["members"][member_id]["password_hash"] = hash_password(new_password)
    auth_users["members"][member_id]["must_change_password"] = True
    auth_users["members"][member_id]["updated_at"] = now_iso()
    save_auth_users(auth_users)
    return jsonify({"status": "ok", "member_id": member_id})


# =========================
# MEMBERS
# =========================

@app.route("/api/members", methods=["GET"])
def get_members():
    if not quick_test_mode_enabled() and current_auth()["role"] != "supervisor":
        return auth_json_error("Supervisor access required", 403)
    return jsonify(load_members_payload())


@app.route("/api/wallboard_members", methods=["GET"])
def get_wallboard_members():
    return jsonify(member_roster_payload())


@app.route("/api/members", methods=["POST"])
@require_role("supervisor")
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
@require_role("supervisor")
def get_availability():
    return jsonify(load_availability_payload())


@app.route("/api/availability", methods=["POST"])
@require_role("supervisor")
def save_availability():
    incoming = request.get_json(silent=True)
    if not isinstance(incoming, dict):
        return jsonify({"error": "Availability payload must be an object"}), 400

    if "months" not in incoming or not isinstance(incoming.get("months"), dict):
        return jsonify({"error": "Availability payload must contain a months object"}), 400

    save_availability_payload(incoming)
    return jsonify({"status": "ok"})


@app.route("/api/admin/availability/clear_future", methods=["POST"])
@require_role("supervisor")
def clear_future_availability():
    payload = load_availability_payload()
    if not os.path.exists(AVAILABILITY_FILE):
        return jsonify({"error": "availability.json not found"}), 404

    try:
        backup_path = backup_json_file(AVAILABILITY_FILE)
        cleared_payload, summary = clear_future_availability_intent(payload)
        save_availability_payload(cleared_payload)
    except Exception as exc:
        return jsonify({"error": f"Failed to clear future availability: {exc}"}), 500

    return jsonify({
        "status": "ok",
        "backup_file": os.path.basename(backup_path),
        "backup_path": backup_path,
        **summary,
    })


@app.route("/api/member/context", methods=["GET"])
def get_member_context():
    member_id, member, error = resolve_member_request_member()
    if error:
        return error
    return jsonify(
        {
            "member": member,
            "roster": member_roster_payload(),
            "availability": extract_member_availability(member_id),
            "schedule": load_json(SCHEDULE_FILE, {}),
            "editing_lock_days": 14,
            "auth_mode": "quick_test" if quick_test_mode_enabled() else "real_login",
            "quick_test_mode": quick_test_mode_enabled(),
            "selected_member_id": member_id,
        }
    )


@app.route("/api/me", methods=["GET"])
@require_role("member")
def api_me():
    member = current_member_record()
    if member is None:
        return auth_json_error("Member record not found", 404)
    return jsonify({"member": member, "role": current_auth()["role"]})


@app.route("/api/member/profile", methods=["POST"])
def save_member_profile():
    payload = request.get_json(silent=True) or {}
    member_id, _, error = resolve_member_request_member(payload)
    if error:
        return error
    members_payload = load_members_payload()
    members = members_payload.get("members", [])
    target = next((member for member in members if str(member.get("member_id", member.get("id"))) == member_id), None)
    if target is None:
        return auth_json_error("Member record not found", 404)
    apply_member_profile_update(target, payload)
    save_members_payload(members_payload)
    return jsonify({
        "status": "ok",
        "member_id": member_id,
        "auth_mode": "quick_test" if quick_test_mode_enabled() else "real_login",
        "quick_test_mode": quick_test_mode_enabled(),
    })


@app.route("/api/member/availability", methods=["POST"])
def save_member_availability():
    payload = request.get_json(silent=True) or {}
    member_id, _, error = resolve_member_request_member(payload)
    if error:
        return error
    try:
        apply_member_availability_update(member_id, payload)
    except ValueError as exc:
        return auth_json_error(str(exc), 400)
    return jsonify({
        "status": "ok",
        "member_id": member_id,
        "auth_mode": "quick_test" if quick_test_mode_enabled() else "real_login",
        "quick_test_mode": quick_test_mode_enabled(),
    })


@app.route("/api/my-availability", methods=["GET"])
@require_role("member")
def get_my_availability():
    auth = current_auth()
    return jsonify(extract_member_availability(auth["member_id"]))


@app.route("/api/my-availability", methods=["POST"])
@require_role("member")
def save_my_availability():
    return save_member_availability()


# =========================
# SHIFTS
# =========================

@app.route("/api/shifts", methods=["GET"])
@require_role("supervisor")
def get_shifts():
    return jsonify(load_shifts())


@app.route("/api/shifts", methods=["POST"])
@require_role("supervisor")
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
@require_role("supervisor")
def get_settings():
    return jsonify(load_settings())


@app.route("/api/settings", methods=["POST"])
@require_role("supervisor")
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


def preview_shift_builder():
    from engine.shift_builder import build_shift_skeletons

    return build_shift_skeletons(
        members=load_members(),
        settings=load_settings(),
        availability_payload=load_availability_payload(),
    )


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


def preview_resolver(shifts_override=None):
    from engine.resolver import resolve

    shifts = shifts_override if isinstance(shifts_override, list) else load_shifts()
    ctx = {
        "members": load_members(),
        "shifts": shifts,
        "settings": load_settings(),
        "availability": load_availability_payload(),
        "schedule_locked": load_json(SCHEDULE_LOCKED_FILE, {}),
        "rotation_templates": load_json(ROTATION_TEMPLATES_FILE, {}),
        "build": {
            "generated_at": now_iso()
        }
    }
    return resolve(ctx)


# =========================
# GENERATE SCHEDULE
# =========================

@app.route("/api/generate", methods=["POST"])
@require_role("supervisor")
def generate_schedule():
    built_shifts = run_shift_builder()
    result = run_resolver()

    shift_count = len(built_shifts) if isinstance(built_shifts, list) else 0

    if isinstance(result, dict):
        result["build_stats"] = {"shift_count": shift_count}

    return jsonify(result)


@app.route("/api/build_shifts", methods=["POST"])
@require_role("supervisor")
def build_shifts_only():
    built_shifts = run_shift_builder()
    shift_count = len(built_shifts) if isinstance(built_shifts, list) else 0
    return jsonify({
        "status": "ok",
        "shift_count": shift_count,
        "shifts": built_shifts
    })


@app.route("/api/schedule_locked", methods=["GET"])
@require_role("supervisor")
def get_schedule_locked():
    return jsonify(load_json(SCHEDULE_LOCKED_FILE, {}))


@app.route("/api/schedule_locked", methods=["POST"])
@require_role("supervisor")
def save_schedule_locked():
    incoming = request.get_json(silent=True)
    if not isinstance(incoming, dict):
        return jsonify({"error": "schedule_locked payload must be an object"}), 400
    save_json(SCHEDULE_LOCKED_FILE, incoming)
    return jsonify({"status": "ok"})


@app.route("/api/supervisor/state", methods=["GET"])
@require_role("supervisor")
def get_supervisor_state():
    return jsonify(load_supervisor_state())


@app.route("/api/supervisor/state", methods=["POST"])
@require_role("supervisor")
def save_supervisor_state_route():
    incoming = request.get_json(silent=True)
    if not isinstance(incoming, dict):
        return jsonify({"error": "Supervisor state payload must be an object"}), 400
    save_supervisor_state(incoming)
    schedule_payload = load_json(SCHEDULE_FILE, {})
    if isinstance(schedule_payload, dict):
        persist_schedule_locked_from_state(schedule_payload, incoming)
    return jsonify({"status": "ok"})


@app.route("/api/supervisor/publish_week", methods=["POST"])
@require_role("supervisor")
def supervisor_publish_week():
    payload = request.get_json(silent=True) or {}
    week_start = str(payload.get("week_start") or "").strip()
    if not week_start:
        return jsonify({"error": "week_start is required"}), 400

    schedule_payload = load_json(SCHEDULE_FILE, {})
    state = load_supervisor_state()
    changes = 0

    for shift in schedule_payload.get("shifts", []):
        date_value = str(shift.get("date") or "").strip()
        if not date_value or start_of_week_iso(date_value) != week_start:
            continue
        for index, seat in enumerate(shift.get("seats", [])):
            if seat.get("active") is False:
                continue
            identity = seat_identity_from_shift(shift, seat, index)
            assigned_member_id = str(seat.get("assigned") or "").strip() or None
            assigned_name = str(seat.get("assigned_name") or "").strip() or None
            if assigned_member_id or assigned_name:
                state = upsert_supervisor_entry(
                    state,
                    {
                        **identity,
                        "state": "DISPLAYED_FROZEN",
                        "assigned_member_id": assigned_member_id,
                        "assigned_name": assigned_name,
                        "updated_at": now_iso(),
                    },
                )
            else:
                state = upsert_supervisor_entry(
                    state,
                    {
                        **identity,
                        "state": "OPEN",
                        "assigned_member_id": None,
                        "assigned_name": None,
                        "updated_at": now_iso(),
                    },
                )
            changes += 1

    save_supervisor_state(state)
    persist_schedule_locked_from_state(schedule_payload, state)
    return jsonify({"status": "ok", "week_start": week_start, "updated_seats": changes})


@app.route("/api/supervisor/drop_seat", methods=["POST"])
@require_role("supervisor")
def supervisor_drop_seat():
    payload = request.get_json(silent=True) or {}
    seat_key = str(payload.get("seat_key") or "").strip()
    if not seat_key:
        return jsonify({"error": "seat_key is required"}), 400

    schedule_payload = load_json(SCHEDULE_FILE, {})
    seat_info = find_schedule_seat(schedule_payload, seat_key)
    if seat_info is None:
        return jsonify({"error": "seat_key not found in current schedule"}), 404

    state = load_supervisor_state()
    state = upsert_supervisor_entry(
        state,
        {
            **{k: seat_info[k] for k in ("seat_key", "date", "label", "role", "unit", "seat_index")},
            "state": "DROPPED",
            "assigned_member_id": None,
            "assigned_name": None,
            "updated_at": now_iso(),
        },
    )
    clear_schedule_seat(schedule_payload, seat_key)
    save_json(SCHEDULE_FILE, schedule_payload)
    save_supervisor_state(state)
    persist_schedule_locked_from_state(schedule_payload, state)
    return jsonify({"status": "ok", "seat_key": seat_key, "state": "DROPPED"})


@app.route("/api/supervisor/open_seat", methods=["POST"])
@require_role("supervisor")
def supervisor_open_seat():
    payload = request.get_json(silent=True) or {}
    seat_key = str(payload.get("seat_key") or "").strip()
    if not seat_key:
        return jsonify({"error": "seat_key is required"}), 400

    schedule_payload = load_json(SCHEDULE_FILE, {})
    seat_info = find_schedule_seat(schedule_payload, seat_key)
    if seat_info is None:
        return jsonify({"error": "seat_key not found in current schedule"}), 404

    state = load_supervisor_state()
    state = upsert_supervisor_entry(
        state,
        {
            **{k: seat_info[k] for k in ("seat_key", "date", "label", "role", "unit", "seat_index")},
            "state": "OPEN",
            "assigned_member_id": None,
            "assigned_name": None,
            "updated_at": now_iso(),
        },
    )
    clear_schedule_seat(schedule_payload, seat_key)
    save_json(SCHEDULE_FILE, schedule_payload)
    save_supervisor_state(state)
    persist_schedule_locked_from_state(schedule_payload, state)
    return jsonify({"status": "ok", "seat_key": seat_key, "state": "OPEN"})


@app.route("/api/supervisor/lock_seat", methods=["POST"])
@require_role("supervisor")
def supervisor_lock_seat():
    payload = request.get_json(silent=True) or {}
    seat_key = str(payload.get("seat_key") or "").strip()
    if not seat_key:
        return jsonify({"error": "seat_key is required"}), 400

    schedule_payload = load_json(SCHEDULE_FILE, {})
    seat_info = find_schedule_seat(schedule_payload, seat_key)
    if seat_info is None:
        return jsonify({"error": "seat_key not found in current schedule"}), 404

    state = load_supervisor_state()
    state = upsert_supervisor_entry(
        state,
        {
            **{k: seat_info[k] for k in ("seat_key", "date", "label", "role", "unit", "seat_index")},
            "state": "SUPERVISOR_LOCKED",
            "assigned_member_id": seat_info["assigned_member_id"],
            "assigned_name": seat_info["assigned_name"],
            "updated_at": now_iso(),
        },
    )
    save_supervisor_state(state)
    persist_schedule_locked_from_state(schedule_payload, state)
    return jsonify({"status": "ok", "seat_key": seat_key, "state": "SUPERVISOR_LOCKED"})


@app.route("/api/supervisor/resolve_week", methods=["POST"])
@require_role("supervisor")
def supervisor_resolve_week():
    payload = request.get_json(silent=True) or {}
    dry_run = bool(payload.get("dry_run", False))

    built_shifts = preview_shift_builder() if dry_run else run_shift_builder()
    result = preview_resolver(built_shifts) if dry_run else run_resolver()
    shift_count = len(built_shifts) if isinstance(built_shifts, list) else 0

    return jsonify({
        "status": "ok",
        "dry_run": dry_run,
        "shift_count": shift_count,
        "schedule": result,
    })


# =========================
# GET SCHEDULE (API)
# =========================

@app.route("/api/schedule", methods=["GET"])
def get_schedule_api():
    return fast_json_file_response(SCHEDULE_FILE)


# =========================
# HEALTH CHECK
# =========================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "time": now_iso(),
        "build_code": BUILD_CODE,
        "quick_test_mode": quick_test_mode_enabled(),
        "auth_mode": "quick_test" if quick_test_mode_enabled() else "real_login",
        "public_base_url": current_public_base_url(),
        "allowed_origins": SC_ALLOWED_ORIGINS,
    })


# =========================
# RUN
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=SC_FLASK_DEBUG)
