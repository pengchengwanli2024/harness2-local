"""Session-gate configuration safety tests, never native/model acceptance.

Run the actual script using temporary CODEX_HOME and business directories.
Only the concurrency test imports the real module, to inject a second writer
during an otherwise real fsync without touching live configuration or policies.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/harness2-local/scripts/configure_session_gate.py"
BEGIN = "# BEGIN HARNESS2_DEVELOPER_GATE v1"
END = "# END HARNESS2_DEVELOPER_GATE"
FOREIGN = '''# Preserve this unrelated source byte-for-byte, including CRLF and comments.
model = "existing-user-model"
unrelated_private_fixture = "do-not-copy-full-config-to-preview"
future_setting = { retain = true, order = ["z", "a"] }

[mcp_servers.foreign]
type = "stdio" # Preserve fields the CLI may not understand.
command = "/fixture/foreign-server"
args = ["--keep", "argument with spaces"]
env = { FIXTURE_ENV = "keep" }
future_option = { keep = true }
'''.replace("\n", "\r\n").encode()


def inventory(root):
    return {path.relative_to(root).as_posix():
            ("directory" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(root.rglob("*"))}


class SessionGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-session-gate-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "isolated-codex-home"
        self.home.mkdir()
        self.config = self.home / "config.toml"
        self.evidence = self.base / "gate-evidence"
        self.business = self.base / "business-project"
        self.business.mkdir()
        (self.business / "strict-sentinel.txt").write_bytes(b"No business file changes authorized.\n")

    def run_script(self, apply=False):
        args = [sys.executable, str(SCRIPT), "--evidence-dir", str(self.evidence)]
        if apply:
            args.append("--apply")
        return subprocess.run(args, cwd=self.business,
                              env={**os.environ, "CODEX_HOME": str(self.home),
                                   "PYTHONDONTWRITEBYTECODE": "1"},
                              text=True, capture_output=True, timeout=20)

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_installed(self, original):
        raw = self.config.read_bytes()
        self.assertTrue(raw.startswith(BEGIN.encode()))
        self.assertTrue(raw.endswith(original))
        self.assertEqual(raw.count(BEGIN.encode()), 1)
        self.assertEqual(raw.count(END.encode()), 1)
        parsed = tomllib.loads(raw.decode())
        instructions = parsed.pop("developer_instructions")
        self.assertEqual(instructions.strip(),
                         (self.evidence / "developer-gate.candidate.md").read_text().strip())
        self.assertTrue(instructions.strip())
        self.assertEqual(parsed, tomllib.loads(original.decode()))

    def test_dry_run_with_absent_or_existing_config_never_writes_home_or_business(self):
        for present in (False, True):
            with self.subTest(present=present):
                if present:
                    self.config.write_bytes(FOREIGN)
                before = inventory(self.home)
                business_before = inventory(self.business)
                report = self.success(self.run_script())
                self.assertFalse(report["applied"])
                self.assertEqual(inventory(self.home), before)
                self.assertEqual(inventory(self.business), business_before)
                self.assertEqual(sorted(path.name for path in self.evidence.iterdir()),
                                 ["developer-gate.candidate.md", "session-gate-install.json"])
                for path in self.evidence.iterdir():
                    self.assertNotIn("do-not-copy-full-config-to-preview", path.read_text())

    def test_apply_prepends_owned_gate_preserving_foreign_suffix_values_and_permissions(self):
        self.config.write_bytes(FOREIGN)
        self.config.chmod(0o640)
        business_before = inventory(self.business)
        report = self.success(self.run_script(apply=True))
        self.assertTrue(report["applied"])
        self.assertTrue(report["unrelated_config_preserved"])
        self.assertEqual(Path(report["backup"]).read_bytes(), FOREIGN)
        self.assertEqual(report["config_sha256"], hashlib.sha256(self.config.read_bytes()).hexdigest())
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        self.assert_installed(FOREIGN)
        self.assertEqual(inventory(self.business), business_before)

    def test_unowned_developer_instructions_and_managed_symlink_are_rejected(self):
        for instructions in ("Existing owner's developer policy", ""):
            with self.subTest(instructions=instructions):
                raw = ("developer_instructions = " + json.dumps(instructions) + "\n").encode() + FOREIGN
                self.config.write_bytes(raw)
                before = inventory(self.home)
                result = self.run_script(apply=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(inventory(self.home), before)
        self.config.unlink()
        managed = self.base / "managed-config-source.toml"
        managed.write_bytes(FOREIGN)
        self.config.symlink_to(managed)
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.config.is_symlink())
        self.assertEqual(os.readlink(self.config), str(managed))
        self.assertEqual(managed.read_bytes(), FOREIGN)

    def test_repeated_apply_of_owned_value_is_byte_identical_and_creates_no_extra_backup(self):
        self.config.write_bytes(FOREIGN)
        self.success(self.run_script(apply=True))
        self.assert_installed(FOREIGN)
        before = inventory(self.home)
        for _ in range(2):
            report = self.success(self.run_script(apply=True))
            self.assertTrue(report["applied"])
            self.assertTrue(report["already_current"])
            self.assertEqual(inventory(self.home), before)

    def test_existing_owned_gate_can_update_without_changing_foreign_config(self):
        old_gate = (BEGIN + "\ndeveloper_instructions = "
                    + json.dumps("Earlier owned gate: deterministic test fixture.")
                    + "\n" + END + "\n").encode()
        original = old_gate + FOREIGN
        self.config.write_bytes(original)
        report = self.success(self.run_script(apply=True))
        self.assertTrue(report["unrelated_config_preserved"])
        self.assertEqual(Path(report["backup"]).read_bytes(), original)
        self.assert_installed(FOREIGN)
        self.assertNotIn(b"Earlier owned gate: deterministic test fixture.", self.config.read_bytes())

    def test_concurrent_config_change_during_fsync_is_preserved_without_replace(self):
        spec = importlib.util.spec_from_file_location("h2_session_gate_under_test", SCRIPT)
        registration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(registration)
        self.config.write_bytes(FOREIGN)
        concurrent = FOREIGN + b'\nconcurrent_writer_field = "must survive"\n'
        real_fsync, real_replace = os.fsync, os.replace

        def fsync_then_concurrent_edit(descriptor):
            real_fsync(descriptor)
            self.config.write_bytes(concurrent)

        args = [str(SCRIPT), "--evidence-dir", str(self.evidence), "--apply"]
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}), \
             patch.object(sys, "argv", args), \
             patch.object(registration.os, "fsync", side_effect=fsync_then_concurrent_edit) as sync, \
             patch.object(registration.os, "replace", wraps=real_replace) as replace:
            with self.assertRaises((RuntimeError, SystemExit)):
                registration.main()
            self.assertTrue(sync.called)
            replace.assert_not_called()
        self.assertEqual(self.config.read_bytes(), concurrent)
        self.assertNotIn("developer_instructions", tomllib.loads(concurrent.decode()))


if __name__ == "__main__":
    unittest.main()
