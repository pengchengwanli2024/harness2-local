"""Real optional-adapter installation against an isolated standard-library venv.

Fake Cognee distributions supply metadata and an inert Enola source file. The
installer and adapter are the actual plugin sources; no real Cognee process,
model, account configuration, package download or indexing call is involved.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import venv
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/harness2-local"
SCRIPT = PLUGIN / "scripts/configure_cognee_coexistence.py"
ADAPTER = PLUGIN / "integrations/cognee_external.py"
PTH = "harness2_cognee_external.pth"


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = ("symlink", os.readlink(path))
        elif path.is_dir():
            result[name] = ("directory", path.stat().st_mode & 0o777)
        else:
            result[name] = ("file", path.stat().st_mode & 0o777,
                            hashlib.sha256(path.read_bytes()).hexdigest())
    return result


class CogneeInstallationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(ADAPTER.is_file(), "Use the real adapter source, not a fabricated installation payload")
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-cognee-install-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.addCleanup(self.make_directories_writable)
        self.home = self.base / "codex-home"
        self.home.mkdir()
        self.environment = {**os.environ, "CODEX_HOME": str(self.home),
                            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONPATH": ""}
        self.venv = self.base / "cognee-venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(self.venv)
        self.python = self.venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        query = subprocess.run([str(self.python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                               env=self.environment, text=True, capture_output=True, check=True, timeout=20)
        self.purelib = Path(query.stdout.strip())
        self.assertTrue(self.purelib.is_relative_to(self.venv))
        for name, version in (("cognee", "0.0.0"), ("enola-cli", "0.0.1")):
            folder = self.purelib / (name.replace("-", "_") + "-" + version + ".dist-info")
            folder.mkdir()
            (folder / "METADATA").write_text("Metadata-Version: 2.1\nName: " + name + "\nVersion: " + version + "\n")
        self.package = self.purelib / "cognee"
        (self.package / "tasks/code_graph").mkdir(parents=True)
        (self.package / "__init__.py").write_text("raise AssertionError('Metadata inspection must not import Cognee')\n")
        (self.package / "tasks/__init__.py").write_text("")
        (self.package / "tasks/code_graph/__init__.py").write_text("")
        self.enola = self.package / "tasks/code_graph/enola.py"
        self.enola.write_text("async def run_enola_generate(repo_path, timeout=600):\n"
                              "    return repo_path / '.enola'\n"
                              "def parse_enola_snapshot(snapshot_dir): return []\n"
                              "def snapshot_identity(snapshot_dir): return str(snapshot_dir)\n")
        self.pth = self.purelib / PTH
        self.cache = self.base / "private-index-cache"
        self.evidence = self.base / "installer-evidence"
        self.business = self.base / "business-project"
        self.business.mkdir()
        (self.business / "strict-sentinel.txt").write_bytes(b"Business data must remain byte-identical.\n")
        self.original_package = inventory(self.package)

    def make_directories_writable(self):
        if self.base.exists():
            for path in [self.base, *self.base.rglob("*")]:
                if not path.is_symlink() and path.is_dir():
                    path.chmod(0o700)

    def arguments(self, apply=False, *, cache=None):
        args = [str(SCRIPT), "--venv", str(self.venv), "--cache-root", str(cache or self.cache),
                "--evidence-dir", str(self.evidence)]
        if apply:
            args.append("--apply")
        return args

    def run_script(self, apply=False, *, cache=None):
        return subprocess.run([sys.executable, *self.arguments(apply, cache=cache)],
                              cwd=self.business, env=self.environment,
                              text=True, capture_output=True, timeout=30)

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertFalse(report["restart_performed"])
        self.assertFalse(report["business_files_modified"])
        self.assertFalse(report["original_cognee_package_modified"])
        self.assertEqual(report["metadata"]["cognee"], "0.0.0")
        self.assertEqual(report["metadata"]["enola_cli"], "0.0.1")
        return report

    def test_preview_queries_real_venv_metadata_without_writing_venv_home_or_business(self):
        before = inventory(self.venv)
        home_before = inventory(self.home)
        business_before = inventory(self.business)
        report = self.success(self.run_script())
        self.assertFalse(report["applied"])
        self.assertFalse(self.pth.exists())
        self.assertFalse(Path(report["runtime"]).exists())
        self.assertFalse(self.cache.exists())
        self.assertEqual(inventory(self.venv), before)
        self.assertEqual(inventory(self.home), home_before)
        self.assertEqual(inventory(self.business), business_before)
        self.assertEqual(report["enola_module_sha256"], hashlib.sha256(self.enola.read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.evidence / "cognee-coexistence-install.json").read_text()), report)

    def test_apply_preserves_package_and_installs_real_adapter_idempotently_without_restart(self):
        before = inventory(self.venv)
        business_before = inventory(self.business)
        report = self.success(self.run_script(apply=True))
        self.assertTrue(report["applied"])
        runtime = Path(report["runtime"])
        self.assertEqual(self.pth.read_text().splitlines(),
                         [str(runtime), "import cognee_external; cognee_external.install()"])
        self.assertEqual((runtime / "cognee_external.py").read_bytes(), ADAPTER.read_bytes())
        config = json.loads((runtime / "config.json").read_text())
        self.assertEqual(config, {"cache_root": str(self.cache),
                                  "expected_enola_sha256": hashlib.sha256(self.enola.read_bytes()).hexdigest()})
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o500)
        self.assertEqual((runtime / "cognee_external.py").stat().st_mode & 0o777, 0o400)
        after = inventory(self.venv)
        after.pop(self.pth.relative_to(self.venv).as_posix())
        self.assertEqual(after, before)
        self.assertEqual(inventory(self.package), self.original_package)
        home_before = inventory(self.home)
        pth_before = self.pth.read_bytes()
        again = self.success(self.run_script(apply=True))
        self.assertTrue(again["already_current"])
        self.assertEqual(inventory(self.home), home_before)
        self.assertEqual(self.pth.read_bytes(), pth_before)
        check = subprocess.run([str(self.python), "-c",
                                "import sys,json; print(json.dumps({'finders':sum(bool(getattr(f,'__cognee_external__',False)) for f in sys.meta_path),'cognee_imported':'cognee' in sys.modules}))"],
                               cwd=self.business, env=self.environment, text=True, capture_output=True, timeout=20)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(json.loads(check.stdout), {"finders": 1, "cognee_imported": False})
        self.assertEqual(inventory(self.business), business_before)

    def test_foreign_pth_and_pth_symlink_are_rejected_without_overwriting_owner(self):
        foreign = b"/fixture/foreign-owner-path\n"
        self.pth.write_bytes(foreign)
        before = inventory(self.venv)
        home_before = inventory(self.home)
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(inventory(self.venv), before)
        self.assertEqual(inventory(self.home), home_before)
        self.pth.unlink()
        owner = self.base / "foreign-managed.pth"
        owner.write_bytes(foreign)
        self.pth.symlink_to(owner)
        before = inventory(self.venv)
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(inventory(self.venv), before)
        self.assertEqual(owner.read_bytes(), foreign)

    def test_existing_immutable_runtime_tamper_is_rejected_without_replacement(self):
        report = self.success(self.run_script(apply=True))
        runtime = Path(report["runtime"])
        adapter = runtime / "cognee_external.py"
        adapter.chmod(0o600)
        adapter.write_bytes(adapter.read_bytes() + b"\n# Deliberate fixture tamper, never executable payload.\n")
        home_before = inventory(self.home)
        pth_before = self.pth.read_bytes()
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("immutable runtime changed", result.stderr)
        self.assertEqual(inventory(self.home), home_before)
        self.assertEqual(self.pth.read_bytes(), pth_before)
        self.assertEqual(inventory(self.package), self.original_package)

    def test_immutable_runtime_file_symlink_is_rejected_even_when_target_bytes_match(self):
        report = self.success(self.run_script(apply=True))
        runtime = Path(report["runtime"])
        config = runtime / "config.json"
        original = config.read_bytes()
        external = self.base / "separately-managed-config.json"
        external.write_bytes(original)
        runtime.chmod(0o700)
        config.unlink()
        config.symlink_to(external)
        runtime.chmod(0o500)
        self.assertEqual(config.read_bytes(), original)
        before = inventory(self.home)
        pth_before = self.pth.read_bytes()
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr.lower())
        self.assertEqual(inventory(self.home), before)
        self.assertTrue(config.is_symlink())
        self.assertEqual(external.read_bytes(), original)
        self.assertEqual(self.pth.read_bytes(), pth_before)
        self.assertEqual(inventory(self.package), self.original_package)

    def test_runtime_directory_symlink_is_rejected_without_writing_its_target(self):
        preview = self.success(self.run_script())
        runtime = Path(preview["runtime"])
        runtime.parent.mkdir(parents=True)
        foreign = self.base / "foreign-runtime-owner"
        foreign.mkdir()
        (foreign / "keep.txt").write_bytes(b"Foreign directory must remain intact.\n")
        runtime.symlink_to(foreign, target_is_directory=True)
        home_before = inventory(self.home)
        foreign_before = inventory(foreign)
        venv_before = inventory(self.venv)
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(inventory(self.home), home_before)
        self.assertEqual(inventory(foreign), foreign_before)
        self.assertEqual(inventory(self.venv), venv_before)
        self.assertTrue(runtime.is_symlink())

    def test_concurrent_pth_creation_during_real_fsync_is_preserved_and_not_replaced(self):
        spec = importlib.util.spec_from_file_location("h2_cognee_installer_fixture", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        concurrent = b"/fixture/concurrent-pth-owner\n"
        real_fsync, real_replace = os.fsync, os.replace
        changed = False

        def fsync_then_second_writer(descriptor):
            nonlocal changed
            real_fsync(descriptor)
            if not changed and list(self.purelib.glob(".h2-cognee-*")):
                self.pth.write_bytes(concurrent)
                changed = True

        with patch.dict(os.environ, self.environment), patch.object(sys, "argv", self.arguments(apply=True)), \
             patch.object(module.os, "fsync", side_effect=fsync_then_second_writer), \
             patch.object(module.os, "replace", wraps=real_replace) as replace, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Concurrent change"):
                module.main()
        self.assertTrue(changed)
        self.assertEqual(self.pth.read_bytes(), concurrent)
        self.assertFalse(any(Path(call.args[1]) == self.pth for call in replace.call_args_list))
        self.assertEqual(list(self.purelib.glob(".h2-cognee-*")), [])
        self.assertEqual(inventory(self.package), self.original_package)


if __name__ == "__main__":
    unittest.main()
