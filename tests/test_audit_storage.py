"""Project-tree preservation and legacy metadata migration contracts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_autostart as fixtures

engine = fixtures.engine


def tree(root):
    """Retain the full path/type/mode/hash inventory, including empty directories."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = {"kind": "symlink", "target": os.readlink(path)}
        elif path.is_dir():
            result[relative] = {"kind": "directory", "mode": path.stat().st_mode & 0o777}
        else:
            result[relative] = {"kind": "file", "mode": path.stat().st_mode & 0o777,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


class AuditStorageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AutoStartTests("test_complex_starts_but_assessment_never_creates_experiment")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.project = self.fixture.project

    def legacy(self, assessment):
        """Simulate an actual older installation retaining its original task JSON."""
        current = engine.auto_path(self.project / ".harness2", assessment["task_key"])
        value = json.loads(current.read_bytes())
        value.pop("_legacy_source", None)
        current.unlink()
        legacy = self.project / ".harness2/auto/tasks" / (assessment["task_key"] + ".json")
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return legacy

    def test_lightweight_three_apis_preserve_full_empty_and_strict_existing_trees(self):
        for existing in (False, True):
            for complexity in ("simple", "complex"):
                with self.subTest(existing=existing, complexity=complexity):
                    project = self.project.parent / f"{'old' if existing else 'empty'}-{complexity}"
                    project.mkdir()
                    if existing:
                        (project / "allowed.txt").write_bytes(b"Only this business file may later be changed.\n")
                        (project / "private").mkdir()
                        (project / "private/strict-sentinel.bin").write_bytes(bytes(range(256)))
                        (project / "private/strict-sentinel.bin").chmod(0o400)
                    before = tree(project)
                    context = self.fixture.call("h2_context", project=project)
                    assessment = self.fixture.assess(project=project, complexity=complexity,
                                                     signals=[] if complexity == "simple" else ["cross-module contract"])
                    feedback = self.fixture.feedback(assessment, "fixture-check", outcome="passed", project=project)
                    for result in (context, assessment, feedback):
                        self.assertTrue(result["metadata_external"])
                        self.assertFalse(Path(result["metadata_store"]).is_relative_to(project))
                    self.assertEqual(tree(project), before)
                    self.assertEqual(assessment["decision"], "skip" if complexity == "simple" else "start")
                    self.assertFalse((project / ".harness2").exists())
                    if os.environ.get("H2_TREE_EVIDENCE") == "1":
                        print(json.dumps({"evidence": "lightweight-full-project-tree", "project": str(project),
                                          "existing": existing, "complexity": complexity,
                                          "before": before, "after": tree(project),
                                          "metadata_store": assessment["metadata_store"]}, sort_keys=True))

    def test_same_text_metadata_is_isolated_by_real_project_path(self):
        first = self.fixture.assess(complexity="standard", signals=[])
        self.fixture.feedback(first, "first-project-failure")
        other = self.project.parent / "other-project"
        other.mkdir()
        second = self.fixture.assess(project=other, complexity="standard", signals=[])
        self.assertEqual(first["task_key"], second["task_key"])
        self.assertNotEqual(first["metadata_store"], second["metadata_store"])
        self.assertEqual(second["failure_streak"], 0)
        self.assertEqual(self.fixture.call("h2_context")["recent_tasks"][0]["failure_streak"], 1)
        self.assertEqual(self.fixture.call("h2_context", project=other)["recent_tasks"][0]["failure_streak"], 0)

    def test_legacy_copy_is_read_only_and_later_source_change_blocks_without_losing_events(self):
        assessment = self.fixture.assess(complexity="standard", signals=[])
        self.fixture.feedback(assessment, "retained-old-failure")
        legacy = self.legacy(assessment)
        original = legacy.read_bytes()
        before = tree(self.project)
        context = self.fixture.call("h2_context")
        self.assertEqual(context["recent_tasks"][0]["failure_streak"], 1)
        self.assertEqual(tree(self.project), before)
        migrated = engine.auto_path(self.project / ".harness2", assessment["task_key"])
        self.assertNotEqual(migrated, legacy)
        self.assertIn("retained-old-failure", json.loads(migrated.read_bytes())["events"])
        self.fixture.feedback(assessment, "new-sidecar-passed", outcome="passed")
        self.assertEqual(legacy.read_bytes(), original)
        retained = migrated.read_bytes()
        legacy.write_bytes(original + b" ")
        for action in (lambda: self.fixture.call("h2_context"),
                       lambda: self.fixture.assess(complexity="standard", signals=[]),
                       lambda: self.fixture.feedback(assessment, "cannot-overwrite-new-legacy-fact")):
            with self.assertRaises(ValueError):
                action()
            self.assertEqual(migrated.read_bytes(), retained)

    def test_legacy_closeout_migration_preserves_run_and_closeout_evidence(self):
        assessment = self.fixture.assess()
        with patch.object(engine, "VERSION", "0.2.1"):
            run = self.fixture.adopted(assessment)
        self.assertEqual(run["version"], "0.2.1")
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.assertEqual(self.fixture.closeout(assessment, run)["decision"], "reuse")
        legacy = self.legacy(assessment)
        original = json.loads(legacy.read_bytes())
        before = tree(self.project)
        self.assertEqual(self.fixture.call("h2_status", run=run["id"])["source_baseline"]["kind"],
                         "reported_outer_validation")
        migrated = self.fixture.disk_task(assessment)
        for key in ("events", "closeouts", "closeout_event", "run"):
            self.assertEqual(migrated[key], original[key])
        self.assertEqual(tree(self.project), before)
        self.assertEqual(self.fixture.assess()["decision"], "reuse")

    def test_legacy_source_changed_during_copy_is_rejected(self):
        assessment = self.fixture.assess(complexity="standard", signals=[])
        legacy = self.legacy(assessment)
        original_read = engine.read_bytes
        changed = False

        def concurrent_update(path):
            nonlocal changed
            raw = original_read(path)
            if path == legacy and not changed:
                changed = True
                value = json.loads(raw)
                value["events"]["old-client-real-failure"] = {
                    "outcome": "failed", "check": "old-client fixture check exit=1",
                    "attempt_id": "old-client-attempt", "recorded_at": engine.now()}
                value["failure_streak"] = 1
                legacy.write_text(json.dumps(value))
            return raw

        with patch.object(engine, "read_bytes", side_effect=concurrent_update):
            with self.assertRaises(ValueError):
                self.fixture.call("h2_context")
        self.assertIn("old-client-real-failure", json.loads(legacy.read_bytes())["events"])
        with self.assertRaises(ValueError):
            self.fixture.assess(complexity="standard", signals=[])

    def test_context_merges_legacy_and_external_task_identities_without_duplicates(self):
        first = self.fixture.assess(task="Legacy task", complexity="simple", signals=[])
        self.legacy(first)
        second = self.fixture.assess(task="Sidecar task", complexity="simple", signals=[])
        context = self.fixture.call("h2_context")
        self.assertEqual({task["task_key"] for task in context["recent_tasks"]},
                         {first["task_key"], second["task_key"]})
        again = self.fixture.call("h2_context")
        self.assertEqual(len(again["recent_tasks"]), 2)

    def test_sidecar_inside_project_is_rejected_without_creating_any_project_file(self):
        before = tree(self.project)
        with patch.dict(os.environ, {"CODEX_HOME": str(self.project / "nested-codex-home")}):
            with self.assertRaises(ValueError):
                self.fixture.assess(complexity="simple", signals=[])
        self.assertEqual(tree(self.project), before)

    def test_existing_legacy_lock_is_only_read_and_no_new_project_lock_is_created(self):
        store = self.project / ".harness2"
        store.mkdir()
        lock = store / "lock"
        lock.write_bytes(b"legacy-lock-sentinel")
        lock.chmod(0o400)
        before = tree(self.project)
        self.fixture.assess(complexity="simple", signals=[])
        self.assertEqual(tree(self.project), before)
        self.assertEqual(lock.read_bytes(), b"legacy-lock-sentinel")

    def test_sidecar_symlinks_and_cross_project_identity_are_rejected(self):
        assessment = self.fixture.assess()
        metadata = Path(assessment["metadata_store"])
        identity = metadata / "project.json"
        original = identity.read_bytes()
        changed = json.loads(original)
        changed["project"] = str(self.project.parent)
        identity.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            self.fixture.call("h2_context")
        identity.write_bytes(original)
        tasks = metadata / "auto/tasks"
        moved = metadata / "original-tasks"
        tasks.rename(moved)
        tasks.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.fixture.assess()

    def test_initialize_teaches_scope_safe_assessment_before_implementation(self):
        command = [sys.executable, str(ROOT_ENGINE), "--stdio"]
        result = subprocess.run(command, input=json.dumps({"jsonrpc": "2.0", "id": 1,
                                                         "method": "initialize"}) + "\n",
                                text=True, capture_output=True, check=True)
        initialized = json.loads(result.stdout)["result"]
        instructions = initialized["instructions"][:512]
        for required in ("h2_context", "h2_assess", "sidecar", "simple", "standard", "complex", "h2_start"):
            self.assertIn(required, instructions)
        self.assertIn("指定文件", instructions)


ROOT_ENGINE = fixtures.ROOT / "plugins/harness2-local/server/harness2_local.py"


if __name__ == "__main__":
    unittest.main()
