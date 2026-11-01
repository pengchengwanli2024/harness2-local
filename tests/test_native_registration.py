"""Run the real native-registration script against isolated Codex configuration.

The current Python executable is supplied only as report metadata; the script
never executes that argument. This portable configuration test is not native
desktop acceptance, which runs separately in a private live verification script.
No Codex process, model, service, real credential file or live fixture is used.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/harness2-local"
SCRIPT = PLUGIN / "scripts/register_native_mcp.py"
METADATA_EXECUTABLE = Path(sys.executable).resolve()

FOREIGN = '''# Existing user configuration: preserve comments and unknown fields verbatim.
model = "existing-user-choice"
future_feature = { preserve = true, order = ["z", "a"] }

[mcp_servers.foreign_stdio]
type = "stdio" # This field was lost by CLI reserialization.
command = "/fixture/foreign-server"
args = ["--transport", "stdio", "argument with spaces"]
env = { CASE_SENTINEL = "fixture-only", FUTURE_ENV = "keep-me" }
future_transport_option = { retries = 3, preserve = true }

[mcp_servers.foreign_http]
type = "http"
url = "https://invalid.example.test/mcp"
future_unknown = "keep this exact field"
'''.replace("\n", "\r\n").encode()


def inventory(root):
    return {path.relative_to(root).as_posix():
            ("directory" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(root.rglob("*"))}


class NativeRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(METADATA_EXECUTABLE.is_file(), "Use the real Python executable as report metadata")
        self.assertTrue(os.access(METADATA_EXECUTABLE, os.X_OK))
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-native-registration-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "isolated-codex-home"
        self.home.mkdir()
        self.config = self.home / "config.toml"
        self.evidence = self.base / "script-evidence"
        self.business = self.base / "business-project"
        self.business.mkdir()
        (self.business / "only-allowed-file.txt").write_bytes(b"Business file must stay exactly as supplied.\n")
        (self.business / "strict-sentinel").mkdir()
        (self.business / "strict-sentinel/no-touch.bin").write_bytes(bytes(range(256)))
        self.expected = {"command": shutil.which("python3"),
                         "args": [str(PLUGIN.resolve() / "server/harness2_local.py"), "--stdio"]}

    def run_script(self, apply=True, approve_tools=()):
        command = [sys.executable, str(SCRIPT), "--codex-bin", str(METADATA_EXECUTABLE),
                   "--evidence-dir", str(self.evidence)]
        if apply:
            command.append("--apply")
        if approve_tools:
            command += ["--approve-tools", *approve_tools]
        return subprocess.run(command, cwd=self.business,
                              env={**os.environ, "CODEX_HOME": str(self.home),
                                   "PYTHONDONTWRITEBYTECODE": "1"},
                              text=True, capture_output=True, timeout=20)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["codex_binary"], str(METADATA_EXECUTABLE.resolve()))
        self.assertEqual(report["desired"], self.expected)
        return report

    def owned(self, extra=""):
        return ('[mcp_servers."harness2-local"]\n'
                + "command = " + json.dumps(self.expected["command"]) + "\n"
                + "args = " + json.dumps(self.expected["args"]) + "\n" + extra).encode()

    def test_append_preserves_foreign_mcp_unknown_fields_comments_and_original_byte_prefix(self):
        self.config.write_bytes(FOREIGN)
        self.config.chmod(0o640)
        before = tomllib.loads(FOREIGN.decode())
        report = self.assert_success(self.run_script())
        updated = self.config.read_bytes()
        self.assertTrue(updated.startswith(FOREIGN))
        after = tomllib.loads(updated.decode())
        native = after["mcp_servers"].pop("harness2-local")
        self.assertEqual(native, self.expected)
        self.assertEqual(after, before)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        self.assertTrue(report["original_bytes_preserved"])
        self.assertTrue(report["unrelated_config_preserved"])
        self.assertEqual(Path(report["backup"]).read_bytes(), FOREIGN)

    def test_auth_is_not_read_or_changed_and_business_tree_has_no_new_files(self):
        self.config.write_bytes(FOREIGN)
        auth = self.home / "auth.json"
        auth_bytes = b'{"fixture":"unreadable noncredential sentinel"}\n'
        auth.write_bytes(auth_bytes)
        auth.chmod(0o000)
        self.addCleanup(auth.chmod, 0o600)
        business_before = inventory(self.business)
        self.assert_success(self.run_script())
        self.assertEqual(auth.stat().st_mode & 0o777, 0o000)
        auth.chmod(0o600)
        self.assertEqual(auth.read_bytes(), auth_bytes)
        self.assertEqual(inventory(self.business), business_before)
        self.assertEqual(sorted(path.name for path in self.home.iterdir()),
                         ["auth.json", "backups", "config.toml"])

    def test_dry_run_never_creates_or_changes_config(self):
        for present in (False, True):
            with self.subTest(config_present=present):
                if present:
                    self.config.write_bytes(FOREIGN)
                before = inventory(self.home)
                report = self.assert_success(self.run_script(apply=False))
                self.assertFalse(report["applied"])
                self.assertEqual(inventory(self.home), before)
                self.assertTrue((self.evidence / "native-mcp.candidate.json").is_file())

    def test_same_name_foreign_command_is_rejected_without_config_changes(self):
        raw = FOREIGN + b'\n[mcp_servers."harness2-local"]\ncommand = "/foreign/owned"\nargs = ["--stay"]\n'
        self.config.write_bytes(raw)
        before = inventory(self.home)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.config.read_bytes(), raw)
        self.assertEqual(inventory(self.home), before)

    def test_same_owned_command_and_args_are_byte_identical_and_idempotent(self):
        raw = FOREIGN + b"\n" + self.owned('# keep owned local options\nenabled = true\nfuture_owned = "keep"\n')
        self.config.write_bytes(raw)
        before = inventory(self.home)
        for _ in range(2):
            report = self.assert_success(self.run_script())
            self.assertTrue(report["already_current"])
            self.assertEqual(self.config.read_bytes(), raw)
            self.assertEqual(inventory(self.home), before)

    def test_explicit_named_trust_is_append_only_scoped_and_idempotent(self):
        raw = FOREIGN + b"\n" + self.owned('future_owned = "preserve"\n')
        self.config.write_bytes(raw)
        report = self.assert_success(self.run_script(approve_tools=("h2_context", "h2_assess")))
        updated = self.config.read_bytes()
        self.assertTrue(updated.startswith(raw))
        after = tomllib.loads(updated.decode())
        owned = after["mcp_servers"].pop("harness2-local")
        self.assertEqual(owned.pop("tools"), {"h2_context": {"approval_mode": "approve"},
                                              "h2_assess": {"approval_mode": "approve"}})
        self.assertEqual(owned, {**self.expected, "future_owned": "preserve"})
        self.assertEqual(after, tomllib.loads(FOREIGN.decode()))
        self.assertEqual(report["explicitly_approved_tools"], ["h2_assess", "h2_context"])
        again = self.assert_success(self.run_script(approve_tools=("h2_context", "h2_assess")))
        self.assertTrue(again["already_current"])
        self.assertEqual(self.config.read_bytes(), updated)

    def test_existing_explicit_tool_policy_is_never_overridden(self):
        for policy in ('approval_mode = "prompt"', 'approval_mode = "auto"', 'output_token_limit = 100'):
            with self.subTest(policy=policy):
                raw = FOREIGN + b"\n" + self.owned() + ('\n[mcp_servers."harness2-local".tools.h2_context]\n' + policy + '\n').encode()
                self.config.write_bytes(raw)
                before = inventory(self.home)
                result = self.run_script(approve_tools=("h2_context",))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(inventory(self.home), before)

    def test_trust_dry_run_changes_no_policy_or_business_file(self):
        self.config.write_bytes(FOREIGN)
        before = inventory(self.home)
        business_before = inventory(self.business)
        report = self.assert_success(self.run_script(apply=False, approve_tools=("h2_context",)))
        self.assertEqual(report["explicitly_approved_tools"], ["h2_context"])
        self.assertEqual(inventory(self.home), before)
        self.assertEqual(inventory(self.business), business_before)

    def test_new_native_config_is_valid_toml_and_second_apply_does_not_rewrite(self):
        report = self.assert_success(self.run_script())
        raw = self.config.read_bytes()
        self.assertEqual(tomllib.loads(raw.decode()), {"mcp_servers": {"harness2-local": self.expected}})
        self.assertEqual(Path(report["backup"]).read_bytes(), b"")
        before = inventory(self.home)
        again = self.assert_success(self.run_script())
        self.assertTrue(again["already_current"])
        self.assertEqual(inventory(self.home), before)

    def test_managed_config_symlink_is_rejected_without_replacing_link_or_target(self):
        target = self.base / "managed-config-source.toml"
        target.write_bytes(FOREIGN)
        self.config.symlink_to(target)
        for apply in (False, True):
            with self.subTest(apply=apply):
                result = self.run_script(apply=apply)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(self.config.is_symlink())
                self.assertEqual(os.readlink(self.config), str(target))
                self.assertEqual(target.read_bytes(), FOREIGN)
                self.assertEqual(sorted(path.name for path in self.home.iterdir()), ["config.toml"])
                self.assertFalse(self.evidence.exists())

    def test_owned_command_with_conflicting_transport_fields_is_rejected_unchanged(self):
        conflicts = ('type = "http"\n', 'type = "sse"\n',
                     'url = "https://invalid.example.test/mcp"\n',
                     'server_url = "https://invalid.example.test/mcp"\n',
                     'bearer_token_env_var = "FIXTURE_TOKEN_ENV_NAME"\n')
        for extra in conflicts:
            with self.subTest(extra=extra):
                raw = FOREIGN + b"\n" + self.owned(extra)
                self.config.write_bytes(raw)
                before = inventory(self.home)
                result = self.run_script()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.config.read_bytes(), raw)
                self.assertEqual(inventory(self.home), before)
                self.assertFalse(self.evidence.exists())
        compatible = FOREIGN + b"\n" + self.owned('type = "stdio"\n')
        self.config.write_bytes(compatible)
        self.assertTrue(self.assert_success(self.run_script())["already_current"])
        self.assertEqual(self.config.read_bytes(), compatible)

    def test_config_changed_during_real_fsync_is_retained_and_never_replaced(self):
        spec = importlib.util.spec_from_file_location("h2_native_registration_under_test", SCRIPT)
        registration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(registration)
        self.config.write_bytes(FOREIGN)
        concurrent = FOREIGN + b'\nconcurrently_added_field = "must survive"\n'
        real_fsync = os.fsync
        real_replace = os.replace

        def fsync_then_another_writer_changes_config(descriptor):
            real_fsync(descriptor)
            self.config.write_bytes(concurrent)

        arguments = [str(SCRIPT), "--codex-bin", str(METADATA_EXECUTABLE),
                     "--evidence-dir", str(self.evidence), "--apply"]
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}), \
             patch.object(sys, "argv", arguments), \
             patch.object(registration.os, "fsync", side_effect=fsync_then_another_writer_changes_config) as sync, \
             patch.object(registration.os, "replace", wraps=real_replace) as replace:
            with self.assertRaises(RuntimeError):
                registration.main()
            sync.assert_called_once()
            replace.assert_not_called()
        self.assertEqual(self.config.read_bytes(), concurrent)
        self.assertNotIn("harness2-local", tomllib.loads(concurrent.decode())["mcp_servers"])
        self.assertEqual(list(self.home.glob(".h2-native-mcp-*")), [])
        backups = list((self.home / "backups").glob("*/config.toml.before"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), FOREIGN)


if __name__ == "__main__":
    unittest.main()
