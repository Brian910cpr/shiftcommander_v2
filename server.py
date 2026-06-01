import json
import os
import base64
import hashlib
import hmac
import secrets
import shutil
import sys
import time
import re
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import date, datetime, timedelta, UTC
from functools import wraps
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, send_from_directory, redirect, session, render_template_string, Response
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from engine.display_normalizer import normalize_wallboard_display
from engine.member_dashboard import build_member_dashboard
from engine.schedule_lifecycle import (
    build_supervisor_schedule_queue,
    classify_shift_lifecycle,
    current_commit_window,
    get_commit_policy,
    get_next_commit_at,
    preview_schedule_commit,
)
from engine.shift_change_review import review_shift_change_request

SERVER_IMPORT_STARTED = time.perf_counter()


def startup_log(message):
    elapsed_ms = (time.perf_counter() - SERVER_IMPORT_STARTED) * 1000
    print(f"[shiftcommander-startup] {elapsed_ms:.1f}ms {message}", file=sys.stderr, flush=True)


startup_log("server import started")
app = Flask(__name__)
startup_log("Flask app created")
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
PUBLIC_SCHEDULE_FILE = os.path.join(DOCS_DIR, "data", "schedule.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PUBLIC_SETTINGS_FILE = os.path.join(DOCS_DIR, "data", "settings.json")
AVAILABILITY_FILE = os.path.join(DATA_DIR, "availability.json")
INFERRED_PREFERENCES_FILE = os.path.join(DATA_DIR, "inferred_preferences.json")
SCHEDULE_LOCKED_FILE = os.path.join(DATA_DIR, "schedule_locked.json")
ROLLOUT_IMPORT_FILE = os.path.join(DATA_DIR, "rollout_import.json")
ROTATION_TEMPLATES_FILE = os.path.join(DATA_DIR, "rotation_templates.json")
SWAP_REQUESTS_FILE = os.path.join(DATA_DIR, "swap_requests.json")
SHIFT_CHANGE_REQUESTS_FILE = os.path.join(DATA_DIR, "shift_change_requests.json")
SUPERVISOR_STATE_FILE = os.path.join(DATA_DIR, "supervisor_state.json")
LIVE_BETA_TRANSACTIONS_FILE = os.path.join(DATA_DIR, "live_beta_transactions.json")
GOOGLE_CALENDAR_JUNE_MIRROR_FILE = os.path.join(DATA_DIR, "google_calendar_june_2026_mirror.json")
GOOGLE_CALENDAR_MIRROR_CACHE_SECONDS = 15 * 60
ADR_EMPLOYEE_SCHEDULE_CALENDAR_ID = "2fbc3612e56a0a2ce28fe826443e20a88c500e1c5b3c56b126cb4afb88fd233e@group.calendar.google.com"
ADR_EMPLOYEE_SCHEDULE_ICAL_URL = (
    "https://calendar.google.com/calendar/ical/"
    "2fbc3612e56a0a2ce28fe826443e20a88c500e1c5b3c56b126cb4afb88fd233e%40group.calendar.google.com"
    "/public/basic.ics"
)
LOCAL_TZ = ZoneInfo("America/New_York")
AUTH_USERS_FILE = os.path.join(DATA_DIR, "auth_users.json")
CALENDAR_MARKERS_FILE = os.path.join(DATA_DIR, "calendar_markers.json")
PUBLIC_CALENDAR_MARKERS_FILE = os.path.join(DOCS_DIR, "data", "calendar_markers.json")
DEFAULT_CAREER_FIRE_DRIVER_RULES = {
    "enabled": True,
    "label": "Career Fire Driver",
    "effective_start": "2026-06-01",
    "days": ["MO", "TU", "TH"],
    "start_time": "08:00",
    "end_time": "18:00",
    "normal_shift_start": "06:00",
    "show_transition_watch": True,
    "transition_watch_label": "0800 Relief Arrival",
    "transition_watch_style": "duty_driver_black_small",
    "counts_as_required_coverage": False,
    "creates_holdover_assignment": False,
    "counts_toward_driver_coverage": True,
    "counts_toward_emt_coverage": True,
    "counts_as_named_member_assignment": False,
    "visible_on_wallboard": True,
}
DEFAULT_MEMBER_ACCOMMODATIONS = {
    "effective_start_offsets": [
        {
            "member_id": "181",
            "member_name": "Anna Squires",
            "active": True,
            "normal_shift_start": "06:00",
            "effective_start": "08:00",
            "applies_to_labels": ["AM"],
            "watch_label": "0600-0800 Watch",
            "visible_on_wallboard": True,
            "counts_as_required_coverage": False,
            "creates_holdover_assignment": False,
        }
    ]
}
DEFAULT_DISPLAY_HORIZON = {
    "mode": "temporary_fixed_until_date",
    "temporary_fixed_end_date": "2026-06-30",
    "resume_rolling_after_date": "2026-06-30",
    "rolling_weeks_default": 5,
    "admin_rolling_weeks": 5,
    "enabled": True,
}
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
SC_DEMO_SUPERVISOR_BYPASS = env_flag("SC_DEMO_SUPERVISOR_BYPASS", SC_QUICK_TEST_MODE)
SC_ALLOWED_ORIGINS = parse_csv_env(
    "SC_ALLOWED_ORIGINS",
    [
        "https://adr-fr.org",
        "https://www.adr-fr.org",
        "https://sc.adr-fr.org",
        "https://sc-api.adr-fr.org",
        "https://shiftcommander.pages.dev",
        "https://06266bdf.shiftcommander.pages.dev",
        "https://base44.com",
        "https://app.base44.com",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:8001",
        "http://localhost:8001",
    ],
)
for required_origin in [
    "https://shiftcommander.pages.dev",
    "https://06266bdf.shiftcommander.pages.dev",
    "https://sc.adr-fr.org",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
]:
    if required_origin not in SC_ALLOWED_ORIGINS:
        SC_ALLOWED_ORIGINS.append(required_origin)
SC_ALLOWED_ORIGIN_SUFFIXES = tuple(parse_csv_env("SC_ALLOWED_ORIGIN_SUFFIXES", [".base44.app", ".base44.com"]))
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
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-ShiftCommander-Beta-Session"
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


def load_live_beta_transactions():
    payload = load_json(LIVE_BETA_TRANSACTIONS_FILE, {"transactions": []})
    if not isinstance(payload, dict):
        payload = {"transactions": []}
    if not isinstance(payload.get("transactions"), list):
        payload["transactions"] = []
    return payload


def rollout_status_payload():
    return {
        "live_beta": True,
        "transactions_live": True,
        "may_24_31": {
            "source": "whiteboard_manual_override",
            "logic_mode": "mirror_only",
            "transactions_live": True,
        },
        "june_2026": {
            "source": "google_calendar_mirror",
            "logic_mode": "mirror_only",
            "transactions_live": True,
        },
        "july_forward": {
            "source": "shiftcommander",
            "logic_mode": "normal",
            "transactions_live": True,
        },
        "august_and_beyond": {
            "priority_focus": True,
            "availability_collection": True,
            "resolver_training_or_planning_allowed": True,
            "requires_actual_member_submitted_availability": True,
        },
        "member_message": (
            "ShiftCommander is live. The current May/June board reflects the known schedule, "
            "but availability, swaps, drops, and pickup requests submitted here are real and "
            "will be reported for supervisor review. Please focus especially on entering "
            "availability for August and beyond."
        ),
    }


def record_live_beta_transaction(action_type, actor_member_id=None, affected=None, before=None, after=None, source="member_portal"):
    payload = load_live_beta_transactions()
    transaction = {
        "id": f"live_beta_{int(time.time() * 1000)}_{secrets.token_hex(4)}",
        "live_beta": True,
        "transactions_live": True,
        "requires_supervisor_review": True,
        "action_type": str(action_type or "unknown"),
        "source": source,
        "actor_member_id": str(actor_member_id or "").strip() or None,
        "created_at": now_iso(),
        "affected": affected or {},
        "before": before,
        "after": after,
    }
    payload["transactions"].append(transaction)
    payload["updated_at"] = transaction["created_at"]
    save_json(LIVE_BETA_TRANSACTIONS_FILE, payload)
    return transaction


def load_shift_change_requests_payload():
    payload = load_json(SHIFT_CHANGE_REQUESTS_FILE, {"requests": []})
    if isinstance(payload, list):
        payload = {"requests": payload}
    if not isinstance(payload, dict):
        payload = {"requests": []}
    if not isinstance(payload.get("requests"), list):
        payload["requests"] = []
    return payload


def save_shift_change_requests_payload(payload):
    if not isinstance(payload, dict):
        payload = {"requests": []}
    if not isinstance(payload.get("requests"), list):
        payload["requests"] = []
    payload["updated_at"] = now_iso()
    save_json(SHIFT_CHANGE_REQUESTS_FILE, payload)
    return payload


def active_shift_change_requests():
    requests_payload = load_shift_change_requests_payload()
    requests = [row for row in requests_payload.get("requests", []) if isinstance(row, dict)]
    return [row for row in requests if str(row.get("status") or "").strip().lower() not in {"cancelled", "declined", "expired", "applied"}]


def save_live_schedule(schedule):
    save_json(SCHEDULE_FILE, schedule)
    save_json(PUBLIC_SCHEDULE_FILE, schedule)


def load_live_schedule_shifts():
    schedule = load_json(SCHEDULE_FILE, {})
    shifts = schedule.get("shifts") if isinstance(schedule, dict) else None
    if isinstance(shifts, list) and shifts:
        return shifts
    return load_shifts()


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


def schedule_json_response():
    if os.path.exists(SCHEDULE_FILE) and os.path.getsize(SCHEDULE_FILE) > 0:
        return fast_json_file_response(SCHEDULE_FILE)
    return fast_json_file_response(PUBLIC_SCHEDULE_FILE)


def load_base_schedule_payload():
    schedule = load_json(SCHEDULE_FILE, {})
    if isinstance(schedule, dict) and isinstance(schedule.get("shifts"), list) and schedule["shifts"]:
        return schedule
    public_schedule = load_json(PUBLIC_SCHEDULE_FILE, {})
    if isinstance(public_schedule, dict):
        return public_schedule
    return {}


def load_schedule_payload():
    return schedule_with_june_calendar_mirror(load_base_schedule_payload())


def schedule_file_summary(path):
    exists = os.path.exists(path)
    payload = load_json(path, {}) if exists else {}
    shifts = payload.get("shifts") if isinstance(payload, dict) else None
    shifts = shifts if isinstance(shifts, list) else []
    dates = sorted({str(shift.get("date")) for shift in shifts if isinstance(shift, dict) and shift.get("date")})
    summary = {
        "exists": exists,
        "shift_count": len(shifts),
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "modified_at": None,
    }
    if exists:
        try:
            summary["modified_at"] = datetime.fromtimestamp(os.path.getmtime(path), UTC).isoformat().replace("+00:00", "Z")
        except OSError:
            summary["modified_at"] = None
    return summary, shifts


def schedule_shift_key(shift):
    if not isinstance(shift, dict):
        return None
    shift_id = shift.get("shift_id") or shift.get("id")
    if shift_id:
        return str(shift_id)
    date_value = shift.get("date")
    period_value = shift.get("period") or shift.get("label")
    unit_value = shift.get("unit") or shift.get("unit_id") or ""
    if date_value and period_value:
        return f"{date_value}|{period_value}|{unit_value}"
    return None


def schedule_assignment_signature(shift):
    seats = shift.get("seats") if isinstance(shift, dict) else None
    if not isinstance(seats, list):
        return []
    signature = []
    for index, seat in enumerate(seats):
        if not isinstance(seat, dict):
            continue
        role = str(seat.get("role") or seat.get("position") or f"seat_{index}")
        signature.append({
            "role": role,
            "assigned": None if seat.get("assigned") is None else str(seat.get("assigned")),
            "assigned_name": seat.get("assigned_name"),
            "assignment_status": seat.get("assignment_status"),
            "cert": seat.get("cert"),
        })
    return sorted(signature, key=lambda item: item["role"])


def shift_period_value(shift):
    return normalize_shift_label(shift.get("label") or shift.get("period") or shift.get("shift"))


def seat_role_value(seat):
    return str(seat.get("role") or seat.get("seat_role") or seat.get("seat_type") or seat.get("display_role") or "").strip().upper()


def seat_key_for_request(shift, seat, index):
    explicit = str(seat.get("seat_id") or seat.get("seat_key") or "").strip()
    if explicit:
        return explicit
    return f"{str(shift.get('date') or shift.get('shift_date') or '')[:10]}:{shift_period_value(shift)}:{seat_role_value(seat) or 'SEAT'}:{index}"


def assigned_member_id_for_seat(seat):
    return str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip()


def find_assigned_shift_seat(schedule, member_id, date_iso, period, seat_role=None, seat_id=None):
    member_id = str(member_id or "").strip()
    date_iso = str(date_iso or "")[:10]
    period = normalize_shift_label(period)
    seat_role = str(seat_role or "").strip().upper()
    seat_id = str(seat_id or "").strip()
    if not member_id or not date_iso or not period:
        return None, None, None
    for shift in schedule.get("shifts", []) if isinstance(schedule, dict) else []:
        if str(shift.get("date") or shift.get("shift_date") or "")[:10] != date_iso:
            continue
        if shift_period_value(shift) != period:
            continue
        seats = shift.get("seats") if isinstance(shift.get("seats"), list) else []
        for index, seat in enumerate(seats):
            key = seat_key_for_request(shift, seat, index)
            if seat_id and key != seat_id and str(seat.get("seat_id") or "").strip() != seat_id:
                continue
            if seat_role and seat_role_value(seat) != seat_role:
                continue
            if assigned_member_id_for_seat(seat) == member_id:
                return shift, seat, index
    return None, None, None


def schedule_display_path(path):
    try:
        return os.path.relpath(path, BASE_DIR).replace("\\", "/")
    except ValueError:
        return os.path.abspath(path).replace("\\", "/")


def compare_schedule_files(active_path=SCHEDULE_FILE, mirror_path=PUBLIC_SCHEDULE_FILE):
    active_summary, active_shifts = schedule_file_summary(active_path)
    mirror_summary, mirror_shifts = schedule_file_summary(mirror_path)
    active_by_key = {key: shift for shift in active_shifts if (key := schedule_shift_key(shift))}
    mirror_by_key = {key: shift for shift in mirror_shifts if (key := schedule_shift_key(shift))}

    active_keys = set(active_by_key)
    mirror_keys = set(mirror_by_key)
    missing_from_mirror = sorted(active_keys - mirror_keys)
    missing_from_active = sorted(mirror_keys - active_keys)
    sample_mismatches = []

    for key in missing_from_mirror[:10]:
        sample_mismatches.append({"key": key, "type": "missing_from_mirror"})
    for key in missing_from_active[: max(0, 10 - len(sample_mismatches))]:
        sample_mismatches.append({"key": key, "type": "missing_from_active"})

    assignment_mismatch_count = 0
    for key in sorted(active_keys & mirror_keys):
        active_assignment = schedule_assignment_signature(active_by_key[key])
        mirror_assignment = schedule_assignment_signature(mirror_by_key[key])
        if active_assignment != mirror_assignment:
            assignment_mismatch_count += 1
            if len(sample_mismatches) < 10:
                sample_mismatches.append({
                    "key": key,
                    "type": "assignment_mismatch",
                    "active": active_assignment,
                    "mirror": mirror_assignment,
                })

    key_mismatch_count = len(missing_from_mirror) + len(missing_from_active)
    if not active_summary["exists"] or not mirror_summary["exists"]:
        status = "error"
    elif key_mismatch_count or assignment_mismatch_count:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "active_file": schedule_display_path(active_path),
        "mirror_file": schedule_display_path(mirror_path),
        "active": active_summary,
        "mirror": mirror_summary,
        "key_mismatches": key_mismatch_count,
        "missing_from_mirror": len(missing_from_mirror),
        "missing_from_active": len(missing_from_active),
        "assignment_mismatches": assignment_mismatch_count,
        "sample_mismatches": sample_mismatches,
        "generated_at": now_iso(),
    }


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
    beta_auth = beta_auth_from_request()
    if beta_auth:
        return beta_auth
    if demo_supervisor_bypass_enabled():
        return {"authenticated": True, "role": "supervisor", "member_id": None}
    role = session.get("auth_role")
    if role in {"supervisor", "admin"}:
        return {"authenticated": True, "role": role, "member_id": None, "email": str(session.get("auth_email") or "").strip().lower() or None}
    if role == "member":
        auth_email = str(session.get("auth_email") or "").strip().lower()
        if auth_email:
            # Beta Google-login bridge: the session email is trusted only after a
            # separate login layer creates the Flask session. TODO: verify Google
            # ID tokens server-side before creating this session in production.
            member = member_record_by_email(auth_email)
            if member is None:
                return {"authenticated": True, "role": "member", "member_id": None, "email": auth_email}
            if member_has_supervisor_access(member):
                return {
                    "authenticated": True,
                    "role": "supervisor",
                    "member_id": str(member.get("member_id", member.get("id")) or "").strip() or None,
                    "email": auth_email,
                }
            return {
                "authenticated": True,
                "role": "member",
                "member_id": str(member.get("member_id", member.get("id")) or "").strip() or None,
                "email": auth_email,
            }
        return {
            "authenticated": True,
            "role": "member",
            "member_id": str(session.get("member_id") or "").strip() or None,
            "email": None,
        }
    return {"authenticated": False, "role": None, "member_id": None, "email": None}


