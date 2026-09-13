"""Synthetic loopback-only process fixture, never an operational launcher."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import server
from werkzeug.serving import make_server
from test_serving_auth_safeguards import FixtureClock

server.load_members = lambda: [
    {"member_id": "fixture-member", "name": "Fixture Member", "active": True},
    {"member_id": "fixture-supervisor", "name": "Fixture Supervisor", "active": True, "role": "supervisor"},
]
server.load_members_payload = lambda: {"members": server.load_members()}
server.datetime = FixtureClock
with patch("urllib.request.urlopen", side_effect=AssertionError("External network forbidden")), \
     patch("engine.resolver.datetime", FixtureClock), \
     patch("engine.schedule_lifecycle.datetime", FixtureClock):
    httpd = make_server("127.0.0.1", 0, server.app)
    print(json.dumps({"port": httpd.server_port}), flush=True)
    httpd.serve_forever()
