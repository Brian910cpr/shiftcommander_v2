from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Member:
    id: str
    first_name: str
    last_name: str
    member_number: str
    position_type: str  # FT | PT | VOL
    expected_min_hours: float
    expected_max_hours: float
    qualifications: List[str] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    active: bool = True
    points_balance: float = 0.0


@dataclass
class Unit:
    id: str
    name: str
    type: str  # e.g. "Ambulance", "Engine"
    default_order: int  # default rotation order (1 = first-out)
    in_service: bool = True
    notes: str = ""


@dataclass
class Shift:
    id: str
    date: str       # YYYY-MM-DD
    start: str      # HH:MM (24h)
    end: str        # HH:MM
    unit_id: str
    required_quals: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)  # weekend, overnight, unpopular
    assigned_member_ids: List[str] = field(default_factory=list)
    override_first_out_unit: Optional[str] = None  # manual 1st-out override for this shift


@dataclass
class DisplayTemplate:
    # pattern examples:
    # "INITIALS_NUMBER", "INITIALS", "NUMBER",
    # "FIRST_LAST_NUMBER", "FIRST_NUMBER", "LAST_NUMBER",
    # "FIRST", "LAST"
    pattern: str
    show_badges: bool = True


@dataclass
class OrgSettings:
    id: str
    name: str
    self_scheduling_enabled: bool
    ft_default_range: Dict[str, float]
    pt_default_range: Dict[str, float]
    vol_default_range: Dict[str, float]
    rotation_order: List[str]  # list of unit IDs defining default first-out order
    display_templates: Dict[str, DisplayTemplate]  # keys: public, member, manager, admin


@dataclass
class Assignment:
    shift_id: str
    member_id: str
    points_earned: float
    breakdown: Dict[str, float]
