import json
from pathlib import Path
from typing import List, Dict
from .models import Member, Unit, Shift, OrgSettings, DisplayTemplate

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read_json(name: str):
    path = DATA_DIR / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_members() -> List[Member]:
    data = _read_json("members.json") or []
    return [Member(**m) for m in data]


def load_units() -> List[Unit]:
    data = _read_json("units.json") or []
    return [Unit(**u) for u in data]


def load_shifts() -> List[Shift]:
    data = _read_json("shifts.json") or []
    return [Shift(**s) for s in data]


def load_org_settings() -> OrgSettings:
    data = _read_json("org_settings.json")
    # convert nested display_templates dicts
    dt = {
        k: DisplayTemplate(**v)
        for k, v in data.get("display_templates", {}).items()
    }
    data["display_templates"] = dt
    return OrgSettings(**data)


def save_org_settings(settings: OrgSettings) -> None:
    path = DATA_DIR / "org_settings.json"
    serializable = {
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
    }
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
