import unittest

from continuum.scope_roles import scope_role_name


class ScopeRoleTests(unittest.TestCase):
    def test_scope_role_is_deterministic_and_bounded(self):
        first = scope_role_name(
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        )
        second = scope_role_name(
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        )
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 63)
        self.assertNotIn("11111111", first)

    def test_scope_role_rejects_non_uuid_scope(self):
        with self.assertRaises(ValueError):
            scope_role_name("tenant", "incident")


if __name__ == "__main__":
    unittest.main()
