import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _env_path(name: str) -> Optional[str]:
    value = str(os.environ.get(name) or "").strip()
    return value or None


def _resolve_path(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def _default_state_path(state_dir: str, filename: str) -> str:
    return _resolve_path(str(Path(state_dir) / filename))


class FileLiveStateStore:
    """File-backed boundary for mutable beta state.

    This keeps the current JSON behavior intact while giving the app one place
    to redirect live mutable state to durable storage later.
    """

    store_type = "file"

    def __init__(self, base_dir: str, data_dir: str, docs_dir: str):
        self.base_dir = _resolve_path(base_dir)
        self.default_data_dir = _resolve_path(data_dir)
        self.default_docs_dir = _resolve_path(docs_dir)
        self.state_dir = _resolve_path(_env_path("SC_STATE_DIR") or self.default_data_dir)

        self.availability_file = _resolve_path(
            _env_path("SC_AVAILABILITY_FILE") or _default_state_path(self.state_dir, "availability.json")
        )
        self.change_requests_file = _resolve_path(
            _env_path("SC_CHANGE_REQUESTS_FILE") or _default_state_path(self.state_dir, "shift_change_requests.json")
        )
        self.beta_transactions_file = _resolve_path(
            _env_path("SC_BETA_TRANSACTIONS_FILE") or _default_state_path(self.state_dir, "live_beta_transactions.json")
        )
        self.assignment_overlays_file = _resolve_path(
            _env_path("SC_ASSIGNMENT_OVERLAYS_FILE") or _default_state_path(self.state_dir, "assignment_overlays.json")
        )
        self.supervisor_state_file = _resolve_path(
            _env_path("SC_SUPERVISOR_STATE_FILE") or _default_state_path(self.state_dir, "supervisor_state.json")
        )
        self.schedule_locked_file = _resolve_path(
            _env_path("SC_SCHEDULE_LOCKED_FILE") or _default_state_path(self.state_dir, "schedule_locked.json")
        )
        self.schedule_file = _resolve_path(
            _env_path("SC_SCHEDULE_FILE") or _default_state_path(self.state_dir, "schedule.json")
        )
        self.public_schedule_file = _resolve_path(
            _env_path("SC_PUBLIC_SCHEDULE_FILE") or str(Path(self.default_docs_dir) / "data" / "schedule.json")
        )

    def read_json(self, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return default

    def write_json(self, path: str, data: Any) -> Any:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(temp_path, path)
        return data

    def load_availability(self) -> Dict[str, Any]:
        payload = self.read_json(self.availability_file, {"months": {}})
        if not isinstance(payload, dict):
            payload = {"months": {}}
        if not isinstance(payload.get("months"), dict):
            payload["months"] = {}
        return payload

    def save_availability(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {"months": {}}
        if not isinstance(payload.get("months"), dict):
            payload["months"] = {}
        return self.write_json(self.availability_file, payload)

    def load_change_requests(self) -> Dict[str, Any]:
        payload = self.read_json(self.change_requests_file, {"requests": []})
        if isinstance(payload, list):
            payload = {"requests": payload}
        if not isinstance(payload, dict):
            payload = {"requests": []}
        if not isinstance(payload.get("requests"), list):
            payload["requests"] = []
        return payload

    def save_change_requests(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {"requests": []}
        if not isinstance(payload.get("requests"), list):
            payload["requests"] = []
        payload["updated_at"] = utc_now_iso()
        return self.write_json(self.change_requests_file, payload)

    def load_beta_transactions(self) -> Dict[str, Any]:
        payload = self.read_json(self.beta_transactions_file, {"transactions": []})
        if not isinstance(payload, dict):
            payload = {"transactions": []}
        if not isinstance(payload.get("transactions"), list):
            payload["transactions"] = []
        return payload

    def save_beta_transactions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {"transactions": []}
        if not isinstance(payload.get("transactions"), list):
            payload["transactions"] = []
        return self.write_json(self.beta_transactions_file, payload)

    def load_supervisor_state(self) -> Dict[str, Any]:
        payload = self.read_json(self.supervisor_state_file, {"entries": [], "updated_at": None})
        if not isinstance(payload, dict):
            payload = {"entries": [], "updated_at": None}
        if not isinstance(payload.get("entries"), list):
            payload["entries"] = []
        return payload

    def save_supervisor_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {"entries": [], "updated_at": utc_now_iso()}
        if not isinstance(payload.get("entries"), list):
            payload["entries"] = []
        payload["updated_at"] = utc_now_iso()
        return self.write_json(self.supervisor_state_file, payload)

    def load_schedule_locked(self) -> Dict[str, Any]:
        payload = self.read_json(self.schedule_locked_file, {})
        return payload if isinstance(payload, dict) else {}

    def save_schedule_locked(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.write_json(self.schedule_locked_file, payload if isinstance(payload, dict) else {})

    def load_schedule(self) -> Dict[str, Any]:
        payload = self.read_json(self.schedule_file, {})
        return payload if isinstance(payload, dict) else {}

    def save_schedule_pair(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        self.write_json(self.schedule_file, schedule)
        self.write_json(self.public_schedule_file, schedule)
        return schedule

    def store_diagnostics(self) -> Dict[str, Any]:
        return {
            "state_store_type": self.store_type,
            "state_dir_detected": self.state_dir,
            "availability_store_present": os.path.exists(self.availability_file),
            "change_request_store_present": os.path.exists(self.change_requests_file),
            "transaction_store_present": os.path.exists(self.beta_transactions_file),
        }

    def integrity_summary(self) -> Dict[str, Any]:
        requests_payload = self.load_change_requests()
        transactions_payload = self.load_beta_transactions()
        requests = [row for row in requests_payload.get("requests", []) if isinstance(row, dict)]
        transactions = [row for row in transactions_payload.get("transactions", []) if isinstance(row, dict)]
        return {
            **self.store_diagnostics(),
            "assignment_overlay_store_present": os.path.exists(self.assignment_overlays_file),
            "supervisor_state_store_present": os.path.exists(self.supervisor_state_file),
            "schedule_locked_store_present": os.path.exists(self.schedule_locked_file),
            "pending_coverage_request_count": sum(
                1
                for row in requests
                if str(row.get("request_type") or "").strip() == "coverage_request"
                and str(row.get("status") or "").strip().lower() == "pending"
            ),
            "approved_coverage_request_count": sum(
                1
                for row in requests
                if str(row.get("request_type") or "").strip() == "coverage_request"
                and str(row.get("status") or "").strip().lower() == "approved"
            ),
            "audit_event_count": sum(
                len(row.get("audit", [])) if isinstance(row.get("audit"), list) else 0
                for row in requests
            ),
            "transaction_count": len(transactions),
        }


def create_live_state_store(base_dir: str, data_dir: str, docs_dir: str) -> FileLiveStateStore:
    return FileLiveStateStore(base_dir=base_dir, data_dir=data_dir, docs_dir=docs_dir)