def auth_json_error(message, status_code=401):
    return jsonify({"error": message}), status_code


def quick_test_mode_enabled():
    return SC_QUICK_TEST_MODE


def demo_supervisor_bypass_enabled():
    return quick_test_mode_enabled() and SC_DEMO_SUPERVISOR_BYPASS


def current_public_base_url():
    if SC_PUBLIC_BASE_URL:
        return SC_PUBLIC_BASE_URL
    forwarded_host = str(request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or "").split(",", 1)[0].strip()
    forwarded_proto = str(request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    if forwarded_host:
        if forwarded_proto in {"http", "https"}:
            return f"{forwarded_proto}://{forwarded_host}".strip().rstrip("/")
        host_name = forwarded_host.split(":", 1)[0].strip().lower()
        if host_name not in {"localhost", "127.0.0.1", "::1"} and "." in host_name:
            return f"https://{forwarded_host}".strip().rstrip("/")
    return str(request.host_url or "").strip().rstrip("/")


def allowed_request_origin():
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    if not origin:
        return None
    host_origin = str(request.host_url or "").strip().rstrip("/")
    if origin == host_origin or origin in SC_ALLOWED_ORIGINS:
        return origin
    try:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        host = str(parsed.hostname or "").lower()
        if parsed.scheme == "https" and any(host.endswith(suffix.lower()) for suffix in SC_ALLOWED_ORIGIN_SUFFIXES):
            return origin
    except Exception:
        return None
    return None


def quick_test_supervisor_allowed():
    if not quick_test_mode_enabled() or not request.path.startswith("/api/"):
        return False
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    return not origin or allowed_request_origin() is not None


def local_testing_login_allowed():
    if quick_test_mode_enabled():
        return True
    host = str(request.host or "").split(":", 1)[0].strip().lower()
    remote = str(request.remote_addr or "").strip()
    return host in {"127.0.0.1", "localhost", "::1"} or remote in {"127.0.0.1", "::1"}


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
            if role_name == "supervisor" and quick_test_supervisor_allowed():
                return func(*args, **kwargs)
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


def member_has_supervisor_access(member):
    if not isinstance(member, dict):
        return False
    access = member.get("access") if isinstance(member.get("access"), dict) else {}
    auth = member.get("auth") if isinstance(member.get("auth"), dict) else {}
    roles = member.get("roles") if isinstance(member.get("roles"), list) else []
    role_values = {str(value or "").strip().lower() for value in roles}
    role_values.add(str(member.get("role") or "").strip().lower())
    role_values.add(str(auth.get("role") or "").strip().lower())
    role_values.update(str(value or "").strip().lower() for value in auth.get("roles", []) if isinstance(auth.get("roles"), list))
    return (
        access.get("supervisor") is True
        or access.get("admin") is True
        or auth.get("supervisor_access") is True
        or auth.get("admin_access") is True
        or bool(role_values & {"supervisor", "admin"})
    )


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


def member_record_by_email(email):
    email = str(email or "").strip().lower()
    if not email:
        return None
    return next(
        (
            member
            for member in load_members()
            if member.get("active") is not False
            and email in {
                str(member.get("email") or "").strip().lower(),
                str(member.get("auth_email") or "").strip().lower(),
                str(member.get("google_email") or "").strip().lower(),
                str((member.get("auth") or {}).get("email") or "").strip().lower() if isinstance(member.get("auth"), dict) else "",
                str((member.get("auth") or {}).get("google_email") or "").strip().lower() if isinstance(member.get("auth"), dict) else "",
            }
        ),
        None,
    )


def start_member_session(member_id):
    session.clear()
    session["auth_role"] = "member"
    session["member_id"] = str(member_id or "").strip()


def start_supervisor_session():
    session.clear()
    session["auth_role"] = "supervisor"


def beta_session_token_secret():
    return str(app.secret_key or "shiftcommander-local-dev-secret-key").encode("utf-8")


def base64url_encode(raw):
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def base64url_decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def member_auth_email(member):
    if not isinstance(member, dict):
        return None
    auth = member.get("auth") if isinstance(member.get("auth"), dict) else {}
    for key in ("email", "auth_email", "google_email"):
        value = str(member.get(key) or "").strip().lower()
        if value:
            return value
    for key in ("email", "google_email"):
        value = str(auth.get(key) or "").strip().lower()
        if value:
            return value
    return None


def beta_role_for_member(member):
    if member_has_supervisor_access(member):
        return "supervisor"
    return "member"


def create_beta_session_token(member_id, lifetime_seconds=12 * 60 * 60):
    member = member_record_by_id(member_id)
    if not member:
        return None
    now = int(time.time())
    payload = {
        "typ": "shiftcommander-beta-session",
        "iat": now,
        "exp": now + int(lifetime_seconds),
        "nonce": secrets.token_hex(8),
        "member_id": str(member.get("member_id", member.get("id")) or "").strip(),
        "email": member_auth_email(member),
        "name": member.get("name") or f"Member {member_id}",
        "role": beta_role_for_member(member),
    }
    payload_b64 = base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(beta_session_token_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload_b64}.{base64url_encode(sig)}"


def verify_beta_session_token(token):
    token = str(token or "").strip()
    if "." not in token:
        return None
    payload_b64, sig_b64 = token.rsplit(".", 1)
    expected = hmac.new(beta_session_token_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    try:
        actual = base64url_decode(sig_b64)
    except Exception:
        return None
    if not hmac.compare_digest(expected, actual):
        return None
    try:
        payload = json.loads(base64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if payload.get("typ") != "shiftcommander-beta-session":
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    member = member_record_by_id(payload.get("member_id"))
    if not member:
        return None
    email = str(payload.get("email") or member_auth_email(member) or "").strip().lower()
    return {
        "authenticated": True,
        "role": beta_role_for_member(member),
        "member_id": str(member.get("member_id", member.get("id")) or "").strip(),
        "email": email,
        "member_name": member.get("name") or payload.get("name") or f"Member {payload.get('member_id')}",
        "member": member,
        "auth_mode": "beta_login_bridge",
        "beta_auth_bridge": True,
        "expires_at": datetime.fromtimestamp(int(payload.get("exp")), UTC).isoformat().replace("+00:00", "Z"),
        "build_code": BUILD_CODE,
    }


def beta_auth_from_request():
    token = str(request.headers.get("X-ShiftCommander-Beta-Session") or "").strip()
    if not token:
        auth_header = str(request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    payload = verify_beta_session_token(token)
    if not payload:
        return None
    return {
        "authenticated": True,
        "role": payload.get("role") or "member",
        "member_id": str(payload.get("member_id") or "").strip() or None,
        "email": str(payload.get("email") or "").strip().lower() or None,
        "beta_auth_bridge": True,
    }


def append_beta_token_to_redirect(redirect_to, token):
    redirect_to = str(redirect_to or "/member").strip() or "/member"
    if not token:
        return redirect_to
    parsed = urlparse(redirect_to)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "sc_beta_session"]
    query.append(("sc_beta_session", token))
    return urlunparse(parsed._replace(query=urlencode(query)))


def member_login_success_payload(member_id, redirect_to="/member"):
    member = member_record_by_id(member_id)
    token = create_beta_session_token(member_id)
    return {
        "status": "ok",
        "authenticated": True,
        "role": beta_role_for_member(member),
        "member_id": str(member_id or "").strip(),
        "member_name": (member or {}).get("name") or f"Member {member_id}",
        "email": member_auth_email(member),
        "redirect": append_beta_token_to_redirect(redirect_to, token),
        # Existing Flask session cookie remains authoritative on same-origin pages.
        # The signed token bridges the standalone beta frontend without trusting
        # cross-site cookies or exposing open impersonation.
        "session_token": token,
        "beta_auth_bridge": True,
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


def resolve_member_read_target(payload=None):
    """Resolve the member whose portal data may be read.

    Supervisors can view a selected member in beta supervisor mode. Regular
    members can only read their own member portal data.
    """
    if quick_test_mode_enabled():
        member_id = requested_member_id(payload) or default_quick_test_member_id()
        member = member_record_by_id(member_id)
        if member is None:
            return None, None, auth_json_error("Quick Test member record not found", 404)
        return str(member_id), member, None

    auth = current_auth()
    if not auth.get("authenticated"):
        return None, None, auth_json_error("Authentication required", 401)

    requested_id = requested_member_id(payload)
    if auth.get("role") in {"supervisor", "admin"}:
        member_id = requested_id or str(auth.get("member_id") or "").strip()
        if not member_id:
            return None, None, auth_json_error("member_id is required for supervisor member view", 400)
        member = member_record_by_id(member_id)
        if member is None:
            return None, None, auth_json_error("Member record not found", 404)
        return str(member_id), member, None

    if auth.get("role") != "member":
        return None, None, auth_json_error("Member access required", 403)

    auth_member_id = str(auth.get("member_id") or "").strip()
    if not auth_member_id:
        return None, None, auth_json_error("Authenticated member record not found", 401)
    if requested_id and str(requested_id) != auth_member_id:
        return None, None, auth_json_error("Members may only read their own portal data", 403)

    member = member_record_by_id(auth_member_id)
    if member is None or member.get("active") is False:
        return None, None, auth_json_error("Authenticated member record not found", 401)
    return auth_member_id, member, None


def resolve_member_write_target(payload=None):
    """Resolve a member write target from backend auth, not frontend selection.

    Beta limitation: Google identity is currently represented by the Flask
    session's auth_email after login. The backend maps that email to an active
    ShiftCommander member before writes. TODO: add production Google ID-token
    verification/session creation before claiming production-grade security.
    """
    auth = current_auth()
    if not auth.get("authenticated"):
        return None, None, auth_json_error("Authentication required", 401)

    requested_id = requested_member_id(payload)
    if auth.get("role") in {"supervisor", "admin"}:
        member_id = requested_id or str(auth.get("member_id") or "").strip()
        member = member_record_by_id(member_id)
        if member is None:
            return None, None, auth_json_error("Member record not found", 404)
        return str(member_id), member, None

    if auth.get("role") != "member":
        return None, None, auth_json_error("Member access required", 403)

    auth_member_id = str(auth.get("member_id") or "").strip()
    if not auth_member_id:
        return None, None, auth_json_error("Authenticated member record not found", 401)
    if requested_id and str(requested_id) != auth_member_id:
        return None, None, auth_json_error("Members may only write their own availability", 403)

    member = member_record_by_id(auth_member_id)
    if member is None or member.get("active") is False:
        return None, None, auth_json_error("Authenticated member record not found", 401)
    return auth_member_id, member, None


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


MEDICAL_CERT_RANKS = {
    "NCLD": 0,
    "EMR": 1,
    "EMT": 2,
    "AEMT": 3,
    "PARAMEDIC": 4,
}

MEDICAL_CERT_LABELS = {
    "NCLD": "Non-Certified, Licensed Driver (NCLD)",
    "EMR": "EMR",
    "EMT": "EMT",
    "AEMT": "AEMT",
    "PARAMEDIC": "Paramedic",
}


def canonical_medical_cert(value):
    raw = str(value or "").strip().upper()
    aliases = {
        "NON-CERTIFIED LICENSED DRIVER": "NCLD",
        "NON CERTIFIED LICENSED DRIVER": "NCLD",
        "NON_CERTIFIED_LICENSED_DRIVER": "NCLD",
        "NCLD": "NCLD",
        "EMR": "EMR",
        "EMT": "EMT",
        "AEMT": "AEMT",
        "ALS": "AEMT",
        "PARAMEDIC": "PARAMEDIC",
        "MEDIC": "PARAMEDIC",
    }
    return aliases.get(raw, raw)


def normalize_member_rotation(member):
    if not isinstance(member, dict):
        return member
    medical_cert = canonical_medical_cert(member.get("medical_cert") or member.get("ops_cert") or member.get("cert") or member.get("raw_cert"))
    if medical_cert:
        member["medical_cert"] = medical_cert
        member["medical_cert_rank"] = MEDICAL_CERT_RANKS.get(medical_cert)
        member["medical_cert_label"] = MEDICAL_CERT_LABELS.get(medical_cert, medical_cert)
    if medical_cert == "NCLD" or member.get("ncld_status") is True:
        member["medical_cert"] = "NCLD"
        member["medical_cert_rank"] = MEDICAL_CERT_RANKS["NCLD"]
        member["medical_cert_label"] = MEDICAL_CERT_LABELS["NCLD"]
        member["ncld_status"] = True
        member.setdefault("ncld_interest_level", "unknown")
        member.setdefault("ncld_notes", "")
        member.setdefault("last_interest_update", None)

    rotation = member.get("rotation")
    if not isinstance(rotation, dict):
        rotation = infer_rotation_from_legacy(member) or {}
    rotation_scope = str(rotation.get("scope") or member.get("rotation_scope") or "").strip()
    pair = str(rotation.get("pair") or "").strip().upper()
    role = str(rotation.get("role") or "").strip().upper()
    is_aemt_rotation = rotation_scope == "aemt_als_rotation"

    if role and pair not in ("AC", "BD"):
        pair = "AC" if role in ("A", "C") else "BD" if role in ("B", "D") else ""

    if pair not in ("AC", "BD") or role not in ("A", "B", "C", "D"):
        member["rotation"] = None
    else:
        member["rotation"] = {"pair": pair, "role": role}
        if is_aemt_rotation:
            member["rotation"]["scope"] = "aemt_als_rotation"
            member["rotation"]["label"] = "AEMT/ALS rotation"

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
        if is_aemt_rotation:
            member["rotation_scope"] = "aemt_als_rotation"
            member["rotation_label"] = "AEMT/ALS rotation"
            member["shift_system"] = "aemt_abcd_rotation"
            member["shift_system_assignment"] = "aemt_abcd_rotation"
            shift_pref["rotation_role"] = "aemt_als_rotation"
            shift_pref["rotation_scope"] = "aemt_als_rotation"
            shift_pref["relief_partner_track"] = None
            shift_pref["staffing_system"] = "aemt_abcd_rotation"
            shift_pref["style"] = "aemt_als_rotation"
            shift_pref["shift_length_hours"] = 24
        else:
            shift_pref["rotation_role"] = "day" if role in ("A", "B") else "night"
            shift_pref["relief_partner_track"] = {"A": "C", "B": "D", "C": "A", "D": "B"}[role]
            shift_pref.setdefault("shift_length_hours", 12)
            if not shift_pref.get("style") or shift_pref.get("style") == "availability_based":
                shift_pref["style"] = "rotation_223_relief"
        shift_pref.setdefault("rotation_template_id", "rot_223_12h_relief")
    else:
        shift_pref.setdefault("rotation_track", None)
        shift_pref.setdefault("rotation_role", None)
        shift_pref.setdefault("relief_partner_track", None)

    member.setdefault("shift_system", member.get("shift_system_assignment") or shift_pref.get("staffing_system") or None)
    member.setdefault("shift_system_assignment", member.get("shift_system") or shift_pref.get("staffing_system") or None)
    member.setdefault("rotation_slot", role if role in ("A", "B", "C", "D") else None)
    member.setdefault("rotation_authorized", bool((member.get("rotation_authorization") or {}).get("status") == "approved") if isinstance(member.get("rotation_authorization"), dict) else False)
    member.setdefault("expected_rotation_ot_allowed", False)
    member.setdefault("zipper_participation", False)
    member.setdefault("zipper_group", None)
    emp = member.setdefault("employment", {})
    if isinstance(emp, dict):
        member.setdefault("max_hours_allowed", emp.get("hard_weekly_hour_cap"))
        member.setdefault("preferred_hours", emp.get("preferred_weekly_hour_cap"))
        member.setdefault("hourly_or_salaried", emp.get("pay_type") or "hourly")

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


def normalize_calendar_markers_payload(payload):
    if isinstance(payload, list):
        payload = {"markers": payload}
    elif not isinstance(payload, dict):
        payload = {"markers": []}
    markers = payload.get("markers", [])
    if not isinstance(markers, list):
        markers = []
    cleaned = []
    for index, marker in enumerate(markers):
        if not isinstance(marker, dict):
            continue
        date_value = str(marker.get("date") or "").strip()[:10]
        title = str(marker.get("short_title") or marker.get("title") or "").strip()
        if not date_value or not title:
            continue
        marker_id = str(marker.get("id") or f"{date_value}-{title.lower().replace(' ', '-')}-{index}").strip()
        cleaned.append({
            "id": marker_id,
            "date": date_value,
            "short_title": title,
            "hover_text": str(marker.get("hover_text") or marker.get("description") or title).strip(),
            "icon": str(marker.get("icon") or "star_of_life").strip(),
            "custom_icon_url": marker.get("custom_icon_url") or None,
            "custom_animated_icon_url": marker.get("custom_animated_icon_url") or None,
            "active": marker.get("active", True) is not False,
            "show_wallboard": marker.get("show_wallboard", True) is not False,
            "show_supervisor": marker.get("show_supervisor", True) is not False,
            "priority": int(marker.get("priority") or 0),
            "flag_status": marker.get("flag_status") if isinstance(marker.get("flag_status"), dict) else {},
        })
    payload["markers"] = cleaned
    payload.setdefault("flag_status_sources", {
        "manual_override_enabled": True,
        "automatic_check_enabled": False,
        "state": "NC",
        "scope": "state_and_federal",
        "current_status": "full_staff",
        "current_label": "FULL STAFF",
        "source_level": "manual",
        "source_url": "https://ncadmin.nc.gov/news/flag-alerts",
    })
    return payload


def load_calendar_markers_payload():
    return normalize_calendar_markers_payload(load_json(CALENDAR_MARKERS_FILE, {"markers": []}))


def save_calendar_markers_payload(payload):
    payload = normalize_calendar_markers_payload(payload)
    save_json(CALENDAR_MARKERS_FILE, payload)
    os.makedirs(os.path.dirname(PUBLIC_CALENDAR_MARKERS_FILE), exist_ok=True)
    save_json(PUBLIC_CALENDAR_MARKERS_FILE, payload)
    return payload
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
    if not isinstance(data, dict):
        data = {}
    data["career_fire_driver"] = normalize_career_fire_driver_rules(data.get("career_fire_driver", {}))
    data["member_accommodations"] = normalize_member_accommodations(data.get("member_accommodations", {}))
    data["display_horizon"] = normalize_display_horizon(data.get("display_horizon", {}))
    return data


def save_settings_payload(settings):
    save_json(SETTINGS_FILE, settings)
    os.makedirs(os.path.dirname(PUBLIC_SETTINGS_FILE), exist_ok=True)
    save_json(PUBLIC_SETTINGS_FILE, settings)


def normalize_career_fire_driver_rules(raw):
    rules = deepcopy(DEFAULT_CAREER_FIRE_DRIVER_RULES)
    if isinstance(raw, dict):
        rules.update(raw)
    valid_days = {"MO", "TU", "WE", "TH", "FR"}
    days = rules.get("days", [])
    if not isinstance(days, list):
        days = DEFAULT_CAREER_FIRE_DRIVER_RULES["days"]
    rules["days"] = [day for day in [str(item).strip().upper() for item in days] if day in valid_days]
    for key in ["enabled", "show_transition_watch", "visible_on_wallboard"]:
        rules[key] = bool(rules.get(key))
    rules["counts_as_required_coverage"] = False
    rules["creates_holdover_assignment"] = False
    rules["counts_toward_driver_coverage"] = bool(rules.get("counts_toward_driver_coverage", True))
    rules["counts_toward_emt_coverage"] = bool(rules.get("counts_toward_emt_coverage", True))
    rules["counts_as_named_member_assignment"] = False
    for key in ["label", "effective_start", "start_time", "end_time", "normal_shift_start", "transition_watch_label", "transition_watch_style"]:
        rules[key] = str(rules.get(key) or DEFAULT_CAREER_FIRE_DRIVER_RULES[key]).strip()
    return rules


def validate_career_fire_driver_rules(payload):
    if not isinstance(payload, dict):
        return None, "Career Fire Driver settings must be an object"
    valid_days = {"MO", "TU", "WE", "TH", "FR"}
    time_keys = ["start_time", "end_time", "normal_shift_start"]
    days = payload.get("days", [])
    if not isinstance(days, list):
        return None, "days must be a list"
    normalized_days = []
    for item in days:
        day = str(item).strip().upper()
        if day not in valid_days:
            return None, f"Invalid weekday code: {day}"
        if day not in normalized_days:
            normalized_days.append(day)
    for key in time_keys:
        value = str(payload.get(key, DEFAULT_CAREER_FIRE_DRIVER_RULES[key]) or "").strip()
        if not re.match(r"^\d{2}:\d{2}$", value):
            return None, f"{key} must use HH:MM"
        hour, minute = [int(part) for part in value.split(":")]
        if hour > 23 or minute > 59:
            return None, f"{key} must use a valid HH:MM time"
    merged = normalize_career_fire_driver_rules({**DEFAULT_CAREER_FIRE_DRIVER_RULES, **payload, "days": normalized_days})
    merged["counts_as_required_coverage"] = False
    merged["creates_holdover_assignment"] = False
    merged["counts_toward_driver_coverage"] = True
    merged["counts_toward_emt_coverage"] = True
    merged["counts_as_named_member_assignment"] = False
    return merged, None


def normalize_display_horizon(raw):
    horizon = deepcopy(DEFAULT_DISPLAY_HORIZON)
    if isinstance(raw, dict):
        horizon.update(raw)
    horizon["enabled"] = bool(horizon.get("enabled"))
    mode = str(horizon.get("mode") or DEFAULT_DISPLAY_HORIZON["mode"]).strip()
    horizon["mode"] = mode if mode in {"temporary_fixed_until_date", "rolling"} else DEFAULT_DISPLAY_HORIZON["mode"]
    for key in ["temporary_fixed_end_date", "resume_rolling_after_date"]:
        parsed = None
        try:
            parsed = datetime.fromisoformat(str(horizon.get(key) or "")[:10]).date()
        except ValueError:
            parsed = datetime.fromisoformat(DEFAULT_DISPLAY_HORIZON[key]).date()
        horizon[key] = parsed.isoformat()
    for key in ["rolling_weeks_default", "admin_rolling_weeks"]:
        try:
            weeks = int(horizon.get(key) or DEFAULT_DISPLAY_HORIZON[key])
        except (TypeError, ValueError):
            weeks = DEFAULT_DISPLAY_HORIZON[key]
        horizon[key] = max(1, min(52, weeks))
    return horizon


def validate_display_horizon(payload):
    if not isinstance(payload, dict):
        return None, "Display horizon settings must be an object"
    try:
        return normalize_display_horizon(payload), None
    except Exception as exc:
        return None, f"Invalid display horizon settings: {exc}"


def normalize_member_accommodations(raw):
    if not isinstance(raw, dict):
        raw = {}
    defaults = deepcopy(DEFAULT_MEMBER_ACCOMMODATIONS)
    offsets = raw.get("effective_start_offsets", defaults["effective_start_offsets"])
    if not isinstance(offsets, list):
        offsets = defaults["effective_start_offsets"]

    normalized_offsets = []
    for item in offsets:
        if not isinstance(item, dict):
            continue
        merged = {
            "member_id": str(item.get("member_id") or "").strip(),
            "member_name": str(item.get("member_name") or "").strip(),
            "active": bool(item.get("active", True)),
            "normal_shift_start": str(item.get("normal_shift_start") or "06:00").strip(),
            "effective_start": str(item.get("effective_start") or "08:00").strip(),
            "applies_to_labels": item.get("applies_to_labels", ["AM"]),
            "watch_label": str(item.get("watch_label") or "0600-0800 Watch").strip(),
            "visible_on_wallboard": bool(item.get("visible_on_wallboard", True)),
            "counts_as_required_coverage": False,
            "creates_holdover_assignment": False,
        }
        if not isinstance(merged["applies_to_labels"], list):
            merged["applies_to_labels"] = ["AM"]
        merged["applies_to_labels"] = [
            str(label).strip().upper()
            for label in merged["applies_to_labels"]
            if str(label).strip()
        ]
        if merged["member_id"]:
            normalized_offsets.append(merged)

    if not normalized_offsets:
        normalized_offsets = defaults["effective_start_offsets"]
    return {"effective_start_offsets": normalized_offsets}


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


def get_current_timecard_period(today=None):
    if today is None:
        today = iso_today()
    if isinstance(today, str):
        today = date.fromisoformat(today[:10])
    start = today - timedelta(days=(today.weekday() - 3) % 7)
    end = start + timedelta(days=6)
    return build_timecard_period(start, end)


def build_timecard_period(start, end=None):
    if isinstance(start, str):
        start = date.fromisoformat(start[:10])
    if end is None:
        end = start + timedelta(days=6)
    if isinstance(end, str):
        end = date.fromisoformat(end[:10])
    if end < start:
        end = start + timedelta(days=6)
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "label": f"Thursday {start.strftime('%m/%d/%Y')} through Wednesday {end.strftime('%m/%d/%Y')}",
    }


def member_display_name(member):
    if not isinstance(member, dict):
        return "Member"
    name = str(member.get("name") or "").strip()
    if name:
        return name
    return " ".join(str(member.get(key) or "").strip() for key in ("first_name", "last_name")).strip() or str(member.get("member_id", member.get("id", "Member")))


def shift_time_range(shift, seat, settings):
    label = str(shift.get("label") or shift.get("shift") or "").strip().upper()
    definitions = settings.get("shift_definitions", {}) if isinstance(settings, dict) else {}
    definition = definitions.get(label, {}) if isinstance(definitions, dict) and isinstance(definitions.get(label), dict) else {}
    start = shift.get("start_time") or seat.get("start_time") or definition.get("start_time") or definition.get("start")
    end = shift.get("end_time") or seat.get("end_time") or definition.get("end_time") or definition.get("end")
    if not start:
        start = "06:00" if label in {"AM", "DAY"} else "18:00" if label in {"PM", "NIGHT"} else ""
    if not end:
        end = "18:00" if label in {"AM", "DAY"} else "06:00" if label in {"PM", "NIGHT"} else ""
    return str(start or ""), str(end or "")


def timecard_regular_threshold(member):
    for value in (
        member.get("ot_threshold") if isinstance(member, dict) else None,
        member.get("weekly_non_ot_hours") if isinstance(member, dict) else None,
        (member.get("employment", {}) or {}).get("weekly_non_ot_hours") if isinstance(member, dict) and isinstance(member.get("employment"), dict) else None,
    ):
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            pass
    employment = member.get("employment", {}) if isinstance(member, dict) else {}
    employment_status = str((employment.get("status") if isinstance(employment, dict) else member.get("employment_type")) or "").strip().upper()
    return 40.0 if employment_status in {"FT", "FULL_TIME"} else None


def build_member_timecard(member_id, today=None, schedule_payload=None, period_start=None, period_end=None):
    member_id = str(member_id or "").strip()
    member = member_record_by_id(member_id)
    if member is None:
        return None
    period = build_timecard_period(period_start, period_end) if period_start else get_current_timecard_period(today)
    period_start = date.fromisoformat(period["period_start"])
    period_end = date.fromisoformat(period["period_end"])
    schedule = schedule_payload if isinstance(schedule_payload, dict) else load_json(SCHEDULE_FILE, {})
    settings = load_settings()
    rows = []
    for shift in schedule.get("shifts", []) if isinstance(schedule.get("shifts"), list) else []:
        shift_date_raw = str(shift.get("date") or shift.get("shift_date") or "")[:10]
        try:
            shift_day = date.fromisoformat(shift_date_raw)
        except ValueError:
            continue
        if shift_day < period_start or shift_day > period_end:
            continue
        for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
            if str(seat.get("assigned") or "").strip() != member_id:
                continue
            role = str(seat.get("role") or seat.get("seat_type") or seat.get("display_role") or "Seat").strip()
            if not role:
                continue
            try:
                hours = float(seat.get("hours") or shift.get("hours") or 12)
            except (TypeError, ValueError):
                hours = 12.0
            start_time, end_time = shift_time_range(shift, seat, settings)
            rows.append({
                "date": shift_day.isoformat(),
                "day": shift_day.strftime("%A"),
                "shift": str(shift.get("label") or shift.get("shift") or ""),
                "unit": str(shift.get("unit") or ""),
                "start_time": start_time,
                "end_time": end_time,
                "role": role,
                "hours": hours,
                "notes": str(seat.get("assignment_reason") or seat.get("selection_statement") or "").strip(),
            })
    rows.sort(key=lambda row: (row["date"], row["shift"], row["role"]))
    total_hours = round(sum(row["hours"] for row in rows), 2)
    threshold = timecard_regular_threshold(member)
    regular_hours = round(min(total_hours, threshold), 2) if threshold is not None else total_hours
    ot_hours = round(max(0.0, total_hours - threshold), 2) if threshold is not None else 0.0
    return {
        "organization_name": settings.get("organization_name") or settings.get("agency_name") or "ShiftCommander",
        "member": member,
        "member_id": member_id,
        "member_name": member_display_name(member),
        "period": period,
        "generated_at": datetime.now().strftime("%m/%d/%Y %I:%M %p"),
        "rows": rows,
        "summary": {
            "total_hours": total_hours,
            "regular_hours": regular_hours,
            "ot_hours": ot_hours,
            "shifts_worked": len(rows),
            "ot_calculable": threshold is not None,
        },
    }


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
                "medical_cert": member.get("medical_cert"),
                "medical_cert_rank": member.get("medical_cert_rank"),
                "medical_cert_label": member.get("medical_cert_label"),
                "ncld_status": bool(member.get("ncld_status", False)),
                "ncld_interest_level": member.get("ncld_interest_level"),
                "ncld_notes": member.get("ncld_notes"),
                "last_interest_update": member.get("last_interest_update"),
                "birthday": member.get("birthday"),
                "birthday_mmdd": member.get("birthday_mmdd"),
            }
        )
    return roster


def normalized_person_name(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def ical_unescape(value):
    return (
        str(value or "")
        .replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def parse_ical_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).astimezone(LOCAL_TZ)
        if "T" in raw:
            return datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=LOCAL_TZ)
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None


def parse_ical_events(ics_text):
    lines = []
    for raw_line in str(ics_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] += raw_line[1:]
        else:
            lines.append(raw_line)

    events = []
    current = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if isinstance(current, dict):
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        name = key.split(";", 1)[0].upper()
        current.setdefault(name, []).append(ical_unescape(value))
    return events


def calendar_event_start(event):
    values = event.get("DTSTART") if isinstance(event, dict) else None
    return parse_ical_datetime(values[0]) if values else None


def calendar_event_recurrence_start(event):
    values = event.get("RECURRENCE-ID") if isinstance(event, dict) else None
    return parse_ical_datetime(values[0]) if values else None


def june_2026_calendar_occurrences(ics_text):
    events = parse_ical_events(ics_text)
    recurrence_overrides = {
        (str(event.get("UID", [""])[0]), calendar_event_recurrence_start(event).isoformat())
        for event in events
        if calendar_event_recurrence_start(event)
    }
    occurrences = []

    for event in events:
        uid = str(event.get("UID", [""])[0])
        summary = str(event.get("SUMMARY", [""])[0]).strip()
        start = calendar_event_start(event)
        if not start:
            continue

        if any(str(rule).upper().startswith("FREQ=DAILY") for rule in event.get("RRULE", [])):
            cursor = max(date(2026, 6, 1), start.date())
            while cursor <= date(2026, 6, 30):
                occurrence_start = datetime.combine(cursor, start.timetz()).astimezone(LOCAL_TZ)
                if (uid, occurrence_start.isoformat()) not in recurrence_overrides:
                    occurrences.append({"uid": uid, "summary": summary, "start": occurrence_start})
                cursor += timedelta(days=1)
            continue

        if start.year == 2026 and start.month == 6:
            occurrences.append({"uid": uid, "summary": summary, "start": start})

    return occurrences


def clean_calendar_summary(summary):
    text = re.sub(r"\s+", " ", str(summary or "").replace("_", " ").strip())
    text = re.sub(r"^(AEMT|BASIC|EMT|ALS|DAY|NIGHT|A|B|C|D)\s*[-:]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(DAY|NIGHT)$", "", text, flags=re.IGNORECASE)
    return text.strip()


def member_aliases(member):
    name = str(member.get("name") or member.get("member_name") or "").strip()
    aliases = {normalized_person_name(name)}
    parts = [part for part in normalized_person_name(name).split() if part]
    if parts:
        aliases.add(parts[0])
    if parts and parts[0] == "sophia":
        aliases.add("sophie")
    return {alias for alias in aliases if alias}


def resolve_calendar_member(summary, members):
    cleaned = normalized_person_name(clean_calendar_summary(summary))
    if not cleaned or cleaned in {"open", "aemt", "basic", "emt", "als"} or "company" in cleaned:
        return None
    for member in members:
        if cleaned in member_aliases(member):
            return member
    for member in members:
        aliases = member_aliases(member)
        if any(alias and re.search(rf"\b{re.escape(alias)}\b", cleaned) for alias in aliases):
            return member
    return None


def calendar_role_for_occurrence(occurrence, member=None):
    summary = normalized_person_name(occurrence.get("summary"))
    uid = str(occurrence.get("uid") or "")
    if uid.startswith("4copgv8r") or uid.startswith("0d75lqc3") or "aemt" in summary or "als" in summary:
        return "ATTENDANT"
    if uid.startswith("1ij3eg78") or uid.startswith("61b1ftda") or "basic" in summary or "emt" in summary:
        return "DRIVER"
    cert = str((member or {}).get("ops_cert") or (member or {}).get("cert") or "").strip().upper()
    return "ATTENDANT" if cert in {"ALS", "AEMT", "PARAMEDIC"} else "DRIVER"


def calendar_period_for_start(start):
    return "AM" if start.hour < 12 else "PM"


def calendar_seat_from_occurrence(occurrence, members):
    summary = clean_calendar_summary(occurrence.get("summary"))
    if "company" in normalized_person_name(summary):
        return None
    member = resolve_calendar_member(summary, members)
    role = calendar_role_for_occurrence(occurrence, member)
    is_open = normalized_person_name(summary) == "open"
    assigned_name = "OPEN" if is_open else (member.get("name") if member else summary)
    seat = {
        "role": role,
        "hours": 12.0,
        "assigned": None if not member else str(member.get("member_id", member.get("id"))),
        "assigned_name": f"OPEN {role}" if is_open else assigned_name,
        "assignment_status": "OPEN" if is_open else "ASSIGNED",
        "display_on_board": True,
        "source": "google_calendar_mirror",
        "logic_mode": "mirror_only",
        "calendar_uid": occurrence.get("uid"),
        "calendar_summary": occurrence.get("summary"),
        "calendar_start": occurrence.get("start").isoformat() if occurrence.get("start") else None,
    }
    if is_open:
        seat["display_open_alert"] = True
    return seat


def choose_calendar_core_seats(seats):
    chosen = []
    for role in ("ATTENDANT", "DRIVER"):
        role_seats = sorted(
            [seat for seat in seats if seat.get("role") == role],
            key=lambda seat: str(seat.get("calendar_start") or ""),
        )
        assigned = [seat for seat in role_seats if seat.get("assigned") or not str(seat.get("assigned_name") or "").upper().startswith("OPEN")]
        open_seats = [seat for seat in role_seats if str(seat.get("assigned_name") or "").upper().startswith("OPEN")]
        if assigned:
            chosen.append(assigned[0])
        elif open_seats:
            chosen.append(open_seats[0])
    return chosen


def build_june_calendar_mirror_payload(ics_text, members_payload=None):
    members = members_payload if isinstance(members_payload, list) else load_members()
    grouped = {}
    for occurrence in june_2026_calendar_occurrences(ics_text):
        start = occurrence["start"]
        date_iso = start.date().isoformat()
        period = calendar_period_for_start(start)
        seat = calendar_seat_from_occurrence(occurrence, members)
        if seat:
            grouped.setdefault((date_iso, period), []).append(seat)

    shifts = []
    for (date_iso, period), seats in sorted(grouped.items()):
        core_seats = choose_calendar_core_seats(seats)
        for index, seat in enumerate(core_seats):
            seat["seat_id"] = f"{date_iso}:{period}:{seat['role']}:{index}"
        shifts.append({
            "date": date_iso,
            "label": period,
            "unit": None,
            "source": "google_calendar_mirror",
            "logic_mode": "mirror_only",
            "calendar_id": ADR_EMPLOYEE_SCHEDULE_CALENDAR_ID,
            "calendar_name": "ADR Employee Schedule",
            "seats": core_seats,
            "calendar_events": [
                {
                    "summary": seat.get("calendar_summary"),
                    "uid": seat.get("calendar_uid"),
                    "role": seat.get("role"),
                    "assigned": seat.get("assigned"),
                    "assigned_name": seat.get("assigned_name"),
                }
                for seat in seats
            ],
        })
    return {
        "build": {
            "source": "google_calendar_mirror",
            "calendar_id": ADR_EMPLOYEE_SCHEDULE_CALENDAR_ID,
            "calendar_name": "ADR Employee Schedule",
            "generated_at": now_iso(),
            "month": "2026-06",
            "shift_count": len(shifts),
        },
        "shifts": shifts,
    }


def load_google_calendar_june_mirror_payload():
    cached = load_json(GOOGLE_CALENDAR_JUNE_MIRROR_FILE, {})
    cached_build = cached.get("build") if isinstance(cached, dict) else {}
    try:
        generated_at = datetime.fromisoformat(str(cached_build.get("generated_at") or "").replace("Z", "+00:00"))
    except ValueError:
        generated_at = None
    if (
        isinstance(cached, dict)
        and isinstance(cached.get("shifts"), list)
        and cached["shifts"]
        and generated_at
        and (datetime.now(UTC) - generated_at.astimezone(UTC)).total_seconds() < GOOGLE_CALENDAR_MIRROR_CACHE_SECONDS
    ):
        return cached

    try:
        req = urllib.request.Request(ADR_EMPLOYEE_SCHEDULE_ICAL_URL, headers={"User-Agent": "ShiftCommander/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            ics_text = response.read().decode("utf-8", "replace")
        payload = build_june_calendar_mirror_payload(ics_text)
        payload["build"]["feed_status"] = "ok"
        save_json(GOOGLE_CALENDAR_JUNE_MIRROR_FILE, payload)
        return payload
    except Exception as exc:
        if isinstance(cached, dict) and isinstance(cached.get("shifts"), list) and cached["shifts"]:
            cached = deepcopy(cached)
            cached.setdefault("build", {})["feed_status"] = f"cached_after_error:{exc.__class__.__name__}"
            return cached
        return {
            "build": {
                "source": "google_calendar_mirror",
                "calendar_id": ADR_EMPLOYEE_SCHEDULE_CALENDAR_ID,
                "feed_status": f"unavailable:{exc.__class__.__name__}",
                "fallback": "base_schedule_payload",
            },
            "shifts": [],
        }


def schedule_with_june_calendar_mirror(schedule_payload):
    base = deepcopy(schedule_payload) if isinstance(schedule_payload, dict) else {}
    calendar_payload = load_google_calendar_june_mirror_payload()
    calendar_shifts = calendar_payload.get("shifts") if isinstance(calendar_payload, dict) else []
    if not isinstance(calendar_shifts, list) or not calendar_shifts:
        base.setdefault("build", {})["june_calendar_mirror"] = calendar_payload.get("build", {}) if isinstance(calendar_payload, dict) else {}
        return base

    base_shifts = base.get("shifts") if isinstance(base.get("shifts"), list) else []
    merged_shifts = [
        shift for shift in base_shifts
        if isinstance(shift, dict) and not is_june_2026_date(shift.get("date") or shift.get("shift_date"))
    ]
    merged_shifts.extend(calendar_shifts)
    base["shifts"] = merged_shifts
    base.setdefault("build", {})["june_calendar_mirror"] = calendar_payload.get("build", {})
    return base


def is_june_2026_date(date_iso):
    try:
        day = date.fromisoformat(str(date_iso or "")[:10])
    except ValueError:
        return False
    return day.year == 2026 and day.month == 6


def member_is_assigned_to_shift(member_id, member, shift):
    if not isinstance(shift, dict):
        return False
    member_id = str(member_id or "").strip()
    member_name = normalized_person_name(member.get("name") if isinstance(member, dict) else "")
    for seat in shift.get("seats", []) if isinstance(shift.get("seats"), list) else []:
        assigned_id = str(seat.get("assigned") or seat.get("assigned_member_id") or seat.get("member_id") or "").strip()
        assigned_name = normalized_person_name(seat.get("assigned_name") or seat.get("member_name") or seat.get("name"))
        if assigned_id and assigned_id == member_id:
            return True
        if member_name and assigned_name and assigned_name == member_name:
            return True
    return False


def schedule_shift_lookup(schedule_payload=None):
    schedule = schedule_payload if isinstance(schedule_payload, dict) else load_schedule_payload()
    lookup = {}
    for shift in schedule.get("shifts", []) if isinstance(schedule.get("shifts"), list) else []:
        if not isinstance(shift, dict):
            continue
        date_iso = str(shift.get("date") or shift.get("shift_date") or "")[:10]
        period = str(shift.get("label") or shift.get("period") or "").strip().upper()
        if date_iso and period:
            lookup[(date_iso, period)] = shift
    return lookup


def june_seeded_availability_entry(member_id, member, date_iso, period, shift_lookup=None):
    date_iso = str(date_iso or "")[:10]
    period = str(period or "").strip().upper()
    if not is_june_2026_date(date_iso) or period not in {"AM", "PM"}:
        return None
    shifts = shift_lookup if isinstance(shift_lookup, dict) else schedule_shift_lookup()
    shift = shifts.get((date_iso, period))
    intent = "prefer" if member_is_assigned_to_shift(member_id, member, shift) else "do_not"
    return {
        "member_id": str(member_id),
        "date": date_iso,
        "period": period,
        "member_intent": intent,
        "updated_at": None,
        "updated_by": None,
        "source": "google_calendar_mirror",
        "logic_mode": "mirror_only",
        "availability_seeded": True,
        "seed_type": "assigned_schedule_to_availability",
        "member_submitted": False,
        "transactions_live": True,
    }


def june_seeded_availability_value(member_id, member, date_iso, period):
    entry = june_seeded_availability_entry(member_id, member, date_iso, period)
    if not entry:
        return None
    return availability_value_for_intent(entry["member_intent"])


def extract_member_availability(member_id):
    payload = load_availability_payload()
    member = member_record_by_id(member_id)
    shift_lookup = schedule_shift_lookup()
    filtered = {"months": {}, "patterns_by_member": {}, "intent_metadata": {}, "entries": []}
    explicit_keys = set()
    for month_key, month_bucket in payload.get("months", {}).items():
        if not isinstance(month_bucket, dict):
            continue
        member_bucket = month_bucket.get(member_id)
        if isinstance(member_bucket, dict):
            filtered["months"][month_key] = {member_id: member_bucket}
            for date_iso, day_entry in member_bucket.items():
                if not isinstance(day_entry, dict):
                    continue
                for period, value in day_entry.items():
                    date_key = str(date_iso)[:10]
                    period_key = str(period).upper()
                    explicit_keys.add((date_key, period_key))
                    intent = canonical_member_intent(value)
                    if intent is None:
                        intent = "blank"
                    meta = availability_intent_metadata(payload, member_id, date_key, period_key)
                    filtered["entries"].append({
                        "member_id": member_id,
                        "date": date_key,
                        "period": period_key,
                        "member_intent": intent,
                        "updated_at": meta.get("updated_at"),
                        "updated_by": meta.get("updated_by"),
                        "source": meta.get("source") or "legacy_availability",
                        "logic_mode": meta.get("logic_mode"),
                        "availability_seeded": bool(meta.get("availability_seeded", False)),
                        "seed_type": meta.get("seed_type"),
                        "member_submitted": bool(meta.get("member_submitted", True)),
                        "transactions_live": bool(meta.get("transactions_live", False)),
                        "previous_seeded_value": meta.get("previous_seeded_value"),
                    })
    if member is not None:
        for day in range(1, 31):
            date_iso = f"2026-06-{day:02d}"
            for period in ("AM", "PM"):
                if (date_iso, period) in explicit_keys:
                    continue
                seeded = june_seeded_availability_entry(member_id, member, date_iso, period, shift_lookup)
                if not seeded:
                    continue
                filtered["months"].setdefault("2026-06", {}).setdefault(member_id, {}).setdefault(date_iso, {})[period] = availability_value_for_intent(seeded["member_intent"])
                filtered["entries"].append(seeded)
    patterns = payload.get("patterns_by_member", {})
    if isinstance(patterns, dict) and isinstance(patterns.get(member_id), dict):
        filtered["patterns_by_member"][member_id] = patterns[member_id]
    metadata = payload.get("intent_metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get(member_id), dict):
        filtered["intent_metadata"][member_id] = metadata[member_id]
    return filtered


def canonical_member_intent(value):
    if isinstance(value, dict):
        value = value.get("member_intent") or value.get("intent") or value.get("status")
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "preferred": "prefer",
        "prefer": "prefer",
        "yes": "prefer",
        "available": "available",
        "can_work": "available",
        "do_not_schedule": "do_not",
        "do_not": "do_not",
        "unavailable": "do_not",
        "dns": "do_not",
        "no": "do_not",
        "blank": "blank",
        "unset": "blank",
        "none": "blank",
        "no_answer": "blank",
        "": "blank",
    }
    return aliases.get(raw)


def availability_value_for_intent(intent):
    return {
        "prefer": "preferred",
        "available": "available",
        "do_not": "do_not_schedule",
        "blank": "blank",
    }[intent]


def availability_intent_metadata(payload, member_id, date_iso, period):
    metadata = payload.get("intent_metadata", {}) if isinstance(payload, dict) else {}
    entry = metadata.get(member_id, {}).get(date_iso, {}).get(period) if isinstance(metadata, dict) else None
    return entry if isinstance(entry, dict) else {}


def validate_availability_entry(member_id, entry):
    if not isinstance(entry, dict):
        raise ValueError("Each availability entry must be an object")
    date_iso = str(entry.get("date") or "").strip()[:10]
    try:
        date_obj = datetime.fromisoformat(date_iso).date()
    except ValueError as exc:
        raise ValueError(f"Invalid availability date: {date_iso or '<blank>'}") from exc
    period = str(entry.get("period") or entry.get("shift") or "").strip().upper()
    if period not in {"AM", "PM"}:
        raise ValueError("Availability period must be AM or PM")
    intent = canonical_member_intent(entry.get("member_intent", entry.get("intent", entry.get("status"))))
    if intent not in {"blank", "prefer", "available", "do_not"}:
        raise ValueError("member_intent must be blank, prefer, available, or do_not")
    return {
        "member_id": member_id,
        "date": date_iso,
        "date_obj": date_obj,
        "period": period,
        "member_intent": intent,
    }


def save_member_availability_entries(member_id, entries, actor_member_id=None):
    if not isinstance(entries, list):
        raise ValueError("Availability payload entries must be a list")
    member = member_record_by_id(member_id)
    if member is None:
        raise ValueError("Member record not found")

    full_payload = load_availability_payload()
    edit_start_date = member_availability_edit_start_date()
    now_value = now_iso()
    actor = str(actor_member_id or member_id)
    saved = []

    for raw_entry in entries:
        entry = validate_availability_entry(member_id, raw_entry)
        if entry["date_obj"] < edit_start_date:
            raise ValueError("Availability in the current Thursday cycle is locked for member editing")
        month_key = entry["date"][:7]
        value = availability_value_for_intent(entry["member_intent"])
        full_payload.setdefault("months", {}).setdefault(month_key, {}).setdefault(member_id, {}).setdefault(entry["date"], {})
        before_value = full_payload["months"][month_key][member_id][entry["date"]].get(entry["period"])
        seeded_before_value = None if before_value is not None else june_seeded_availability_value(member_id, member, entry["date"], entry["period"])
        effective_before_value = before_value if before_value is not None else seeded_before_value
        full_payload["months"][month_key][member_id][entry["date"]][entry["period"]] = value
        meta = {
            "member_id": member_id,
            "date": entry["date"],
            "period": entry["period"],
            "member_intent": entry["member_intent"],
            "updated_at": now_value,
            "updated_by": actor,
            "source": "member_portal",
            "logic_mode": "normal",
            "availability_seeded": False,
            "seed_type": None,
            "member_submitted": True,
            "live_beta": True,
            "transactions_live": True,
            "requires_supervisor_review": True,
        }
        if seeded_before_value is not None:
            meta["previous_seeded_value"] = seeded_before_value
            meta["previous_seeded_source"] = "google_calendar_mirror"
            meta["previous_seeded_logic_mode"] = "mirror_only"
            meta["previous_seeded_type"] = "assigned_schedule_to_availability"
        full_payload.setdefault("intent_metadata", {}).setdefault(member_id, {}).setdefault(entry["date"], {})[entry["period"]] = meta
        record_live_beta_transaction(
            "availability_intent",
            actor_member_id=actor,
            affected={
                "member_id": member_id,
                "date": entry["date"],
                "shift": entry["period"],
                "seat": None,
            },
            before={
                "availability_value": effective_before_value,
                "seeded_value": seeded_before_value,
                "source": "google_calendar_mirror" if seeded_before_value is not None else None,
                "logic_mode": "mirror_only" if seeded_before_value is not None else None,
                "availability_seeded": seeded_before_value is not None,
                "seed_type": "assigned_schedule_to_availability" if seeded_before_value is not None else None,
                "member_submitted": False if seeded_before_value is not None else None,
            },
            after={
                "availability_value": value,
                "member_intent": entry["member_intent"],
                "availability_seeded": False,
                "member_submitted": True,
            },
            source="member_portal",
        )
        saved.append(meta)

    save_availability_payload(full_payload)
    return saved


def apply_member_profile_update(member, payload):
    employment = member.setdefault("employment", {}) if isinstance(member, dict) else {}
    preferences = member.setdefault("preferences", {}) if isinstance(member, dict) else {}
    scheduler = member.setdefault("scheduler", {}) if isinstance(member, dict) else {}
    shift_preference = preferences.setdefault("shift_preference", {})
    today_iso = datetime.now(LOCAL_TZ).date().isoformat()

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
    if "medical_cert" in payload:
        medical_cert = canonical_medical_cert(payload.get("medical_cert"))
        if medical_cert not in MEDICAL_CERT_RANKS:
            raise ValueError("medical_cert must be NCLD, EMR, EMT, AEMT, or Paramedic")
        member["medical_cert"] = medical_cert
        member["medical_cert_rank"] = MEDICAL_CERT_RANKS[medical_cert]
        member["medical_cert_label"] = MEDICAL_CERT_LABELS[medical_cert]
        member["ops_cert"] = medical_cert
        member["cert"] = medical_cert
        member["ncld_status"] = medical_cert == "NCLD"
    if "ncld_status" in payload:
        member["ncld_status"] = bool(payload.get("ncld_status"))
        if member["ncld_status"]:
            member["medical_cert"] = "NCLD"
            member["medical_cert_rank"] = MEDICAL_CERT_RANKS["NCLD"]
            member["medical_cert_label"] = MEDICAL_CERT_LABELS["NCLD"]
            member["ops_cert"] = "NCLD"
            member["cert"] = "NCLD"
    if "ncld_interest_level" in payload:
        value = str(payload.get("ncld_interest_level") or "unknown").strip()
        allowed = {"unknown", "interested", "active_support", "not_interested"}
        if value not in allowed:
            raise ValueError("ncld_interest_level must be unknown, interested, active_support, or not_interested")
        member["ncld_interest_level"] = value
        member["last_interest_update"] = today_iso
    if "ncld_notes" in payload:
        member["ncld_notes"] = str(payload.get("ncld_notes") or "")
        member["last_interest_update"] = today_iso
    if "last_interest_update" in payload:
        raw = str(payload.get("last_interest_update") or "").strip()
        if raw:
            datetime.fromisoformat(raw[:10])
        member["last_interest_update"] = raw or None
    normalize_member_rotation(member)


def member_availability_edit_start_date():
    from engine.resolver import local_operational_today, next_operational_cycle_start_for

    return next_operational_cycle_start_for(local_operational_today())


def apply_member_availability_update(member_id, payload):
    if isinstance(payload, dict) and "entries" in payload:
        save_member_availability_entries(member_id, payload.get("entries"), actor_member_id=member_id)
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("months"), dict):
        raise ValueError("Availability payload must contain a months object")

    full_payload = load_availability_payload()
    edit_start_date = member_availability_edit_start_date()

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
            if date_obj < edit_start_date:
                raise ValueError("Availability in the current Thursday cycle is locked for member editing")
            full_payload.setdefault("months", {}).setdefault(month_key, {}).setdefault(member_id, {})
            if isinstance(day_entry, dict):
                previous_day = dict(full_payload["months"][month_key][member_id].get(date_iso, {}))
                full_payload["months"][month_key][member_id][date_iso] = day_entry
                for period, value in day_entry.items():
                    period_label = str(period or "").strip().upper()
                    if period_label not in {"AM", "PM"}:
                        continue
                    member = member_record_by_id(member_id)
                    seeded_before_value = None
                    if previous_day.get(period) is None and member is not None:
                        seeded_before_value = june_seeded_availability_value(member_id, member, date_iso, period_label)
                    effective_before_value = previous_day.get(period) if previous_day.get(period) is not None else seeded_before_value
                    record_live_beta_transaction(
                        "availability_intent",
                        actor_member_id=member_id,
                        affected={
                            "member_id": member_id,
                            "date": str(date_iso)[:10],
                            "shift": period_label,
                            "seat": None,
                        },
                        before={
                            "availability_value": effective_before_value,
                            "seeded_value": seeded_before_value,
                            "source": "google_calendar_mirror" if seeded_before_value is not None else None,
                            "logic_mode": "mirror_only" if seeded_before_value is not None else None,
                            "availability_seeded": seeded_before_value is not None,
                            "seed_type": "assigned_schedule_to_availability" if seeded_before_value is not None else None,
                            "member_submitted": False if seeded_before_value is not None else None,
                        },
                        after={
                            "availability_value": value,
                            "availability_seeded": False,
                            "member_submitted": True,
                        },
                        source="member_portal",
                    )

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
    # Rescue pass: let the Supervisor shell open without a Flask session.
    # Protected write APIs still enforce supervisor auth.
    if lowered in {"admin.html", "admin_members.html"} and current_auth()["role"] != "supervisor":
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
    return redirect("/docs/supervisor.html")


@app.route("/admin")
def admin_shortcut():
    if current_auth()["role"] != "supervisor":
        return login_redirect("supervisor")
    return redirect("/docs/admin.html")


@app.route("/admin/members")
def admin_members_shortcut():
    if current_auth()["role"] != "supervisor":
        return login_redirect("supervisor")
    return redirect("/docs/admin_members.html")


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
        "email": auth.get("email"),
        "beta_auth_bridge": auth.get("beta_auth_bridge") is True,
        "quick_test_mode": quick_test_mode_enabled(),
        "demo_supervisor_bypass": demo_supervisor_bypass_enabled(),
        "auth_mode": "quick_test" if quick_test_mode_enabled() and not auth["authenticated"] else "real_login",
        "build_code": BUILD_CODE,
        "public_base_url": current_public_base_url(),
    }
    if auth["role"] == "member":
        member = current_member_record()
        if member:
            payload["member_name"] = member.get("name") or f"Member {auth['member_id']}"
    return jsonify(payload)


@app.route("/api/auth/beta-session", methods=["POST"])
def auth_beta_session():
    payload = request.get_json(silent=True) or {}
    session_payload = verify_beta_session_token(payload.get("token"))
    if not session_payload:
        return auth_json_error("Invalid or expired beta session", 401)
    return jsonify(session_payload)


@app.route("/api/testing/members", methods=["GET"])
def testing_members():
    if not local_testing_login_allowed():
        return auth_json_error("Testing login is only available on localhost", 404)
    members = []
    for member in load_members():
        member_id = str(member.get("member_id", member.get("id")) or "").strip()
        if not member_id:
            continue
        members.append({
            "member_id": member_id,
            "name": member.get("name") or f"Member {member_id}",
            "cert": member.get("ops_cert") or member.get("cert") or member.get("raw_cert") or "",
            "active": member.get("active", True) is not False,
        })
    members.sort(key=lambda row: (not row["active"], row["name"].lower(), row["member_id"]))
    return jsonify({"members": members, "testing_login": True})


@app.route("/api/testing/login_as_member", methods=["POST"])
def testing_login_as_member():
    if not local_testing_login_allowed():
        return auth_json_error("Testing login is only available on localhost", 404)
    payload = request.get_json(silent=True) or request.form or {}
    member_id = str(payload.get("member_id") or payload.get("selected_member_id") or "").strip()
    next_url = str(payload.get("next") or "/member").strip() or "/member"
    requested_role = str(payload.get("role") or "").strip().lower()
    member = member_record_by_id(member_id)
    if not member:
        return auth_json_error("Member record not found", 404)
    if requested_role == "supervisor" or next_url.startswith(("/supervisor", "/admin", "/docs/supervisor", "/docs/admin")):
        start_supervisor_session()
        return jsonify({
            "status": "ok",
            "role": "supervisor",
            "member_id": member_id,
            "member_name": member.get("name") or f"Member {member_id}",
            "redirect": next_url,
            "auth_mode": "local_testing_dropdown",
            "quick_test_mode": quick_test_mode_enabled(),
        })
    start_member_session(member_id)
    response = member_login_success_payload(member_id, next_url)
    response["auth_mode"] = "local_testing_dropdown"
    response["quick_test_mode"] = quick_test_mode_enabled()
    return jsonify(response)


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


@app.route("/api/calendar_markers", methods=["GET"])
def get_calendar_markers():
    return jsonify(load_calendar_markers_payload())


@app.route("/api/calendar_markers", methods=["POST"])
@require_role("supervisor")
def save_calendar_markers():
    incoming = request.get_json(silent=True)
    if incoming is None:
        return jsonify({"error": "No JSON body provided"}), 400
    payload = save_calendar_markers_payload(incoming)
    return jsonify({"status": "ok", "count": len(payload.get("markers", []))})


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


@app.route("/api/live_beta/transactions", methods=["GET"])
@require_role("supervisor")
def get_live_beta_transactions():
    return jsonify(load_live_beta_transactions())


@app.route("/api/member/context", methods=["GET"])
def get_member_context():
    member_id, member, error = resolve_member_read_target()
    if error:
        return error
    settings = load_settings()
    member_page_settings = settings.get("member_page", {}) if isinstance(settings.get("member_page"), dict) else {}
    return jsonify(
        {
            "member": member,
            "roster": member_roster_payload(),
            "availability": extract_member_availability(member_id),
            "schedule": load_schedule_payload(),
            "change_requests": member_change_requests(member_id),
            "availability_edit_start_date": member_availability_edit_start_date().isoformat(),
            "member_page_settings": {
                "availability_max_forward_weeks": member_page_settings.get("availability_max_forward_weeks"),
                "display_horizon": settings.get("display_horizon", DEFAULT_DISPLAY_HORIZON),
            },
            "rollout": rollout_status_payload(),
            "auth_mode": "quick_test" if quick_test_mode_enabled() else "real_login",
            "quick_test_mode": quick_test_mode_enabled(),
            "selected_member_id": member_id,
        }
    )


@app.route("/api/member_dashboard", methods=["GET"])
def get_member_dashboard():
    member_id, _, error = resolve_member_read_target()
    if error:
        return error
    dashboard = build_member_dashboard(
        member_id,
        members_payload=load_members_payload(),
        schedule_payload=load_schedule_payload(),
        availability_payload=load_availability_payload(),
        settings=load_settings(),
        rotation_templates=load_json(ROTATION_TEMPLATES_FILE, {}),
        change_requests_payload=load_change_requests_for_queue(),
        start_date=request.args.get("start") or request.args.get("start_date"),
        end_date=request.args.get("end") or request.args.get("end_date"),
    )
    if dashboard is None:
        return auth_json_error("Member record not found", 404)
    dashboard["auth_mode"] = "quick_test" if quick_test_mode_enabled() else "real_login"
    dashboard["quick_test_mode"] = quick_test_mode_enabled()
    return jsonify(dashboard)


def member_change_requests(member_id):
    member_id = str(member_id or "").strip()
    rows = []
    for row in load_change_requests_for_queue():
        if not isinstance(row, dict):
            continue
        original = row.get("original_assignment") if isinstance(row.get("original_assignment"), dict) else {}
        if str(row.get("original_member_id") or row.get("created_by_member_id") or original.get("member_id") or "").strip() == member_id:
            rows.append(row)
    return rows


def coverage_candidate_payload(candidate):
    if not isinstance(candidate, dict):
        return None
    intent = str(candidate.get("bid_strength") or "").strip().upper()
    if intent not in {"PREFER", "AVAILABLE"}:
        return None
    return {
        "member_id": str(candidate.get("member_id") or "").strip(),
        "name": candidate.get("member_name") or candidate.get("name"),
        "intent": "Prefer" if intent == "PREFER" else "Available",
        "bid_strength": intent,
        "intent_rank": 1 if intent == "PREFER" else 2,
        "cert": candidate.get("cert"),
        "qualification_match": candidate.get("qualification_match") is not False,
        "eligible_low_risk": candidate.get("eligible_low_risk") is True,
        "warnings": candidate.get("warnings", []) if isinstance(candidate.get("warnings"), list) else [],
    }


def coverage_request_candidate_summary(request_row, schedule=None, members=None, availability=None):
    schedule = schedule if isinstance(schedule, dict) else load_schedule_payload()
    members = members if members is not None else load_members()
    availability = availability if isinstance(availability, dict) else load_availability_payload()
    validation = review_shift_change_request(schedule, members, availability, request_row)
    raw_candidates = validation.get("candidate_summary", []) if isinstance(validation, dict) else []
    candidates = [row for row in (coverage_candidate_payload(candidate) for candidate in raw_candidates) if row]
    candidates.sort(key=lambda row: (row["intent_rank"], 0 if row["eligible_low_risk"] else 1, str(row.get("name") or "")))
    prefer_count = sum(1 for row in candidates if row["intent"] == "Prefer")
    available_count = sum(1 for row in candidates if row["intent"] == "Available")
    clean_prefer_count = sum(1 for row in candidates if row["intent"] == "Prefer" and row["eligible_low_risk"])
    warnings = []
    for candidate in candidates:
        warnings.extend(candidate.get("warnings") or [])
    if isinstance(validation.get("warnings"), list):
        warnings.extend(validation["warnings"])
    if not candidates:
        recommendation = "No candidates yet"
    elif clean_prefer_count == 1 and len(candidates) == 1:
        recommendation = "Clean candidate"
    else:
        recommendation = "Supervisor review"
    coverage_before = validation.get("coverage_before") if isinstance(validation.get("coverage_before"), dict) else {}
    original = request_row.get("original_assignment") if isinstance(request_row.get("original_assignment"), dict) else {}
    current_assigned = {
        "member_id": coverage_before.get("member_id") or original.get("member_id") or request_row.get("original_member_id"),
        "name": coverage_before.get("member_name") or original.get("member_name"),
    }
    return {
        "validation": validation,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "prefer_count": prefer_count,
        "available_count": available_count,
        "recommendation_label": recommendation,
        "warnings": list(dict.fromkeys(str(warning) for warning in warnings if warning)),
        "review_reasons": validation.get("reasons", []) if isinstance(validation.get("reasons"), list) else [],
        "current_assigned_member": current_assigned,
    }


def enrich_coverage_request_for_queue(request_row, schedule=None, members=None, availability=None):
    row = deepcopy(request_row)
    original = row.get("original_assignment") if isinstance(row.get("original_assignment"), dict) else {}
    summary = coverage_request_candidate_summary(row, schedule, members, availability)
    members = members if members is not None else load_members()
    member_by_id = {
        str(member.get("member_id") or member.get("id") or "").strip(): member
        for member in members
        if isinstance(member, dict)
    }
    original_member_id = str(row.get("original_member_id") or row.get("created_by_member_id") or original.get("member_id") or "").strip()
    original_member = member_by_id.get(original_member_id) or {}
    row["request_id"] = row.get("request_id")
    row["original_member"] = {
        "member_id": original_member_id,
        "name": original.get("member_name") or original_member.get("name"),
    }
    row["date"] = str(row.get("date") or original.get("date") or "")[:10]
    row["period"] = normalize_shift_label(row.get("period") or original.get("period"))
    row["seat_role"] = str(row.get("seat_role") or original.get("role") or "").strip().upper()
    row.update(summary)
    return row


def coverage_queue_item_as_request(queue_row):
    if not isinstance(queue_row, dict):
        return None
    if queue_row.get("request_id") and str(queue_row.get("type") or "") == "drop_coverage_request":
        return queue_row
    if str(queue_row.get("reason") or "") != "assigned_member_marked_do_not_after_commit":
        return None
    shift = queue_row.get("shift") if isinstance(queue_row.get("shift"), dict) else {}
    seat = queue_row.get("seat") if isinstance(queue_row.get("seat"), dict) else {}
    date_iso = str(shift.get("date") or "")[:10]
    period = normalize_shift_label(shift.get("period"))
    role = str(seat.get("role") or "").strip().upper()
    member_id = str(seat.get("member_id") or "").strip()
    seat_id = str(seat.get("seat_id") or "").strip()
    if not date_iso or not period or not role or not member_id:
        return None
    return {
        "request_id": f"derived_coverage_{date_iso}_{period}_{role}_{member_id}",
        "request_type": "coverage_request",
        "type": "drop_coverage_request",
        "status": "pending",
        "derived": True,
        "reason": queue_row.get("reason"),
        "original_member_id": member_id,
        "date": date_iso,
        "period": period,
        "seat_role": role,
        "original_assignment": {
            "seat_key": seat_id,
            "seat_id": seat_id,
            "date": date_iso,
            "period": period,
            "role": role,
            "member_id": member_id,
            "member_name": seat.get("member_name"),
            "assignment_status": seat.get("assignment_status"),
        },
    }


def request_record_for_assigned_seat(actor_member_id, shift, seat, index, comment=None):
    date_iso = str(shift.get("date") or shift.get("shift_date") or "")[:10]
    period = shift_period_value(shift)
    role = seat_role_value(seat)
    seat_key = seat_key_for_request(shift, seat, index)
    member_id = str(actor_member_id or "").strip()
    member_name = seat.get("assigned_name") or member_display_name(member_record_by_id(member_id) or {})
    created_at = now_iso()
    return {
        "request_id": f"scr_cov_{int(time.time() * 1000)}_{secrets.token_hex(4)}",
        "request_type": "coverage_request",
        "type": "drop_coverage_request",
        "status": "pending",
        "original_member_id": member_id,
        "created_by_member_id": member_id,
        "replacement_member_id": None,
        "requested_replacement_member_id": None,
        "supervisor_review_required": True,
        "date": date_iso,
        "period": period,
        "seat_role": role,
        "comment": str(comment or "").strip() or None,
        "created_at": created_at,
        "updated_at": created_at,
        "original_assignment": {
            "seat_key": seat_key,
            "seat_id": str(seat.get("seat_id") or seat_key),
            "date": date_iso,
            "period": period,
            "role": role,
            "member_id": member_id,
            "member_name": member_name,
            "assignment_status": seat.get("assignment_status") or "ASSIGNED",
        },
        "bid_overlay": {
            "opens_for_bidding": True,
            "seat_key": seat_key,
        },
        "audit": [
            {
                "event": "coverage_request_created",
                "at": created_at,
                "actor_member_id": member_id,
                "note": "Original assignment preserved; assigned member remains responsible until supervisor approval.",
            }
        ],
    }


def matching_pending_coverage_request(rows, member_id, date_iso, period, role):
    for row in rows:
        if not isinstance(row, dict):
            continue
        original = row.get("original_assignment") if isinstance(row.get("original_assignment"), dict) else {}
        if str(row.get("type") or "") != "drop_coverage_request":
            continue
        if str(row.get("status") or "").strip().lower() not in {"pending", "pending_supervisor_review", "pending_bids"}:
            continue
        if str(row.get("original_member_id") or row.get("created_by_member_id") or original.get("member_id") or "").strip() != member_id:
            continue
        if str(original.get("date") or row.get("date") or "")[:10] != date_iso:
            continue
        if str(original.get("period") or row.get("period") or "").strip().upper() != period:
            continue
        if role and str(original.get("role") or row.get("seat_role") or "").strip().upper() != role:
            continue
        return row
    return None


@app.route("/api/member/change-requests", methods=["GET"])
def get_member_change_requests():
    auth = current_auth()
    requested_id = str(request.args.get("member_id") or "").strip()
    if not auth.get("authenticated"):
        return auth_json_error("Authentication required", 401)
    if auth.get("role") == "supervisor":
        if not requested_id:
            return jsonify({"requests": load_change_requests_for_queue(), "generated_at": now_iso()})
        return jsonify({"requests": member_change_requests(requested_id), "member_id": requested_id, "generated_at": now_iso()})
    auth_member_id = str(auth.get("member_id") or "").strip()
    if not auth_member_id:
        return auth_json_error("Member session required", 403)
    if requested_id and requested_id != auth_member_id:
        return auth_json_error("Cannot view another member's change requests", 403)
    return jsonify({"requests": member_change_requests(auth_member_id), "member_id": auth_member_id, "generated_at": now_iso()})


@app.route("/api/member/request-coverage", methods=["POST"])
def request_member_coverage():
    auth = current_auth()
    if not auth.get("authenticated"):
        return auth_json_error("Authentication required", 401)
    actor_member_id = str(auth.get("member_id") or "").strip()
    if not actor_member_id:
        return auth_json_error("Member session required for coverage requests", 403)
    payload = request.get_json(silent=True) or {}
    requested_member_id = str(payload.get("member_id") or payload.get("original_member_id") or actor_member_id).strip()
    if requested_member_id != actor_member_id:
        return auth_json_error("Members may only request coverage for their own assigned shifts", 403)
    date_iso = str(payload.get("date") or "")[:10]
    period = normalize_shift_label(payload.get("period") or payload.get("label"))
    seat_role = str(payload.get("seat_role") or payload.get("role") or "").strip().upper()
    seat_id = str(payload.get("seat_id") or payload.get("seat_key") or "").strip()
    if not date_iso or not period:
        return auth_json_error("date and period are required", 400)
    shift_day = parse_iso_date(date_iso)
    if not shift_day:
        return auth_json_error("Invalid shift date", 400)
    if shift_day < datetime.now(LOCAL_TZ).date():
        return auth_json_error("Coverage requests are only available for current or future shifts", 400)

    schedule = load_schedule_payload()
    shift, seat, index = find_assigned_shift_seat(schedule, actor_member_id, date_iso, period, seat_role, seat_id)
    if not shift or not seat:
        return auth_json_error("Assigned seat not found for this member/date/period", 404)

    payload_store = load_shift_change_requests_payload()
    existing = matching_pending_coverage_request(payload_store["requests"], actor_member_id, date_iso, period, seat_role_value(seat))
    if existing:
        return jsonify({
            "status": "ok",
            "ok": True,
            "saved": True,
            "already_exists": True,
            "request": existing,
            "assignment_preserved": True,
        })

    record = request_record_for_assigned_seat(actor_member_id, shift, seat, index or 0, payload.get("comment") or payload.get("reason"))
    review = review_shift_change_request(schedule, load_members(), load_availability_payload(), record)
    if review.get("decision") == "denied":
        return jsonify({"error": "Coverage request failed validation", "validation": review}), 400
    record["validation"] = review
    payload_store["requests"].append(record)
    save_shift_change_requests_payload(payload_store)
    return jsonify({
        "status": "ok",
        "ok": True,
        "saved": True,
        "request": record,
        "assignment_preserved": True,
        "responsibility_remains_with_member": True,
    })


@app.route("/api/member/timecard", methods=["GET"])
def api_member_timecard():
    member_id, _, error = resolve_member_read_target()
    if error:
        return error
    payload = build_member_timecard(
        member_id,
        period_start=request.args.get("start") or request.args.get("period_start"),
        period_end=request.args.get("end") or request.args.get("period_end"),
    )
    if payload is None:
        return auth_json_error("Member record not found", 404)
    return jsonify(payload)


@app.route("/member/timecard", methods=["GET"])
def member_timecard_page():
    member_id, _, error = resolve_member_request_member()
    if error:
        return login_redirect("member")
    payload = build_member_timecard(
        member_id,
        period_start=request.args.get("start") or request.args.get("period_start"),
        period_end=request.args.get("end") or request.args.get("period_end"),
    )
    if payload is None:
        return auth_json_error("Member record not found", 404)
    return render_template_string(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>ShiftCommander Time Card</title>
  <style>
    *{box-sizing:border-box}
    body{margin:0;background:#f3f4f6;color:#111827;font-family:Arial,Helvetica,sans-serif;font-size:13px}
    .sheet{width:min(8.5in,100%);min-height:11in;margin:0 auto;background:#fff;padding:.45in;box-shadow:0 12px 36px rgba(0,0,0,.14)}
    .actions{display:flex;gap:10px;justify-content:flex-end;margin-bottom:16px}
    button,a.button{border:1px solid #1f2937;background:#1f2937;color:#fff;border-radius:6px;padding:9px 12px;text-decoration:none;font-weight:700;cursor:pointer}
    a.button{background:#fff;color:#1f2937}
    h1{margin:0;font-size:24px}
    .muted{color:#4b5563}
    .header{display:grid;grid-template-columns:1fr auto;gap:18px;border-bottom:2px solid #111827;padding-bottom:14px;margin-bottom:16px}
    .meta{display:grid;gap:4px;text-align:right}
    .info{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px;margin-bottom:16px}
    .box{border:1px solid #d1d5db;padding:8px;min-height:36px}
    table{width:100%;border-collapse:collapse;margin:12px 0 18px}
    th,td{border:1px solid #9ca3af;padding:7px;text-align:left;vertical-align:top}
    th{background:#f3f4f6;font-size:12px;text-transform:uppercase}
    td.num{text-align:right}
    .summary{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:24px}
    .signature-grid{display:grid;grid-template-columns:1fr 120px 1fr 120px;gap:12px;align-items:end;margin-top:30px}
    .line{border-bottom:1px solid #111827;height:32px}
    .notes{margin-top:20px;border:1px solid #9ca3af;min-height:80px;padding:8px}
    .template-note{margin-top:18px;font-size:11px;color:#6b7280}
    @media print{
      body{background:#fff}
      .sheet{width:auto;min-height:auto;margin:0;box-shadow:none;padding:.25in}
      .actions{display:none}
      @page{size:letter;margin:.35in}
    }
  </style>
</head>
<body>
  <main class="sheet">
    <div class="actions">
      <a class="button" href="/member">Back to Member Page</a>
      <button type="button" onclick="window.print()">Print</button>
    </div>

    <!-- TODO: Replace with official ADR time card template when provided. -->
    <section class="header">
      <div>
        <h1>{{ organization_name }} Time Card</h1>
        <div class="muted">Thursday-Wednesday work summary for signature</div>
      </div>
      <div class="meta">
        <strong>Generated</strong>
        <span>{{ generated_at }}</span>
      </div>
    </section>

    <section class="info">
      <div class="box"><strong>Member</strong><br>{{ member_name }}</div>
      <div class="box"><strong>Member ID</strong><br>{{ member_id }}</div>
      <div class="box" style="grid-column:1/-1"><strong>Time card period</strong><br>{{ period.label }}</div>
    </section>

    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Day</th>
          <th>Shift</th>
          <th>Start Time</th>
          <th>End Time</th>
          <th>Role/Seat</th>
          <th>Hours</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
        <tr>
          <td>{{ row.date }}</td>
          <td>{{ row.day }}</td>
          <td>{{ row.shift }}</td>
          <td>{{ row.start_time }}</td>
          <td>{{ row.end_time }}</td>
          <td>{{ row.role }}</td>
          <td class="num">{{ "%.2f"|format(row.hours) }}</td>
          <td>{{ row.notes }}</td>
        </tr>
        {% else %}
        <tr><td colspan="8" class="muted">No worked shifts found for this member in the current time card period.</td></tr>
        {% endfor %}
      </tbody>
    </table>

    <section class="summary">
      <div class="box"><strong>Total hours</strong><br>{{ "%.2f"|format(summary.total_hours) }}</div>
      <div class="box"><strong>Regular hours</strong><br>{{ "%.2f"|format(summary.regular_hours) }}</div>
      <div class="box"><strong>OT hours</strong><br>{{ "%.2f"|format(summary.ot_hours) }}</div>
      <div class="box"><strong>Shifts worked</strong><br>{{ summary.shifts_worked }}</div>
    </section>

    <section class="signature-grid">
      <div><div class="line"></div><strong>Employee signature</strong></div>
      <div><div class="line"></div><strong>Date</strong></div>
      <div><div class="line"></div><strong>Supervisor signature</strong></div>
      <div><div class="line"></div><strong>Date</strong></div>
    </section>

    <section class="notes"><strong>Notes/comments</strong></section>
    <div class="template-note">First-pass printable template. Payroll export and electronic signatures are not enabled.</div>
  </main>
</body>
</html>
        """,
        **payload,
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
    try:
        apply_member_profile_update(target, payload)
    except (TypeError, ValueError) as exc:
        return auth_json_error(str(exc), 400)
    save_members_payload(members_payload)
    return jsonify({
        "status": "ok",
        "member_id": member_id,
        "auth_mode": "quick_test" if quick_test_mode_enabled() else "real_login",
        "quick_test_mode": quick_test_mode_enabled(),
    })


@app.route("/api/member/availability", methods=["GET"])
def get_member_availability():
    member_id, _, error = resolve_member_read_target()
    if error:
        return error
    return jsonify(extract_member_availability(member_id))


@app.route("/api/member/availability", methods=["POST"])
def save_member_availability():
    payload = request.get_json(silent=True) or {}
    member_id, _, error = resolve_member_write_target(payload)
    if error:
        return error
    try:
        apply_member_availability_update(member_id, payload)
    except ValueError as exc:
        return auth_json_error(str(exc), 400)
    return jsonify({
        "status": "ok",
        "member_id": member_id,
        "availability": extract_member_availability(member_id),
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


@app.route("/api/wallboard_settings", methods=["GET"])
def get_wallboard_settings():
    settings = load_settings()
    return jsonify({
        "resolver_rules": settings.get("resolver_rules", {}) if isinstance(settings, dict) else {},
        "career_fire_driver": settings.get("career_fire_driver", DEFAULT_CAREER_FIRE_DRIVER_RULES) if isinstance(settings, dict) else DEFAULT_CAREER_FIRE_DRIVER_RULES,
        "member_accommodations": settings.get("member_accommodations", DEFAULT_MEMBER_ACCOMMODATIONS) if isinstance(settings, dict) else DEFAULT_MEMBER_ACCOMMODATIONS,
        "display_horizon": settings.get("display_horizon", DEFAULT_DISPLAY_HORIZON) if isinstance(settings, dict) else DEFAULT_DISPLAY_HORIZON,
    })


@app.route("/api/settings", methods=["POST"])
@require_role("supervisor")
def save_settings():
    settings = request.get_json(silent=True)
    if not isinstance(settings, dict):
        return jsonify({"error": "Settings must be an object"}), 400

    settings["display_horizon"] = normalize_display_horizon(settings.get("display_horizon", {}))
    save_settings_payload(settings)
    return jsonify({"status": "ok"})


@app.route("/api/settings/career_fire_driver", methods=["GET"])
@require_role("supervisor")
def get_career_fire_driver_settings():
    settings = load_settings()
    return jsonify(settings.get("career_fire_driver", DEFAULT_CAREER_FIRE_DRIVER_RULES))


@app.route("/api/settings/career_fire_driver", methods=["POST"])
@require_role("supervisor")
def save_career_fire_driver_settings():
    payload = request.get_json(silent=True)
    rules, error = validate_career_fire_driver_rules(payload)
    if error:
        return jsonify({"error": error}), 400
    settings = load_settings()
    settings["career_fire_driver"] = rules
    save_settings_payload(settings)
    return jsonify({"status": "ok", "career_fire_driver": rules})


@app.route("/api/settings/display_horizon", methods=["POST"])
@require_role("supervisor")
def save_display_horizon_settings():
    payload = request.get_json(silent=True) or {}
    rules, error = validate_display_horizon(payload)
    if error:
        return jsonify({"error": error}), 400
    settings = load_settings()
    settings["display_horizon"] = rules
    save_settings_payload(settings)
    return jsonify({"status": "ok", "display_horizon": rules})


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


def build_open_schedule_from_shifts(shifts):
    schedule_shifts = []
    for shift in shifts if isinstance(shifts, list) else []:
        if not isinstance(shift, dict):
            continue
        next_shift = deepcopy(shift)
        date_value = str(next_shift.get("date") or "").strip()
        label = normalize_shift_label(next_shift.get("label"))
        next_shift["label"] = label
        seats = []
        for index, seat in enumerate(next_shift.get("seats", [])):
            if not isinstance(seat, dict):
                continue
            role = str(seat.get("role") or "").strip().upper()
            next_seat = deepcopy(seat)
            next_seat["_seat_index"] = index
            next_seat["seat_id"] = str(next_seat.get("seat_id") or f"{date_value}:{label}:{role}:{index}")
            next_seat["assigned"] = None
            next_seat["assigned_name"] = None
            next_seat["display_open_alert"] = True
            next_seat["preserved_existing_assignment"] = False
            next_seat["fallback_used"] = False
            next_seat["fallback_reason"] = "open_shift_skeleton"
            next_seat["short_explanation"] = "OPEN - not assigned yet"
            seats.append(next_seat)
        next_shift["seats"] = seats
        schedule_shifts.append(next_shift)

    total_seats = sum(len(shift.get("seats", [])) for shift in schedule_shifts)
    return {
        "build": {
            "generated_at": now_iso(),
            "source": "open_shift_skeletons",
            "summary": {
                "total_shift_days": len(schedule_shifts),
                "total_active_seats": total_seats,
                "filled_active_seats": 0,
                "unfilled_active_seats": total_seats,
                "fill_rate": 0,
                "open_assignments": total_seats,
            },
        },
        "shifts": schedule_shifts,
    }


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

def run_resolver(shifts_override=None):
    from engine.rule_based_resolver import resolve_rule_based

    members = load_members()
    shifts = shifts_override if isinstance(shifts_override, list) else load_live_schedule_shifts()
    settings = load_settings()
    availability = load_availability_payload()
    schedule_locked = load_json(SCHEDULE_LOCKED_FILE, {})
    rollout_import = load_json(ROLLOUT_IMPORT_FILE, {})
    rotation_templates = load_json(ROTATION_TEMPLATES_FILE, {})

    ctx = {
        "members": members,
        "shifts": shifts,
        "settings": settings,
        "availability": availability,
        "schedule_locked": schedule_locked,
        "rollout_import": rollout_import,
        "rotation_templates": rotation_templates,
        "build": {
            "generated_at": now_iso()
        }
    }

    result = resolve_rule_based(ctx)
    save_live_schedule(result)
    return result


def preview_resolver(shifts_override=None):
    from engine.rule_based_resolver import resolve_rule_based

    shifts = shifts_override if isinstance(shifts_override, list) else load_live_schedule_shifts()
    ctx = {
        "members": load_members(),
        "shifts": shifts,
        "settings": load_settings(),
        "availability": load_availability_payload(),
        "schedule_locked": load_json(SCHEDULE_LOCKED_FILE, {}),
        "rollout_import": load_json(ROLLOUT_IMPORT_FILE, {}),
        "rotation_templates": load_json(ROTATION_TEMPLATES_FILE, {}),
        "build": {
            "generated_at": now_iso()
        }
    }
    return resolve_rule_based(ctx)


def request_now_param():
    value = request.args.get("now")
    if value:
        return value
    return datetime.now(LOCAL_TZ).isoformat()


def load_change_requests_for_queue():
    combined = list(active_shift_change_requests())
    payload = load_json(SWAP_REQUESTS_FILE, {})
    if isinstance(payload, list):
        combined.extend(row for row in payload if isinstance(row, dict))
        return combined
    if isinstance(payload, dict):
        for key in ("requests", "change_requests", "items"):
            if isinstance(payload.get(key), list):
                combined.extend(row for row in payload[key] if isinstance(row, dict))
                return combined
    return combined


@app.route("/api/schedule/lifecycle", methods=["GET"])
@require_role("supervisor")
def get_schedule_lifecycle():
    settings = load_settings()
    policy = get_commit_policy(settings)
    now_value = request_now_param()
    schedule = load_schedule_payload()
    shifts = schedule.get("shifts", []) if isinstance(schedule, dict) else []
    counts = {"draft": 0, "committed": 0, "visible": 0, "past": 0}
    samples = {}
    for shift in shifts:
        if not isinstance(shift, dict):
            continue
        state = classify_shift_lifecycle(shift, shift.get("label") or shift.get("period"), now_value, settings)
        counts[state] = counts.get(state, 0) + 1
        samples.setdefault(state, {
            "date": str(shift.get("date") or shift.get("shift_date") or "")[:10],
            "period": normalize_shift_label(shift.get("label") or shift.get("period")),
            "state": state,
        })
    return jsonify({
        "status": "ok",
        "read_only": True,
        "schedule_commit": policy,
        "now": now_value,
        "next_commit_at": get_next_commit_at(now_value, settings),
        "current_commit_window": current_commit_window(now_value, settings),
        "counts": counts,
        "samples": samples,
    })


@app.route("/api/schedule/commit-preview", methods=["GET"])
@require_role("supervisor")
def get_schedule_commit_preview():
    return jsonify(preview_schedule_commit(
        load_schedule_payload(),
        load_members(),
        load_availability_payload(),
        load_settings(),
        request_now_param(),
    ))


@app.route("/api/supervisor/schedule-queue", methods=["GET"])
@require_role("supervisor")
def get_supervisor_schedule_queue():
    schedule = load_schedule_payload()
    availability = load_availability_payload()
    members = load_members()
    raw_queue = build_supervisor_schedule_queue(
        schedule,
        availability,
        load_change_requests_for_queue(),
        load_settings(),
        request_now_param(),
        members=members,
    )
    raw_queue["coverage_requests"] = [
        enrich_coverage_request_for_queue(request_like, schedule, members, availability)
        if (request_like := coverage_queue_item_as_request(row))
        else row
        for row in raw_queue.get("coverage_requests", [])
    ]
    return jsonify(raw_queue)


# =========================
# GENERATE SCHEDULE
# =========================

@app.route("/api/generate", methods=["POST"])
@require_role("supervisor")
def generate_schedule():
    built_shifts = run_shift_builder()
    result = run_resolver(built_shifts)

    shift_count = len(built_shifts) if isinstance(built_shifts, list) else 0

    if isinstance(result, dict):
        result["build_stats"] = {"shift_count": shift_count}

    return jsonify(result)


@app.route("/api/build_shifts", methods=["POST"])
@require_role("supervisor")
def build_shifts_only():
    built_shifts = run_shift_builder()
    shift_count = len(built_shifts) if isinstance(built_shifts, list) else 0
    schedule = build_open_schedule_from_shifts(built_shifts)
    save_json(SCHEDULE_FILE, schedule)
    return jsonify({
        "status": "ok",
        "shift_count": shift_count,
        "shifts": built_shifts,
        "schedule": schedule,
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
    before_state = {
        "assigned_member_id": seat_info["assigned_member_id"],
        "assigned_name": seat_info["assigned_name"],
    }
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
    save_live_schedule(schedule_payload)
    save_supervisor_state(state)
    persist_schedule_locked_from_state(schedule_payload, state)
    record_live_beta_transaction(
        "drop_request",
        actor_member_id=current_auth().get("member_id"),
        affected={k: seat_info[k] for k in ("seat_key", "date", "label", "role", "unit", "seat_index")},
        before=before_state,
        after={"state": "DROPPED", "assigned_member_id": None, "assigned_name": None},
        source="supervisor_action",
    )
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
    before_state = {
        "assigned_member_id": seat_info["assigned_member_id"],
        "assigned_name": seat_info["assigned_name"],
    }
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
    save_live_schedule(schedule_payload)
    save_supervisor_state(state)
    persist_schedule_locked_from_state(schedule_payload, state)
    record_live_beta_transaction(
        "open_seat",
        actor_member_id=current_auth().get("member_id"),
        affected={k: seat_info[k] for k in ("seat_key", "date", "label", "role", "unit", "seat_index")},
        before=before_state,
        after={"state": "OPEN", "assigned_member_id": None, "assigned_name": None},
        source="supervisor_action",
    )
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
    record_live_beta_transaction(
        "lock_seat",
        actor_member_id=current_auth().get("member_id"),
        affected={k: seat_info[k] for k in ("seat_key", "date", "label", "role", "unit", "seat_index")},
        before={
            "assigned_member_id": seat_info["assigned_member_id"],
            "assigned_name": seat_info["assigned_name"],
        },
        after={
            "state": "SUPERVISOR_LOCKED",
            "assigned_member_id": seat_info["assigned_member_id"],
            "assigned_name": seat_info["assigned_name"],
        },
        source="supervisor_action",
    )
    return jsonify({"status": "ok", "seat_key": seat_key, "state": "SUPERVISOR_LOCKED"})


@app.route("/api/supervisor/resolve_week", methods=["POST"])
@require_role("supervisor")
def supervisor_resolve_week():
    payload = request.get_json(silent=True) or {}
    dry_run = bool(payload.get("dry_run", False))

    result = preview_resolver() if dry_run else run_resolver()
    shift_count = len(result.get("shifts", [])) if isinstance(result, dict) else 0

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
    return schedule_json_response()


# =========================
# BASE44 BOOTSTRAP (READ-ONLY)
# =========================

@app.route("/api/bootstrap", methods=["GET"])
def get_bootstrap():
    schedule = load_schedule_payload()
    members = load_members_payload()
    settings = load_settings()
    return jsonify({
        "health": health_payload(),
        "members": members,
        "availability": load_availability_payload(),
        "settings": settings,
        "shifts": schedule.get("shifts", []) if isinstance(schedule, dict) else [],
        "schedule": schedule,
        "display": normalize_wallboard_display(schedule, members, settings),
        "rollout": rollout_status_payload(),
        "live_beta_transactions": load_live_beta_transactions(),
        "generated_at": now_iso(),
    })


@app.route("/api/wallboard_display", methods=["GET"])
def get_wallboard_display():
    schedule = load_schedule_payload()
    members = load_members_payload()
    settings = load_settings()
    return jsonify(normalize_wallboard_display(schedule, members, settings))


@app.route("/api/schedule_integrity", methods=["GET"])
def get_schedule_integrity():
    return jsonify(compare_schedule_files())


@app.route("/api/base44/manifest", methods=["GET"])
def get_base44_manifest():
    return jsonify({
        "service": "ShiftCommander",
        "version": os.environ.get("SHIFTCOMMANDER_VERSION"),
        "generated_at": now_iso(),
        "local_base_url": request.host_url.rstrip("/"),
        "source_of_truth": "ShiftCommander backend JSON files/API",
        "endpoints": {
            "health": {"method": "GET", "path": "/api/health"},
            "bootstrap": {"method": "GET", "path": "/api/bootstrap"},
            "schedule": {"method": "GET", "path": "/api/schedule"},
            "wallboard_display": {"method": "GET", "path": "/api/wallboard_display"},
            "live_beta_transactions": {"method": "GET", "path": "/api/live_beta/transactions"},
            "schedule_integrity": {"method": "GET", "path": "/api/schedule_integrity"},
            "generate": {"method": "POST", "path": "/api/generate"},
            "members_get": {"method": "GET", "path": "/api/members"},
            "members_post": {"method": "POST", "path": "/api/members"},
            "availability_get": {"method": "GET", "path": "/api/availability"},
            "availability_post": {"method": "POST", "path": "/api/availability"},
            "settings_get": {"method": "GET", "path": "/api/settings"},
            "settings_post": {"method": "POST", "path": "/api/settings"},
            "shifts_get": {"method": "GET", "path": "/api/shifts"},
            "shifts_post": {"method": "POST", "path": "/api/shifts"},
        },
        "notes": [
            "Base44 should call backend functions/proxies, not the browser directly.",
            "Localhost is dev-only.",
            "Replace base URL with deployed public backend URL for production.",
            "ShiftCommander remains source of truth.",
        ],
    })


SC_UPSTREAM_API_BASE = os.environ.get("SC_UPSTREAM_API_BASE", "https://sc-api.adr-fr.org").rstrip("/")


@app.route("/api/sc_proxy", methods=["GET"])
def sc_proxy_get():
    path = str(request.args.get("path") or "").strip()
    if path not in {"/api/bootstrap", "/api/schedule"}:
        return jsonify({"error": "Unsupported proxy path"}), 400
    upstream_url = f"{SC_UPSTREAM_API_BASE}{path}"
    try:
        req = urllib.request.Request(upstream_url, headers={
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "Mozilla/5.0 ShiftCommanderSupervisor/1.0",
        })
        with urllib.request.urlopen(req, timeout=12) as upstream:
            payload = upstream.read()
            status = upstream.getcode()
            content_type = upstream.headers.get("Content-Type") or "application/json"
        return Response(payload, status=status, mimetype=content_type.split(";", 1)[0])
    except urllib.error.HTTPError as exc:
        payload = exc.read() or json.dumps({"error": str(exc)}).encode("utf-8")
        return Response(payload, status=exc.code, mimetype="application/json")
    except Exception as exc:
        return jsonify({"error": f"Proxy fetch failed: {exc}", "upstream": upstream_url}), 502


# =========================
# HEALTH CHECK
# =========================

def health_payload():
    return {
        "status": "ok",
        "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "build_code": BUILD_CODE,
        "quick_test_mode": SC_QUICK_TEST_MODE,
        "demo_supervisor_bypass": demo_supervisor_bypass_enabled(),
    }


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify(health_payload())


@app.route("/api/debug/connectivity", methods=["GET"])
def debug_connectivity():
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    return jsonify({
        **health_payload(),
        "backend_reachable": True,
        "public_base_url": current_public_base_url(),
        "request_origin": origin or None,
        "request_host_url": str(request.host_url or "").strip().rstrip("/"),
        "request_host": request.host,
        "request_forwarded_proto": request.headers.get("X-Forwarded-Proto"),
        "request_forwarded_host": request.headers.get("X-Forwarded-Host"),
        "request_remote_addr": request.remote_addr,
        "allowed_origin_match": allowed_request_origin(),
        "allowed_origins": SC_ALLOWED_ORIGINS,
        "allowed_origin_suffixes": list(SC_ALLOWED_ORIGIN_SUFFIXES),
        "quick_test_mode": quick_test_mode_enabled(),
        "build_code": BUILD_CODE,
    })


@app.route("/ api / health", methods=["GET"])
def health_malformed_render_path():
    response = jsonify({
        **health_payload(),
        "warning": "Render health check path contains spaces. Set Health Check Path to /api/health.",
    })
    response.headers["X-ShiftCommander-Health-Path-Warning"] = "Set Render Health Check Path to /api/health"
    return response


startup_log("routes registered; startup complete")


# =========================
# RUN
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=SC_FLASK_DEBUG)
