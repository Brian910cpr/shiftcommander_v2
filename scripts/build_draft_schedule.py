
from server import build_schedule
import sys

month = sys.argv[1] if len(sys.argv) > 1 else None
payload = build_schedule(month)
print(f"Schedule created for {payload['meta']['month']} at docs/data/schedule.json")
