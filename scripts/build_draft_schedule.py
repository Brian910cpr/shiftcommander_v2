import json
import sys
import calendar
import random
from datetime import datetime, timedelta

MEMBERS_FILE = "data/members.json"
OUTPUT_FILE = "docs/data/schedule.json"


def load_members():
    with open(MEMBERS_FILE, "r") as f:
        return json.load(f)


def get_month_range():

    if len(sys.argv) < 2:
        print("Usage: python build_draft_schedule.py YYYY-MM")
        sys.exit(1)

    year, month = map(int, sys.argv[1].split("-"))

    first_day = datetime(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]

    return first_day, days_in_month, year, month


def generate_schedule():

    members = load_members()
    first_day, days_in_month, year, month = get_month_range()

    schedule = {}

    for i in range(days_in_month):

        date = first_day + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")

        am = random.sample(members, 2)
        pm = random.sample(members, 2)

        schedule[date_str] = {
            "AM": am,
            "PM": pm
        }

    output = {
        "meta": {
            "month": f"{year}-{month:02d}",
            "generated_at": datetime.now().isoformat()
        },
        "schedule": schedule
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Schedule written to {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_schedule()