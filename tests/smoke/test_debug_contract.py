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
DOCS_DIR = ROOT / "docs"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_debug(name: str):
    return json.loads((DEBUG_DIR / name).read_text(encoding="utf-8"))


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


def ensure_debug_artifacts() -> None:
    required = [
        "latest_run_summary.json",
        "latest_run_supervisor_cards.json",
        "latest_run_full_audit.json",
        "latest_run_failures.json",
    ]
    if all((DEBUG_DIR / name).exists() for name in required):
        return

    data = load_fixture("resolver_base.json")
    apply_shift_date(data, (datetime.now(UTC).date() + timedelta(days=45)).isoformat())
    apply_availability(data, {})
    resolve(copy.deepcopy(data))


class DebugContractTests(unittest.TestCase):
    def setUp(self) -> None:
        if DEBUG_DIR.exists():
            for path in DEBUG_DIR.iterdir():
                if path.is_file():
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass

    def test_debug_artifact_contract_matches_ui_expectations(self) -> None:
        ensure_debug_artifacts()

        summary = load_debug("latest_run_summary.json")
        supervisor_cards = load_debug("latest_run_supervisor_cards.json")
        full_audit = load_debug("latest_run_full_audit.json")
        failures = load_debug("latest_run_failures.json")

        self.assertIsInstance(summary, dict)
        for key in ["generated_at", "shift_count", "seat_count", "fallback_used_count", "later_pass_reviewed_count", "failure_count"]:
            self.assertIn(key, summary)

        self.assertIsInstance(supervisor_cards, list)
        self.assertGreater(len(supervisor_cards), 0)
        for key in ["seat_id", "seat_type", "selected_member_id", "short_explanation", "flags"]:
            self.assertIn(key, supervisor_cards[0])

        self.assertIsInstance(full_audit, dict)
        self.assertIn("seat_audit", full_audit)
        self.assertIsInstance(full_audit["seat_audit"], list)
        self.assertGreater(len(full_audit["seat_audit"]), 0)
        seat = full_audit["seat_audit"][0]
        for key in [
            "seat_id",
            "seat_type",
            "selected_member_id",
            "preserved_existing_assignment",
            "fallback_used",
            "decision_stage",
            "pass_sequence",
            "rotation_status",
            "rotation_score_applied",
            "missing_data_assumptions",
            "fallback_reason",
            "later_pass_reviewed",
            "rejected_candidates",
            "legal_candidates_remaining",
            "short_explanation",
            "long_explanation",
            "flags",
        ]:
            self.assertIn(key, seat)

        self.assertIsInstance(failures, list)

    def test_docs_pages_reference_expected_truth_sources(self) -> None:
        supervisor = (DOCS_DIR / "supervisor.html").read_text(encoding="utf-8")
        member = (DOCS_DIR / "member.html").read_text(encoding="utf-8")
        wallboard = (DOCS_DIR / "wallboard.html").read_text(encoding="utf-8")

        self.assertIn("/api/schedule", supervisor)
        self.assertIn("/api/supervisor/state", supervisor)
        self.assertIn("Open Seats", supervisor)
        self.assertIn('id="actionDiagnostics"', supervisor)
        self.assertIn("updateActionDiagnostics", supervisor)
        self.assertIn('apiPost("/api/build_shifts", {})', supervisor)
        self.assertIn('apiPost("/api/supervisor/resolve_week"', supervisor)
        self.assertIn('apiPost("/api/supervisor/publish_week"', supervisor)
        self.assertIn("No week is selected. Build shift skeletons first.", supervisor)
        self.assertIn('id="quickTestSupervisorBadge"', supervisor)
        self.assertIn("Quick Test Supervisor Mode", supervisor)

        self.assertIn("/api/member/context", member)
        self.assertIn('id="startupLine"', member)
        self.assertIn("FETCH_TIMEOUT_MS", member)
        self.assertIn("startupMessageFor", member)
        self.assertIn('event.target.closest(".state-btn")', member)
        self.assertIn('setStatus(button.dataset.date, button.dataset.shift, button.dataset.value)', member)
        self.assertIn('apiPath("/api/member/availability")', member)
        self.assertIn("dirtyAvailabilityKeys", member)
        self.assertIn("No editable changes to save.", member)
        self.assertIn("DEFAULT_EDITABLE_WEEK_OFFSET = 0", member)
        self.assertIn("VISIBLE_OPERATIONAL_CYCLES = 8", member)
        self.assertIn("OPERATIONAL_CYCLE_START_DAY = 4", member)
        self.assertIn("Copy availability forward", member)
        self.assertIn("applyRepeatForward", member)
        self.assertNotIn("./data/", member)
        self.assertIn("Assigned Shifts", member)

        self.assertIn("/api/schedule", wallboard)
        self.assertIn("/api/wallboard_members", wallboard)
        self.assertNotIn("./data/", wallboard)
        self.assertIn("Here is who is working. Here is what is open.", wallboard)
        self.assertIn("firstFutureAssignedWeekOffset", wallboard)
        self.assertIn("firstVisibleWeekHasAssignedMember", wallboard)

    def test_github_pages_uses_render_api_base_without_breaking_local_dev(self) -> None:
        for name in ["member.html", "supervisor.html", "wallboard.html"]:
            text = (DOCS_DIR / name).read_text(encoding="utf-8")
            self.assertIn('const PUBLIC_API_BASE = "https://shiftcommander-v2.onrender.com";', text)
            self.assertIn('host === "adr-fr.org" || host === "www.adr-fr.org"', text)
            self.assertIn('window.SC_API_BASE_URL || defaultApiBase() || localStorage.getItem("sc_api_base_url") || ""', text)

    def test_public_docs_do_not_contain_git_conflict_markers(self) -> None:
        markers = ["<<<<<<<", "=======", ">>>>>>>", "Updated upstream", "Stashed changes"]
        for name in ["index.html", "member.html", "supervisor.html", "wallboard.html"]:
            text = (DOCS_DIR / name).read_text(encoding="utf-8")
            for marker in markers:
                self.assertNotIn(marker, text, f"{name} contains {marker}")

    def test_render_backend_config_points_at_flask_app(self) -> None:
        render_yaml = (ROOT / "render.yaml").read_text(encoding="utf-8")
        procfile = (ROOT / "Procfile").read_text(encoding="utf-8")
        start_command = "python -m gunicorn server:app --bind 0.0.0.0:$PORT"

        self.assertIn("name: shiftcommander-backend", render_yaml)
        self.assertIn("runtime: python", render_yaml)
        self.assertIn(f"startCommand: {start_command}", render_yaml)
        self.assertIn("healthCheckPath: /api/health", render_yaml)
        self.assertIn("autoDeployTrigger: commit", render_yaml)
        self.assertIn(f"web: {start_command}", procfile)


if __name__ == "__main__":
    unittest.main()
