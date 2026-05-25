import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_server_module():
    spec = importlib.util.spec_from_file_location("shiftcommander_server_ncld_profile", ROOT / "server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NcldProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()

    def test_normalize_member_marks_ncld_as_lowest_medical_cert(self):
        payload = self.server.normalize_members_payload({
            "members": [{
                "member_id": "n1",
                "name": "NCLD Member",
                "ops_cert": "NCLD",
                "can_attend": True,
            }]
        })
        member = payload["members"][0]

        self.assertTrue(member["ncld_status"])
        self.assertEqual(member["ncld_interest_level"], "unknown")
        self.assertEqual(member["medical_cert"], "NCLD")
        self.assertEqual(member["medical_cert_rank"], 0)
        self.assertEqual(member["medical_cert_label"], "Non-Certified, Licensed Driver (NCLD)")
        self.assertNotIn("clinical_staffing_category", member)
        self.assertNotIn("support_role_category", member)

    def test_profile_update_keeps_ncld_interest_editable(self):
        member = {"member_id": "n1", "name": "NCLD Member", "ops_cert": "NCLD"}

        self.server.apply_member_profile_update(member, {
            "ncld_status": True,
            "ncld_interest_level": "interested",
            "ncld_notes": "Wants support/driver opportunities.",
            "last_interest_update": "2026-05-25",
        })

        self.assertTrue(member["ncld_status"])
        self.assertEqual(member["ncld_interest_level"], "interested")
        self.assertEqual(member["ncld_notes"], "Wants support/driver opportunities.")
        self.assertEqual(member["last_interest_update"], "2026-05-25")
        self.assertEqual(member["medical_cert"], "NCLD")
        self.assertEqual(member["medical_cert_rank"], 0)

    def test_profile_update_accepts_ncld_as_medical_cert_value(self):
        member = {"member_id": "n1", "name": "NCLD Member", "ops_cert": "EMR"}

        self.server.apply_member_profile_update(member, {"medical_cert": "NCLD"})

        self.assertEqual(member["medical_cert"], "NCLD")
        self.assertEqual(member["ops_cert"], "NCLD")
        self.assertEqual(member["cert"], "NCLD")
        self.assertEqual(member["medical_cert_rank"], 0)
        self.assertTrue(member["ncld_status"])

    def test_profile_update_rejects_unknown_interest_level(self):
        with self.assertRaises(ValueError):
            self.server.apply_member_profile_update(
                {"member_id": "n1", "name": "NCLD Member", "ops_cert": "NCLD"},
                {"ncld_interest_level": "promote_to_attendant"},
            )


if __name__ == "__main__":
    unittest.main()
