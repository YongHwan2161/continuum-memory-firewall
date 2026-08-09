import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from continuum.blind_holdout import canonical_json_bytes
from scripts.run_live_blind_holdout import _load, _write_canonical


class BlindHoldoutRunnerCodecTests(unittest.TestCase):
    def test_candidate_writer_matches_evaluator_canonical_codec(self) -> None:
        value = {
            "kind": "continuum.blind-holdout.observations",
            "observations": [{"case_id": "case-1", "latency_ms": 1.25}],
            "schema_version": 1,
        }
        with TemporaryDirectory() as directory:
            path = Path(directory, "observations.json")
            _write_canonical(path, value)

            self.assertEqual(path.read_bytes(), canonical_json_bytes(value))
            self.assertEqual(_load(path), value)

    def test_candidate_loader_rejects_pretty_printed_observations(self) -> None:
        value = {"kind": "continuum.blind-holdout.observations"}
        with TemporaryDirectory() as directory:
            path = Path(directory, "observations.json")
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "not canonical JSON"):
                _load(path)


if __name__ == "__main__":
    unittest.main()
