import json
import os
import urllib.error
import urllib.request
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional


SUPPORTED_STATE_BACKENDS = {"file", "d1", "supabase", "neon", "kv"}
RENDER_EPHEMERAL_PREFIXES = (
    "/opt/render/project/src/data",
    "/opt/render/project/src\\data",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _env_path(name: str) -> Optional[str]:
    value = str(os.environ.get(name) or "").strip()
    return value or None


def _resolve_path(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def _default_state_path(state_dir: str, filename: str) -> str:
    return _resolve_path(str(Path(state_dir) / filename))


def _env_value(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or default).strip()


def _looks_like_render_ephemeral_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").rstrip("/")
    return any(normalized == prefix.replace("\\", "/").rstrip("/") for prefix in RENDER_EPHEMERAL_PREFIXES)


def _missing_credentials(names: list[str]) -> list[str]:
    return [name for name in names if not _env_value(name)]


def _secret_fingerprint(value: str) -> Optional[str]:
    value = str(value or "")
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


class FileLiveStateStore:
    """File-backed boundary for mutable beta state.

    This keeps the current JSON behavior intact while giving the app one place
    to redirect live mutable state to durable storage later.
    """

    store_type = "file"
    state_backend = "file"
    state_backend_ready = True

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

    @property
    def state_backend_detail(self) -> str:
        if _looks_like_render_ephemeral_path(self.state_dir):
            return "file backend is using Render's ephemeral app filesystem; live beta writes may be lost on redeploy"
        return "file backend ready"

    @property
    def state_backend_warning(self) -> Optional[str]:
        if _looks_like_render_ephemeral_path(self.state_dir):
            return "file backend is using Render ephemeral storage; configure a durable backend before trusting live beta writes"
        return None

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

    def read_availability(self) -> Dict[str, Any]:
        return self.load_availability()

    def write_availability(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.save_availability(payload)

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

    def read_change_requests(self) -> Dict[str, Any]:
        return self.load_change_requests()

    def write_change_requests(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.save_change_requests(payload)

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

    def append_transaction(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        payload = self.load_beta_transactions()
        payload["transactions"].append(transaction)
        payload["updated_at"] = transaction.get("created_at") or utc_now_iso()
        self.save_beta_transactions(payload)
        return transaction

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

    def read_supervisor_state(self) -> Dict[str, Any]:
        return self.load_supervisor_state()

    def write_supervisor_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.save_supervisor_state(payload)

    def load_schedule_locked(self) -> Dict[str, Any]:
        payload = self.read_json(self.schedule_locked_file, {})
        return payload if isinstance(payload, dict) else {}

    def save_schedule_locked(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.write_json(self.schedule_locked_file, payload if isinstance(payload, dict) else {})

    def read_schedule_locked(self) -> Dict[str, Any]:
        return self.load_schedule_locked()

    def write_schedule_locked(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.save_schedule_locked(payload)

    def read_assignment_overlays(self) -> Dict[str, Any]:
        payload = self.read_json(self.assignment_overlays_file, {"overlays": []})
        if not isinstance(payload, dict):
            payload = {"overlays": []}
        if not isinstance(payload.get("overlays"), list):
            payload["overlays"] = []
        return payload

    def write_assignment_overlays(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {"overlays": []}
        if not isinstance(payload.get("overlays"), list):
            payload["overlays"] = []
        payload["updated_at"] = utc_now_iso()
        return self.write_json(self.assignment_overlays_file, payload)

    def load_schedule(self) -> Dict[str, Any]:
        payload = self.read_json(self.schedule_file, {})
        return payload if isinstance(payload, dict) else {}

    def save_schedule_pair(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        self.write_json(self.schedule_file, schedule)
        self.write_json(self.public_schedule_file, schedule)
        return schedule

    def store_diagnostics(self) -> Dict[str, Any]:
        files = {
            "availability": os.path.exists(self.availability_file),
            "change_requests": os.path.exists(self.change_requests_file),
            "transactions": os.path.exists(self.beta_transactions_file),
            "supervisor_state": os.path.exists(self.supervisor_state_file),
            "schedule_locked": os.path.exists(self.schedule_locked_file),
            "assignment_overlays": os.path.exists(self.assignment_overlays_file),
        }
        diagnostics = {
            "state_store_type": self.store_type,
            "state_backend": self.state_backend,
            "state_backend_ready": self.state_backend_ready,
            "state_backend_detail": self.state_backend_detail,
            "state_dir_detected": self.state_dir,
            "availability_store_present": os.path.exists(self.availability_file),
            "change_request_store_present": os.path.exists(self.change_requests_file),
            "transaction_store_present": os.path.exists(self.beta_transactions_file),
            "state_files_or_tables_detected": files,
        }
        warning = self.state_backend_warning
        if warning:
            diagnostics["state_backend_warning"] = warning
        return diagnostics

    def integrity_summary(self) -> Dict[str, Any]:
        read_errors = []

        try:
            requests_payload = self.load_change_requests()
        except Exception as exc:
            requests_payload = {"requests": []}
            read_errors.append(f"change_requests: {exc}")

        try:
            transactions_payload = self.load_beta_transactions()
        except Exception as exc:
            transactions_payload = {"transactions": []}
            read_errors.append(f"transactions: {exc}")

        if not isinstance(requests_payload, dict):
            requests_payload = {"requests": []}
        if not isinstance(transactions_payload, dict):
            transactions_payload = {"transactions": []}

        request_rows = requests_payload.get("requests", [])
        transaction_rows = transactions_payload.get("transactions", [])
        if not isinstance(request_rows, list):
            request_rows = []
        if not isinstance(transaction_rows, list):
            transaction_rows = []

        requests = [row for row in request_rows if isinstance(row, dict)]
        transactions = [row for row in transaction_rows if isinstance(row, dict)]
        summary = {
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
        if read_errors:
            summary["live_state_store_read_errors"] = read_errors
        return summary


class CandidateDurableLiveStateStore(FileLiveStateStore):
    """Placeholder for a future durable backend.

    The file behavior remains active so setting SC_STATE_BACKEND early does not
    break beta runtime. Diagnostics make it clear that the selected backend is
    not actually durable until a concrete implementation replaces this stub.
    """

    REQUIRED_ENV_BY_BACKEND = {
        "d1": ["SC_D1_BRIDGE_URL", "SC_D1_BRIDGE_TOKEN"],
        "supabase": ["SC_SUPABASE_URL", "SC_SUPABASE_SERVICE_ROLE_KEY"],
        "neon": ["SC_NEON_DATABASE_URL"],
        "kv": ["SC_KV_NAMESPACE_ID"],
    }

    def __init__(self, base_dir: str, data_dir: str, docs_dir: str, backend: str):
        self.store_type = "file"
        self.state_backend = backend
        self.state_backend_ready = False
        super().__init__(base_dir=base_dir, data_dir=data_dir, docs_dir=docs_dir)

    @property
    def state_backend_detail(self) -> str:
        required = self.REQUIRED_ENV_BY_BACKEND.get(self.state_backend, [])
        missing = _missing_credentials(required)
        if missing:
            return f"{self.state_backend} backend placeholder only; missing env vars: {', '.join(missing)}"
        return f"{self.state_backend} backend placeholder only; no durable adapter implementation is active"

    @property
    def state_backend_warning(self) -> Optional[str]:
        return (
            f"SC_STATE_BACKEND={self.state_backend} is selected, but this checkpoint still falls back to file storage; "
            "live beta writes are not durable until the adapter is implemented"
        )

    def store_diagnostics(self) -> Dict[str, Any]:
        diagnostics = super().store_diagnostics()
        diagnostics.update({
            "state_store_type": self.store_type,
            "state_backend": self.state_backend,
            "state_backend_ready": self.state_backend_ready,
            "state_backend_detail": self.state_backend_detail,
            "fallback_active": True,
        })
        if self.state_backend == "d1":
            diagnostics.update({
                "d1_bridge_configured": False,
                "d1_bridge_url_present": bool(_env_value("SC_D1_BRIDGE_URL")),
            })
        warning = self.state_backend_warning
        if warning:
            diagnostics["state_backend_warning"] = warning
        return diagnostics


class D1BridgeLiveStateStore(FileLiveStateStore):
    """HTTP bridge adapter for Cloudflare D1-owned mutable beta state.

    Render-hosted Flask cannot use Worker D1 bindings directly. This adapter
    talks to a Cloudflare Worker bridge that validates a shared token and owns
    all D1 reads/writes. The bridge is disabled unless SC_STATE_BACKEND=d1 and
    both SC_D1_BRIDGE_URL and SC_D1_BRIDGE_TOKEN are present.
    """

    store_type = "d1_bridge"
    state_backend = "d1"

    RESOURCE_DEFAULTS = {
        "availability": {"months": {}},
        "change_requests": {"requests": []},
        "transactions": {"transactions": []},
        "supervisor_state": {"entries": [], "updated_at": None},
        "schedule_locked": {},
        "assignment_overlays": {"overlays": []},
    }

    def __init__(
        self,
        base_dir: str,
        data_dir: str,
        docs_dir: str,
        bridge_url: Optional[str] = None,
        bridge_token: Optional[str] = None,
        bridge_client: Optional[Callable[[str, str, Optional[Dict[str, Any]]], Dict[str, Any]]] = None,
    ):
        super().__init__(base_dir=base_dir, data_dir=data_dir, docs_dir=docs_dir)
        self.bridge_url = str(bridge_url or _env_value("SC_D1_BRIDGE_URL")).strip().rstrip("/")
        self.bridge_token = str(bridge_token or _env_value("SC_D1_BRIDGE_TOKEN")).strip()
        self.bridge_client = bridge_client
        self.state_backend_ready = bool((self.bridge_url and self.bridge_token) or self.bridge_client)

    @property
    def state_backend_detail(self) -> str:
        if self.bridge_client:
            return "d1 bridge mock client configured for dry-run/testing"
        if self.state_backend_ready:
            return "d1 bridge configured; Flask will call Cloudflare Worker bridge for mutable state"
        missing = _missing_credentials(["SC_D1_BRIDGE_URL", "SC_D1_BRIDGE_TOKEN"])
        return f"d1 bridge not configured; missing env vars: {', '.join(missing)}"

    @property
    def state_backend_warning(self) -> Optional[str]:
        if not self.state_backend_ready:
            return "SC_STATE_BACKEND=d1 is selected, but bridge configuration is incomplete; file fallback is active"
        return None

    @property
    def fallback_active(self) -> bool:
        return not self.state_backend_ready

    def _fallback_or_raise(self, operation: str, fallback: Callable[[], Any]) -> Any:
        if self.fallback_active:
            return fallback()
        raise RuntimeError(f"D1 bridge operation failed: {operation}")

    def _bridge_call(self, resource: str, operation: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.bridge_client:
            result = self.bridge_client(resource, operation, payload)
            return result if isinstance(result, dict) else {}
        if not self.state_backend_ready:
            return {}

        url = f"{self.bridge_url}/api/live-state/{resource}/{operation}"
        body = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.bridge_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = ""
            message = f"HTTP {exc.code}: {exc.reason}"
            if detail:
                message = f"{message}: {detail[:500]}"
            raise RuntimeError(f"D1 bridge request failed for {resource}/{operation}: {message}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"D1 bridge request failed for {resource}/{operation}: {exc}") from exc
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"D1 bridge returned non-JSON response for {resource}/{operation}") from exc
        return parsed if isinstance(parsed, dict) else {}

    def _bridge_read(self, resource: str, fallback: Callable[[], Any]) -> Dict[str, Any]:
        if self.fallback_active:
            return fallback()
        result = self._bridge_call(resource, "read")
        payload = result.get("payload", result.get(resource, result.get("data")))
        if payload is None:
            payload = self.RESOURCE_DEFAULTS.get(resource, {})
        return payload if isinstance(payload, dict) else self.RESOURCE_DEFAULTS.get(resource, {})

    def _bridge_write(self, resource: str, payload: Dict[str, Any], fallback: Callable[[], Any]) -> Dict[str, Any]:
        if self.fallback_active:
            return fallback()
        result = self._bridge_call(resource, "write", {"payload": payload})
        saved = result.get("payload", result.get(resource, result.get("data", payload)))
        return saved if isinstance(saved, dict) else payload

    def load_availability(self) -> Dict[str, Any]:
        return self._bridge_read("availability", super().load_availability)

    def save_availability(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._bridge_write("availability", payload, lambda: FileLiveStateStore.save_availability(self, payload))

    def load_change_requests(self) -> Dict[str, Any]:
        return self._bridge_read("change_requests", super().load_change_requests)

    def save_change_requests(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._bridge_write("change_requests", payload, lambda: FileLiveStateStore.save_change_requests(self, payload))

    def load_beta_transactions(self) -> Dict[str, Any]:
        return self._bridge_read("transactions", super().load_beta_transactions)

    def save_beta_transactions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._bridge_write("transactions", payload, lambda: FileLiveStateStore.save_beta_transactions(self, payload))

    def append_transaction(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        if self.fallback_active:
            return super().append_transaction(transaction)
        result = self._bridge_call("transactions", "append", {"transaction": transaction})
        saved = result.get("transaction", transaction)
        return saved if isinstance(saved, dict) else transaction

    def load_supervisor_state(self) -> Dict[str, Any]:
        return self._bridge_read("supervisor_state", super().load_supervisor_state)

    def save_supervisor_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._bridge_write("supervisor_state", payload, lambda: FileLiveStateStore.save_supervisor_state(self, payload))

    def load_schedule_locked(self) -> Dict[str, Any]:
        return self._bridge_read("schedule_locked", super().load_schedule_locked)

    def save_schedule_locked(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._bridge_write("schedule_locked", payload, lambda: FileLiveStateStore.save_schedule_locked(self, payload))

    def read_assignment_overlays(self) -> Dict[str, Any]:
        return self._bridge_read("assignment_overlays", super().read_assignment_overlays)

    def write_assignment_overlays(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._bridge_write("assignment_overlays", payload, lambda: FileLiveStateStore.write_assignment_overlays(self, payload))

    def store_diagnostics(self) -> Dict[str, Any]:
        diagnostics = super().store_diagnostics()
        diagnostics.update({
            "state_store_type": self.store_type,
            "state_backend": self.state_backend,
            "state_backend_ready": self.state_backend_ready,
            "state_backend_detail": self.state_backend_detail,
            "d1_bridge_configured": self.state_backend_ready,
            "d1_bridge_url": self.bridge_url,
            "d1_bridge_url_present": bool(self.bridge_url),
            "d1_bridge_token_present": bool(self.bridge_token),
            "d1_bridge_token_length": len(self.bridge_token),
            "d1_bridge_token_sha256_first8": _secret_fingerprint(self.bridge_token),
            "fallback_active": self.fallback_active,
        })
        warning = self.state_backend_warning
        if warning:
            diagnostics["state_backend_warning"] = warning
        return diagnostics


def create_live_state_store(base_dir: str, data_dir: str, docs_dir: str) -> FileLiveStateStore:
    requested_backend = _env_value("SC_STATE_BACKEND", "file").lower() or "file"
    if requested_backend not in SUPPORTED_STATE_BACKENDS:
        requested_backend = "file"
    if requested_backend == "file":
        return FileLiveStateStore(base_dir=base_dir, data_dir=data_dir, docs_dir=docs_dir)
    if requested_backend == "d1":
        if _env_value("SC_D1_BRIDGE_URL") and _env_value("SC_D1_BRIDGE_TOKEN"):
            return D1BridgeLiveStateStore(base_dir=base_dir, data_dir=data_dir, docs_dir=docs_dir)
        return CandidateDurableLiveStateStore(
            base_dir=base_dir,
            data_dir=data_dir,
            docs_dir=docs_dir,
            backend=requested_backend,
        )
    return CandidateDurableLiveStateStore(
        base_dir=base_dir,
        data_dir=data_dir,
        docs_dir=docs_dir,
        backend=requested_backend,
    )
