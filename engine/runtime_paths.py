"""Opt-in private pilot paths; ordinary deployments retain their existing paths."""

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def private_pilot_root():
    raw = os.environ.get("SC_PRIVATE_PILOT_ROOT", "")
    if not raw:
        return None
    root = Path(raw)
    if not root.is_absolute():
        raise ValueError("Private pilot root must be an existing absolute directory")
    root = root.resolve()
    if (not root.is_dir() or root == root.parent or REPO_ROOT.is_relative_to(root)
            or any((parent / ".git").exists() for parent in (root, *root.parents))):
        raise ValueError("Private pilot root must be outside Git checkouts")
    # Validate existing links before any runtime reads/writes. Restrict filesystem
    # ownership separately: this is not a sandbox against a hostile local user.
    for child in root.rglob("*"):
        if not child.resolve().is_relative_to(root):
            raise ValueError("Private pilot paths must remain inside their root")
    return root


def runtime_paths():
    root = private_pilot_root()
    return {
        "pilot_root": root,
        "data": (root or REPO_ROOT) / "data",
        "public": root / "public" if root else REPO_ROOT / "docs",
        "debug": (root or REPO_ROOT) / "debug",
    }


def validate_pilot_environment(root):
    """Reject unsafe inherited configuration before constructing storage."""
    if root is None:
        return
    allowed = {
        "SC_PRIVATE_PILOT_ROOT", "SC_AUTH_DB_PATH", "SC_STATE_BACKEND",
        "SC_QUICK_TEST_MODE", "SC_DEMO_SUPERVISOR_BYPASS", "SC_PUBLIC_BASE_URL",
        "SC_ALLOWED_ORIGINS", "SC_ALLOWED_ORIGIN_SUFFIXES",
    }
    if any(key.startswith("SC_") and value and key not in allowed
           for key, value in os.environ.items()):
        raise ValueError("Private pilot refuses unapproved inherited SC configuration")
    if os.environ.get("SC_STATE_BACKEND") != "file":
        raise ValueError("Private pilot requires isolated file state")
    if any(os.environ.get(key, "").lower() != "false" for key in (
            "SC_QUICK_TEST_MODE", "SC_DEMO_SUPERVISOR_BYPASS")):
        raise ValueError("Private pilot requires explicitly disabled development authentication")
    auth_path = Path(os.environ.get("SC_AUTH_DB_PATH", ""))
    if not auth_path.is_absolute() or auth_path.resolve() != root / "auth.sqlite3":
        raise ValueError("Private pilot requires its own auth store")
