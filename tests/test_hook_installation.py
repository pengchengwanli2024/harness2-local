"""Isolated real installer tests; native inventory is explicitly mocked for trust tests.

No desktop host, model, real hooks or account configuration is invoked. Copied
installer/gate/engine sources freeze the fixture independently of peer edits.
"""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/harness2-local"
PREFIX = "Harness2 forced assessment"
EVENTS = {"UserPromptSubmit": "user_prompt_submit", "PreToolUse": "pre_tool_use",
          "PostToolUse": "post_tool_use", "Stop": "stop"}
CONFIG = b'''# Preserve unrelated bytes, comments, fields and trust.
model = "fixture-user-model"
unrelated_fixture = "not-for-public-preview"
future_timestamp = 1979-05-27T07:32:00Z
[hooks.state."cognee-fixture:stop:0:0"]
enabled = true
trusted_hash = "sha256:unrelated-declaration"
trusted_content_hash = "sha256:unrelated-contents"
[mcp_servers.foreign]
type = "stdio"
command = "/fixture/foreign"
args = ["--keep"]
future_field = { keep = true }
'''.replace(b"\n", b"\r\n")
HOOKS = {"future_top_level": {"preserve": True}, "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "echo fixture-stop-0"},
                         {"type": "command", "command": "echo fixture-stop-1"}]}],
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo foreign-pre"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo foreign-prompt"}]}]}}


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[key] = ("link", os.readlink(path))
        elif path.is_dir():
            result[key] = ("dir", path.stat().st_mode & 0o777)
        else:
            result[key] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode & 0o777)
    return result


class HookInstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-hook-install-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.plugin = self.base / "source-plugin"
        for name in ("scripts/configure_forced_hooks.py", "hooks/gate.py", "server/harness2_local.py"):
            destination = self.plugin / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PLUGIN / name, destination)
        self.script = self.plugin / "scripts/configure_forced_hooks.py"
        self.home = self.base / "codex-home"
        self.home.mkdir()
        self.evidence = self.base / "evidence"
        self.business = self.base / "business"
        self.business.mkdir()
        (self.business / "strict-sentinel.txt").write_bytes(b"Only approved business edits may touch this.\n")
        self.config = self.home / "config.toml"
        self.hooks = self.home / "hooks.json"
        self.config.write_bytes(CONFIG)
        self.hooks.write_text(json.dumps(HOOKS, indent=4) + "\n")

    def run_script(self, apply=False, trust=False):
        args = [sys.executable, str(self.script), "--codex-bin", sys.executable,
                "--evidence-dir", str(self.evidence)]
        if apply:
            args.append("--apply")
        if trust:
            args.append("--trust")
        return subprocess.run(args, cwd=self.business, env={**os.environ, "CODEX_HOME": str(self.home),
                              "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, timeout=25)

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def module(self):
        spec = importlib.util.spec_from_file_location("h2_hook_installer_under_test", self.script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def invoke(self, module, trust=True):
        args = [str(self.script), "--codex-bin", sys.executable,
                "--evidence-dir", str(self.evidence), "--apply"]
        if trust:
            args.append("--trust")
        output = io.StringIO()
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}), patch.object(sys, "argv", args), \
             contextlib.redirect_stdout(output):
            module.main()
        return json.loads(output.getvalue())

    def own_inventory(self, trusted=False):
        result = []
        for event, groups in json.loads(self.hooks.read_bytes())["hooks"].items():
            for gi, group in enumerate(groups):
                for hi, handler in enumerate(group["hooks"]):
                    if handler.get("statusMessage", "").startswith(PREFIX):
                        result.append({"key": f"{self.hooks}:{EVENTS[event]}:{gi}:{hi}",
                            "eventName": event[0].lower() + event[1:], "source": "user",
                            "sourcePath": str(self.hooks), "handlerType": "command",
                            "command": handler["command"], "enabled": True,
                            "currentHash": "sha256:" + hashlib.sha256(json.dumps(handler, sort_keys=True).encode()).hexdigest(),
                            "trustStatus": "trusted" if trusted else "untrusted"})
        return result

    def test_preview_writes_only_own_evidence_and_never_codex_home_or_business(self):
        before, business = inventory(self.home), inventory(self.business)
        report = self.success(self.run_script())
        self.assertFalse(report["applied"])
        self.assertFalse(report["verified_active"])
        self.assertEqual(inventory(self.home), before)
        self.assertEqual(inventory(self.business), business)
        self.assertEqual(sorted(path.name for path in self.evidence.iterdir()),
                         ["forced-hooks-install.json", "forced-hooks.candidate.json"])
        for path in self.evidence.iterdir():
            self.assertNotIn("not-for-public-preview", path.read_text())
            self.assertNotIn("fixture-stop-0", path.read_text())

    def test_apply_without_trust_preserves_foreign_handlers_indices_and_config_bytes(self):
        self.hooks.chmod(0o640)
        business = inventory(self.business)
        report = self.success(self.run_script(apply=True))
        self.assertTrue(report["applied"])
        self.assertFalse(report["verified_active"])
        self.assertFalse(report["trust_requested"])
        self.assertEqual(self.config.read_bytes(), CONFIG)
        self.assertEqual(self.hooks.stat().st_mode & 0o777, 0o640)
        updated = json.loads(self.hooks.read_bytes())
        self.assertEqual(updated["future_top_level"], HOOKS["future_top_level"])
        for event, groups in HOOKS["hooks"].items():
            self.assertEqual(updated["hooks"][event][:len(groups)], groups)
        self.assertEqual(len(self.own_inventory()), 4)
        for event, groups in updated["hooks"].items():
            own = [group for group in groups if any(h.get("statusMessage", "").startswith(PREFIX) for h in group["hooks"])]
            self.assertEqual(len(own), 1)
            handler = own[0]["hooks"][0]
            self.assertFalse(handler["async"])
            if event in ("PreToolUse", "PostToolUse"):
                self.assertEqual(own[0]["matcher"], ".*")
            command = shlex.split(handler["command"])
            self.assertEqual(command[0], str(Path(sys.executable).resolve()))
            self.assertEqual(command[2::2], ["--expect-self-sha", "--expect-engine-sha"])
            self.assertEqual(command[3], report["runtime_hashes"]["gate.py"])
            self.assertEqual(command[5], report["runtime_hashes"]["harness2_local.py"])
        folder = Path(report["runtime"])
        self.assertEqual({path.name for path in folder.iterdir()}, {"gate.py", "harness2_local.py"})
        self.assertEqual((folder / "gate.py").read_bytes(), (self.plugin / "hooks/gate.py").read_bytes())
        self.assertEqual((folder / "harness2_local.py").read_bytes(), (self.plugin / "server/harness2_local.py").read_bytes())
        self.assertEqual(inventory(self.business), business)
        self.assertTrue(all(Path(path).stat().st_mode & 0o777 == 0o600 for path in report["backups"]))

    def test_repeated_apply_is_byte_identical_and_does_not_duplicate_handlers_or_backups(self):
        self.success(self.run_script(apply=True))
        before = inventory(self.home)
        self.success(self.run_script(apply=True))
        self.assertEqual(inventory(self.home), before)
        self.assertEqual(len(self.own_inventory()), 4)

    def test_existing_runtime_bundle_is_verified_never_overwritten(self):
        report = self.success(self.run_script(apply=True))
        gate = Path(report["runtime"]) / "gate.py"
        gate.chmod(0o600)
        gate.write_bytes(gate.read_bytes() + b"# fixture tamper\n")
        before = inventory(self.home)
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(inventory(self.home), before)
        self.assertFalse(json.loads(result.stdout)["verified_active"])

    def test_runtime_upgrade_changes_only_owned_handlers_in_place_and_keeps_old_bundle(self):
        first = self.success(self.run_script(apply=True))
        old_bundle = inventory(Path(first["runtime"]))
        gate = self.plugin / "hooks/gate.py"
        gate.write_bytes(gate.read_bytes() + b"\n# independently frozen fixture upgrade\n")
        second = self.success(self.run_script(apply=True))
        self.assertNotEqual(first["runtime"], second["runtime"])
        self.assertEqual(first["hook_keys"], second["hook_keys"])
        self.assertEqual(inventory(Path(first["runtime"])), old_bundle)
        updated = json.loads(self.hooks.read_bytes())
        for event, groups in HOOKS["hooks"].items():
            self.assertEqual(updated["hooks"][event][:len(groups)], groups)
        self.assertEqual(len(self.own_inventory()), 4)

    def test_disabled_feature_or_owned_trust_policy_is_never_changed(self):
        for feature in ("hooks", "codex_hooks"):
            with self.subTest(feature=feature):
                self.config.write_bytes(CONFIG + f"\n[features]\n{feature}=false\n".encode())
                before = inventory(self.home)
                self.assertNotEqual(self.run_script(apply=True).returncode, 0)
                self.assertEqual(inventory(self.home), before)
        self.config.write_bytes(CONFIG)
        report = self.success(self.run_script(apply=True))
        self.config.write_bytes(CONFIG + ("\n[hooks.state." + json.dumps(report["hook_keys"][0])
                                           + "]\nenabled=false\n").encode())
        before = inventory(self.home)
        self.assertNotEqual(self.run_script(apply=True).returncode, 0)
        self.assertEqual(inventory(self.home), before)

    def test_owned_status_prefix_with_foreign_command_is_rejected(self):
        value = json.loads(self.hooks.read_bytes())
        value["hooks"]["Stop"][0]["hooks"][0]["statusMessage"] = PREFIX + ": spoof fixture"
        self.hooks.write_text(json.dumps(value))
        before = inventory(self.home)
        self.assertNotEqual(self.run_script(apply=True).returncode, 0)
        self.assertEqual(inventory(self.home), before)

    def test_symlink_config_is_rejected_and_trust_requires_apply(self):
        self.assertNotEqual(self.run_script(trust=True).returncode, 0)
        self.assertFalse(self.evidence.exists())
        self.config.unlink()
        target = self.base / "managed-config.toml"
        target.write_bytes(CONFIG)
        self.config.symlink_to(target)
        before = inventory(self.home)
        self.assertNotEqual(self.run_script(apply=True).returncode, 0)
        self.assertEqual(inventory(self.home), before)
        self.assertEqual(target.read_bytes(), CONFIG)

    def test_explicit_trust_uses_only_native_inventory_hashes_for_the_four_owned_keys(self):
        module = self.module()
        calls = []
        def native(binary, cwd):
            calls.append((binary, cwd))
            return self.own_inventory(trusted=len(calls) == 2), {"fixture-stderr:WARN": 1}
        with patch.object(module, "native_inventory", side_effect=native):
            report = self.invoke(module)
        self.assertTrue(report["applied"])
        self.assertTrue(report["verified_active"])
        self.assertFalse(report["execution_verified"])
        self.assertEqual(len(calls), 2)
        updated = self.config.read_bytes()
        self.assertTrue(updated.startswith(CONFIG))
        after = tomllib.loads(updated.decode())
        actual = {key: after["hooks"]["state"].pop(key) for key in report["hook_keys"]}
        expected = {item["key"]: {"trusted_hash": item["currentHash"]} for item in self.own_inventory()}
        self.assertEqual(actual, expected)
        self.assertEqual(after, tomllib.loads(CONFIG.decode()))

    def test_failed_final_native_verification_reports_partial_installation_not_active(self):
        module = self.module()
        with patch.object(module, "native_inventory", side_effect=lambda binary, cwd: (self.own_inventory(), {})):
            with self.assertRaises(SystemExit):
                self.invoke(module)
        report = json.loads((self.evidence / "forced-hooks-install.json").read_bytes())
        self.assertTrue(report["applied"])
        self.assertTrue(report["partial_installation"])
        self.assertFalse(report["verified_active"])
        self.assertIn("error", report)

    def test_native_inventory_cannot_approve_other_source_or_unexpected_user_hash(self):
        for invalid in ("foreign-source", "plugin-composite-hash", "wrong-event"):
            with self.subTest(invalid=invalid):
                module = self.module()
                def native(binary, cwd):
                    hooks = self.own_inventory()
                    if invalid == "foreign-source":
                        hooks[0]["source"] = "plugin"
                    elif invalid == "plugin-composite-hash":
                        hooks[0]["currentHash"] += "/sha256:" + "b" * 64
                    else:
                        hooks[0]["eventName"] = "sessionStart"
                    return hooks, {}
                with patch.object(module, "native_inventory", side_effect=native):
                    with self.assertRaises(SystemExit):
                        self.invoke(module)
                self.assertEqual(self.config.read_bytes(), CONFIG)
                report = json.loads((self.evidence / "forced-hooks-install.json").read_bytes())
                self.assertTrue(report["partial_installation"])
                self.assertFalse(report["verified_active"])

    def test_trust_hash_update_preserves_every_unrelated_byte_and_comment(self):
        module = self.module()
        key = "fixture-owned-key"
        raw = CONFIG + ('\n[hooks.state.' + json.dumps(key) + ']\n'
                        'enabled = true\ntrusted_hash = "old" # preserve "quoted comment"\n'
                        'future_field = "keep"\n').encode()
        updated = module.trust_config(raw, {key: "sha256:" + "a" * 64})
        self.assertEqual(updated, raw.replace(b'trusted_hash = "old"',
                                             b'trusted_hash = "sha256:' + b"a" * 64 + b'"'))

    def test_atomic_write_detects_concurrent_edit_during_real_fsync(self):
        module = self.module()
        original = self.hooks.read_bytes()
        concurrent = original + b" \n"
        real_sync, real_replace = os.fsync, os.replace
        def sync_then_edit(descriptor):
            real_sync(descriptor)
            self.hooks.write_bytes(concurrent)
        with patch.object(module.os, "fsync", side_effect=sync_then_edit), \
             patch.object(module.os, "replace", wraps=real_replace) as replace:
            with self.assertRaises(ValueError):
                module.atomic_replace(self.hooks, original + b"\n", original)
            replace.assert_not_called()
        self.assertEqual(self.hooks.read_bytes(), concurrent)


if __name__ == "__main__":
    unittest.main()
