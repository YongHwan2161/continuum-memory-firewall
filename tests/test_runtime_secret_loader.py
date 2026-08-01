import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.load_mcp_secret import (
    _parse_secret,
    _quote_environment_value,
    load_secret,
    write_environment,
)


class RuntimeSecretLoaderTests(unittest.TestCase):
    def payload(self):
        return {
            "database_url": (
                "postgresql://runtime@example.test:26257/continuum"
                "?sslmode=verify-full"
            ),
            "oidc_issuer": "https://issuer.example.test/pool",
            "oidc_required_scope": "continuum/memory.read",
            "bedrock_region": "ap-southeast-1",
            "public_base_url": "https://203-0-113-10.sslip.io/",
            "caller_scopes": {
                "client-a": {
                    "tenant_id": "tenant-a",
                    "incident_id": "incident-a",
                }
            },
        }

    def test_parser_requires_every_string_field(self):
        self.assertEqual(_parse_secret(json.dumps(self.payload())), self.payload())
        for field in self.payload():
            value = self.payload()
            del value[field]
            with self.subTest(field=field):
                with self.assertRaises(RuntimeError):
                    _parse_secret(json.dumps(value))

    def test_environment_quoting_rejects_multiline_values(self):
        self.assertEqual(_quote_environment_value('a"b\\c'), '"a\\"b\\\\c"')
        with self.assertRaises(ValueError):
            _quote_environment_value("line-1\nline-2")

    @patch("scripts.load_mcp_secret.subprocess.run")
    def test_loader_never_places_secret_on_command_line(self, run):
        run.return_value.stdout = json.dumps(self.payload())
        loaded = load_secret(secret_arn="arn:secret", region="ap-southeast-1")
        self.assertEqual(loaded, self.payload())
        command = run.call_args.args[0]
        self.assertNotIn(self.payload()["database_url"], command)
        self.assertNotIn("client-a", command)

    def test_environment_file_contains_only_expected_names(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.env"
            write_environment(path, self.payload())
            text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("CONTINUUM_"), 6)
        self.assertIn("CONTINUUM_CALLER_SCOPES_JSON", text)
        self.assertNotIn("AWS_", text)


if __name__ == "__main__":
    unittest.main()
