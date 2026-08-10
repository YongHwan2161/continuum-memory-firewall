import unittest

from continuum.ci_recovery import CI_RECOVERY_FAMILIES, build_ci_recovery_cases
from scripts.ci_recovery_fixture import run_fixture


class CIRecoveryFixtureTests(unittest.TestCase):
    def test_every_family_is_red_without_fix_and_green_only_with_its_fix(self) -> None:
        cases = build_ci_recovery_cases()
        for family in CI_RECOVERY_FAMILIES:
            case = next(item for item in cases if item.family == family.family)
            with self.subTest(family=family.family, phase="baseline"):
                baseline, _ = run_fixture(case_id=case.case_id, patch_id="no_patch")
                self.assertFalse(baseline["exercise_passed"])
                self.assertEqual(baseline["cleanup_residual_count"], 0)
            with self.subTest(family=family.family, phase="wrong"):
                wrong, _ = run_fixture(
                    case_id=case.case_id, patch_id=family.wrong_patch_id
                )
                self.assertFalse(wrong["exercise_passed"])
            with self.subTest(family=family.family, phase="green"):
                green, _ = run_fixture(
                    case_id=case.case_id, patch_id=family.expected_patch_id
                )
                self.assertTrue(green["exercise_passed"])
                self.assertFalse(green["repository_mutation"])


if __name__ == "__main__":
    unittest.main()
