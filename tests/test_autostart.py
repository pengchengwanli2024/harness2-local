"""Independent automatic-assessment contracts; all writes stay in temporary projects.

No model, external service or installation is invoked. The small checker processes
below validate actual fixture artifacts; they do not claim real agent execution.
Run: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_autostart.py -v
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "harness2_autostart_under_test", ROOT / "plugins/harness2-local/server/harness2_local.py"
)
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


class AutoStartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-auto-contract-")
        self.addCleanup(self.tmp.cleanup)
        isolated_home = Path(self.tmp.name).resolve() / "codex-home"
        environment = patch.dict(os.environ, {"CODEX_HOME": str(isolated_home)})
        environment.start()
        self.addCleanup(environment.stop)
        self.project = Path(self.tmp.name).resolve() / "project"
        self.project.mkdir()
        self.task = "Implement arithmetic source verification and independent validation."
        self.write_inputs(self.project)

    def write_inputs(self, project):
        (project / "task.json").write_text('{"numbers": [19, 23]}')
        (project / "checker.py").write_text(
            "import json\nfrom pathlib import Path\n"
            "expected = sum(json.loads(Path('task.json').read_text())['numbers'])\n"
            "assert json.loads(Path('answer.json').read_text())['answer'] == expected\n"
            "print('actual fixture arithmetic passed')\n")
        (project / "validator.py").write_text(
            "import json\nfrom pathlib import Path\n"
            "result = json.loads(Path('answer.json').read_text())\n"
            "assert result == {'answer': 42}\n"
            "print('independent fixture schema validation passed')\n")

    def call(self, name, project=None, **kwargs):
        return engine.dispatch(name, {"project": str(project or self.project), **kwargs})

    def assess(self, task=None, project=None, **overrides):
        args = {"task": task or self.task, "domain": "arithmetic",
                "complexity": "complex", "signals": ["cross-module implementation and validation"]}
        args.update(overrides)
        return self.call("h2_assess", project=project, **args)

    def feedback(self, assessment, event_id, outcome="failed", project=None, **overrides):
        args = {"task_key": assessment["task_key"], "event_id": event_id,
                "outcome": outcome, "check": f"fixture verification {event_id}; exit={'1' if outcome == 'failed' else '0'}"}
        args.update(overrides)
        return self.call("h2_feedback", project=project, **args)

    def start(self, assessment=None, task=None, **overrides):
        args = {"task": task or self.task, "domain": "arithmetic",
                "executor": "deterministic fixture host; no model execution",
                "input_files": ["task.json", "checker.py", "validator.py"],
                "baseline": {"instructions.md": "Read the source; calculate; validate the actual artifact."},
                "probe_command": [sys.executable, "checker.py"],
                "validation_command": [sys.executable, "validator.py"]}
        if assessment is not None:
            args["assessment"] = assessment["task_key"]
        args.update(overrides)
        return self.call("h2_start", **args)

    def runs(self):
        folder = self.project / ".harness2/runs"
        return sorted(folder.iterdir()) if folder.exists() else []

    def disk_task(self, assessment):
        path = engine.auto_path(self.project / ".harness2", assessment["task_key"])
        return json.loads(path.read_text())

    def disk_run(self, run):
        return json.loads((Path(run["run_dir"]) / "state.json").read_text())

    def adopted(self, assessment=None, task=None):
        run = self.start(assessment, task=task or (assessment.get("task") if assessment else None))
        workspace = Path(run["candidates"]["baseline"]["workspace"])
        (workspace / "answer.json").write_text('{"answer": 42}')
        run = self.call("h2_probe", run=run["id"], candidate="baseline",
                        artifacts=["answer.json"], observation="Actual deterministic fixture artifact checked.")
        self.assertEqual(run["probes"]["baseline"]["status"], "passed")
        run = self.call("h2_adopt", run=run["id"], candidate="baseline",
                        rationale="Actual arithmetic checker and independent schema validation passed.")
        self.assertEqual(run["validation"]["status"], "passed")
        return run

    def test_complex_starts_but_assessment_never_creates_experiment(self):
        assessment = self.assess()
        self.assertEqual(assessment["decision"], "start")
        self.assertEqual(assessment["failure_streak"], 0)
        self.assertEqual(assessment["experience_count"], 0)
        self.assertEqual(assessment["experiences"], [])
        self.assertTrue(assessment["next_step"])
        self.assertTrue(self.disk_task(assessment))
        self.assertEqual(self.runs(), [])
        repeated = self.assess()
        self.assertEqual(repeated["task_key"], assessment["task_key"])
        self.assertEqual(repeated["decision"], "start")
        self.assertEqual(self.runs(), [])

    def test_simple_and_standard_without_failures_skip(self):
        for complexity in ("simple", "standard"):
            with self.subTest(complexity=complexity):
                assessment = self.assess(task=f"Task {complexity}", complexity=complexity, signals=[])
                self.assertEqual(assessment["decision"], "skip")
                self.assertEqual(assessment["failure_streak"], 0)
                self.assertEqual(self.runs(), [])

    def test_complex_needs_observable_signal_and_unknown_complexity_is_rejected(self):
        for overrides in ({"signals": []}, {"signals": [""]},
                          {"signals": "cross-module"}, {"complexity": "enormous"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.assess(**overrides)
        self.assertEqual(self.runs(), [])

    def test_second_failed_check_starts_even_a_simple_task(self):
        assessment = self.assess(complexity="simple", signals=[])
        first = self.feedback(assessment, "test-attempt-1")
        self.assertEqual(first["failure_streak"], 1)
        self.assertEqual(first["decision"], "skip")
        second = self.feedback(assessment, "test-attempt-2")
        self.assertEqual(second["failure_streak"], 2)
        self.assertEqual(second["decision"], "start")
        reassessed = self.assess(complexity="simple", signals=[])
        self.assertEqual(reassessed["failure_streak"], 2)
        self.assertEqual(reassessed["decision"], "start")
        self.assertEqual(self.runs(), [])

    def test_duplicate_feedback_is_idempotent_and_conflicts_are_rejected(self):
        assessment = self.assess(complexity="standard", signals=[])
        first = self.feedback(assessment, "same-check")
        before = self.disk_task(assessment)
        repeated = self.feedback(assessment, "same-check")
        self.assertEqual(first["failure_streak"], repeated["failure_streak"])
        self.assertEqual(before, self.disk_task(assessment))
        with self.assertRaises(ValueError):
            self.feedback(assessment, "same-check", outcome="passed")
        self.assertEqual(before, self.disk_task(assessment))

    def test_pass_resets_and_external_block_does_not_increment(self):
        assessment = self.assess(complexity="standard", signals=[])
        self.feedback(assessment, "first-failure")
        blocked = self.feedback(assessment, "external-device-unavailable", outcome="blocked")
        self.assertEqual(blocked["failure_streak"], 1)
        passed = self.feedback(assessment, "fixed-check", outcome="passed")
        self.assertEqual(passed["failure_streak"], 0)
        self.assertEqual(passed["decision"], "skip")
        failed = self.feedback(assessment, "new-failure")
        self.assertEqual(failed["failure_streak"], 1)
        self.assertEqual(failed["decision"], "skip")

    def test_task_and_project_failure_counters_are_independent(self):
        first = self.assess(complexity="standard", signals=[])
        self.feedback(first, "attempt-1")
        self.feedback(first, "attempt-2")
        second = self.assess(task="Different independent implementation", complexity="standard", signals=[])
        self.assertNotEqual(first["task_key"], second["task_key"])
        self.assertEqual(second["failure_streak"], 0)
        self.assertEqual(self.feedback(second, "attempt-1")["failure_streak"], 1)
        other = Path(self.tmp.name).resolve() / "other-project"
        other.mkdir()
        elsewhere = self.assess(project=other, complexity="standard", signals=[])
        self.assertEqual(elsewhere["failure_streak"], 0)
        self.assertEqual(elsewhere["decision"], "skip")
        self.assertEqual(self.feedback(elsewhere, "attempt-1", project=other)["failure_streak"], 1)
        self.assertEqual(self.assess(complexity="standard", signals=[])["failure_streak"], 2)

    def test_context_restores_original_task_identity_without_crossing_projects(self):
        assessment = self.assess()
        self.feedback(assessment, "retained-failure")
        run = self.start(assessment)
        context = self.call("h2_context")
        self.assertEqual(context["project"], str(self.project))
        self.assertEqual(len(context["recent_tasks"]), 1)
        retained = context["recent_tasks"][0]
        self.assertEqual(retained["task_key"], assessment["task_key"])
        self.assertEqual(retained["task"], self.task)
        self.assertEqual(retained["domain"], "arithmetic")
        self.assertEqual(retained["failure_streak"], 1)
        self.assertEqual(retained["run"], run["id"])
        other = Path(self.tmp.name).resolve() / "other-project"
        other.mkdir()
        elsewhere = self.call("h2_context", project=other)
        self.assertEqual(elsewhere["project"], str(other))
        self.assertEqual(elsewhere["recent_tasks"], [])
        self.assertEqual(elsewhere["domains"], [])
        other_assessment = self.assess(project=other)
        isolated = self.call("h2_context", project=other)["recent_tasks"][0]
        self.assertEqual(isolated["task_key"], other_assessment["task_key"])
        self.assertEqual(isolated["failure_streak"], 0)
        self.assertIsNone(isolated["run"])

    def test_two_failed_checks_in_one_attempt_count_once_then_next_attempt_triggers(self):
        assessment = self.assess(complexity="standard", signals=[])
        first = self.feedback(assessment, "test-failed", attempt_id="implementation-1")
        second = self.feedback(assessment, "lint-failed", attempt_id="implementation-1")
        self.assertEqual(first["failure_streak"], 1)
        self.assertEqual(second["failure_streak"], 1)
        self.assertEqual(second["decision"], "skip")
        next_attempt = self.feedback(assessment, "test-failed-after-fix", attempt_id="implementation-2")
        self.assertEqual(next_attempt["failure_streak"], 2)
        self.assertEqual(next_attempt["decision"], "start")
        self.assertEqual(len(self.disk_task(assessment)["events"]), 3)

    def test_pass_fail_order_within_attempt_preserves_previous_failed_attempt(self):
        for order in (("passed", "failed"), ("failed", "passed")):
            with self.subTest(order=order):
                assessment = self.assess(task="Independent attempt order " + "-".join(order),
                                         complexity="standard", signals=[])
                self.feedback(assessment, "previous-attempt-failed", attempt_id="implementation-1")
                for index, outcome in enumerate(order):
                    result = self.feedback(assessment, f"current-check-{index}", outcome=outcome,
                                           attempt_id="implementation-2")
                self.assertEqual(result["failure_streak"], 2)
                self.assertEqual(result["decision"], "start")
                additional_pass = self.feedback(assessment, "another-passing-check", outcome="passed",
                                                attempt_id="implementation-2")
                self.assertEqual(additional_pass["failure_streak"], 2)
                self.assertEqual(additional_pass["decision"], "start")

    def test_feedback_requires_real_summary_and_known_task(self):
        assessment = self.assess()
        before = self.disk_task(assessment)
        for overrides in ({"check": ""}, {"check": "x" * 1001},
                          {"outcome": "unknown"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.feedback(assessment, "invalid-check", **overrides)
        with self.assertRaises(ValueError):
            self.feedback(assessment, "")
        self.assertEqual(before, self.disk_task(assessment))
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.feedback({"task_key": "a" * 24}, "unassessed-task")

    def test_assessment_binding_resumes_same_run_without_new_workspace(self):
        assessment = self.assess()
        original = self.start(assessment)
        directories = self.runs()
        resumed = self.start(assessment)
        self.assertEqual(resumed["id"], original["id"])
        self.assertEqual(self.runs(), directories)
        self.assertEqual(self.assess()["decision"], "resume")
        self.assertEqual(len(original["candidates"]), 1)

    def test_assessment_cannot_bind_a_different_task_or_domain(self):
        assessment = self.assess()
        for overrides in ({"task": "Different task"}, {"domain": "unrelated"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.start(assessment, **overrides)
        self.assertEqual(self.runs(), [])

    def test_adopted_bound_run_is_reused(self):
        assessment = self.assess()
        adopted = self.adopted(assessment)
        self.assertEqual(self.assess()["decision"], "reuse")
        again = self.start(assessment)
        self.assertEqual(again["id"], adopted["id"])
        self.assertEqual(again["status"], "adopted")
        self.assertEqual(len(self.runs()), 1)

    def test_completed_binding_does_not_reuse_artifacts_after_source_changes(self):
        assessment = self.assess()
        self.adopted(assessment)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        observed = self.assess()
        self.assertEqual(observed["decision"], "blocked")
        self.assertEqual(len(self.runs()), 1)

    def input_hashes(self, run):
        return {name: hashlib.sha256((self.project / name).read_bytes()).hexdigest()
                for name in run["contract"]["inputs"]}

    def closeout(self, assessment, run, event="outer-validation", **overrides):
        return self.feedback(assessment, event, outcome="passed",
                             validated_inputs=self.input_hashes(run), **overrides)

    def test_verified_post_apply_closeout_retains_evidence_and_forbids_replay(self):
        assessment = self.assess()
        self.feedback(assessment, "original-implementation-failure")
        run = self.adopted(assessment)
        folder = Path(run["run_dir"])
        before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.assertEqual(self.assess()["decision"], "blocked")
        result = self.closeout(assessment, run)
        self.assertEqual(result["decision"], "reuse")
        self.assertEqual(result["reason"], "verified_post_apply_closeout")
        self.assertIn("do not reapply", result["next_step"])
        status = self.call("h2_status", run=run["id"])
        self.assertEqual(status["source_baseline"]["kind"], "reported_outer_validation")
        self.assertEqual(status["source_baseline"]["changed_inputs"], ["task.json"])
        self.assertEqual(self.assess()["decision"], "reuse")
        value = self.disk_task(assessment)
        self.assertEqual(value["events"]["original-implementation-failure"]["outcome"], "failed")
        self.assertEqual(value["closeouts"]["outer-validation"]["inputs"], self.input_hashes(run))
        self.assertEqual(before, {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()})
        with self.assertRaises(ValueError):
            self.start(assessment)
        with self.assertRaises(ValueError):
            self.call("h2_probe", run=run["id"], candidate="baseline",
                      artifacts=["answer.json"], observation="Must not replay a completed probe.")
        with self.assertRaises(ValueError):
            self.call("h2_adopt", run=run["id"], candidate="baseline", rationale="Must not replay.")

    def test_changed_source_requires_explicit_matching_validation_hashes(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        old_hashes = self.input_hashes(run)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        unbound = self.feedback(assessment, "passing-without-source-binding", outcome="passed")
        self.assertEqual(unbound["decision"], "blocked")
        stale = self.feedback(assessment, "passing-stale-sources", outcome="passed", validated_inputs=old_hashes)
        self.assertEqual(stale["decision"], "blocked")
        self.assertNotIn("closeouts", self.disk_task(assessment))
        self.assertIn("passing-stale-sources", self.disk_task(assessment)["events"])
        self.assertEqual(self.closeout(assessment, run, "fresh-bound-validation")["decision"], "reuse")

    def test_closeout_duplicates_never_accept_new_source_and_history_is_append_only(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        first_hashes = self.input_hashes(run)
        self.closeout(assessment, run)
        retained = self.disk_task(assessment)
        duplicate = self.feedback(assessment, "outer-validation", outcome="passed", validated_inputs=first_hashes)
        self.assertTrue(duplicate["duplicate_event"])
        self.assertEqual(retained, self.disk_task(assessment))
        (self.project / "task.json").write_text('{"numbers": [21, 23]}')
        repeated = self.feedback(assessment, "outer-validation", outcome="passed", validated_inputs=first_hashes)
        self.assertEqual(repeated["decision"], "blocked")
        self.assertEqual(retained, self.disk_task(assessment))
        with self.assertRaises(ValueError):
            self.closeout(assessment, run)
        with self.assertRaises(ValueError):
            self.feedback(assessment, "outer-validation", outcome="passed")
        with self.assertRaises(ValueError):
            self.call("h2_status", run=run["id"])
        self.assertEqual(self.closeout(assessment, run, "second-outer-validation")["decision"], "reuse")
        current = self.disk_task(assessment)
        self.assertEqual(current["closeouts"]["outer-validation"], retained["closeouts"]["outer-validation"])
        self.assertEqual(set(current["closeouts"]), {"outer-validation", "second-outer-validation"})

    def test_mixed_attempt_results_cannot_authorize_or_keep_closeout(self):
        for order in (("failed", "passed"), ("passed", "failed")):
            with self.subTest(order=order):
                task = self.task + " closeout " + "-".join(order)
                assessment = self.assess(task=task)
                run = self.adopted(assessment)
                (self.project / "task.json").write_text('{"numbers": [20, 23]}')
                for index, outcome in enumerate(order):
                    self.feedback(assessment, f"mixed-{index}", outcome=outcome,
                                  attempt_id="same-implementation", validated_inputs=self.input_hashes(run))
                self.assertEqual(self.assess(task=task)["decision"], "blocked")
                with self.assertRaises(ValueError):
                    self.call("h2_status", run=run["id"])
                self.assertEqual(self.closeout(assessment, run, "fixed-and-verified", attempt_id="new-implementation")["decision"], "reuse")
                self.write_inputs(self.project)

    def test_frozen_tampering_still_blocks_post_apply_feedback_and_retains_event(self):
        for kind in ("snapshot", "harness", "artifact", "log", "validation"):
            with self.subTest(kind=kind):
                task = self.task + " closeout tamper " + kind
                assessment = self.assess(task=task)
                run = self.adopted(assessment)
                folder = Path(run["run_dir"])
                paths = {"snapshot": folder / "inputs/task.json",
                         "harness": folder / "harnesses/baseline/instructions.md",
                         "artifact": folder / "evidence/baseline/artifacts/answer.json",
                         "log": folder / "evidence/baseline/check.log", "validation": folder / "validation.log"}
                target = paths[kind]
                original = target.read_bytes()
                target.write_bytes(original + b"tamper")
                result = self.closeout(assessment, run, "real-check-with-tampered-" + kind)
                self.assertEqual(result["decision"], "blocked")
                value = self.disk_task(assessment)
                self.assertNotIn("closeouts", value)
                self.assertEqual(value["events"]["real-check-with-tampered-" + kind]["outcome"], "passed")
                target.write_bytes(original)

    def test_running_unknown_and_failed_validation_never_authorize_closeout(self):
        for state_kind in ("running", "unknown-probe", "unknown-validation", "failed-validation"):
            with self.subTest(state_kind=state_kind):
                task = self.task + " closeout stage " + state_kind
                assessment = self.assess(task=task)
                run = self.start(assessment, task=task) if state_kind == "running" else self.adopted(assessment)
                state = self.disk_run(run)
                if state_kind == "unknown-probe":
                    state["probes"]["general"] = {"status": "running", "evidence_hashes": {}}
                elif state_kind == "unknown-validation":
                    state["validation"]["status"] = "running"
                elif state_kind == "failed-validation":
                    state["validation"]["status"] = "failed"
                    state["status"] = "running"
                (Path(run["run_dir"]) / "state.json").write_text(json.dumps(state))
                (self.project / "task.json").write_text('{"numbers": [20, 23]}')
                result = self.closeout(assessment, run, "outer-check-after-" + state_kind)
                self.assertEqual(result["decision"], "blocked")
                self.assertNotIn("closeouts", self.disk_task(assessment))
                self.write_inputs(self.project)

    def test_closeout_rejects_corrupt_cross_run_metadata(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.closeout(assessment, run)
        retained = self.disk_task(assessment)
        path = engine.auto_path(self.project / ".harness2", assessment["task_key"])
        for field, value in (("run", "a" * 24), ("contract_sha256", "b" * 64),
                             ("inputs", {"task.json": "c" * 64}), ("attempt_id", "wrong-attempt")):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(retained))
                changed["closeouts"]["outer-validation"][field] = value
                path.write_text(json.dumps(changed))
                self.assertEqual(self.assess()["decision"], "blocked")
                with self.assertRaises(ValueError):
                    self.call("h2_status", run=run["id"])
                path.write_text(json.dumps(retained))

    def test_closeout_works_for_existing_v020_runs(self):
        assessment = self.assess()
        with patch.object(engine, "VERSION", "0.2.0"):
            run = self.adopted(assessment)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.assertEqual(self.closeout(assessment, run)["decision"], "reuse")

    def test_closeout_uses_same_task_whitespace_normalization_as_start(self):
        assessment = self.assess(task="Whitespace  equivalent   task")
        run = self.adopted(assessment, task="Whitespace equivalent task")
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.assertEqual(self.closeout(assessment, run)["decision"], "reuse")

    def test_malformed_closeout_history_is_rejected_without_fallback(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.closeout(assessment, run)
        retained = self.disk_task(assessment)
        path = engine.auto_path(self.project / ".harness2", assessment["task_key"])
        for kind in ("not-dict", "missing-pointer"):
            with self.subTest(kind=kind):
                changed = json.loads(json.dumps(retained))
                if kind == "not-dict":
                    changed["closeouts"] = []
                else:
                    del changed["closeout_event"]
                path.write_text(json.dumps(changed))
                self.assertEqual(self.assess()["decision"], "blocked")
                with self.assertRaises(ValueError):
                    self.call("h2_status", run=run["id"])
                path.write_text(json.dumps(retained))

    def test_legacy_passed_event_cannot_be_retroactively_bound(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        self.feedback(assessment, "legacy-outer-passed", outcome="passed")
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        before = self.disk_task(assessment)
        with self.assertRaises(ValueError):
            self.closeout(assessment, run, "legacy-outer-passed")
        self.assertEqual(before, self.disk_task(assessment))
        self.assertEqual(self.closeout(assessment, run, "new-bound-check")["decision"], "reuse")

    def test_evidence_guards_remain_active_after_valid_closeout(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.closeout(assessment, run)
        folder = Path(run["run_dir"])
        for relative in ("inputs/task.json", "harnesses/baseline/instructions.md",
                         "evidence/baseline/artifacts/answer.json", "evidence/baseline/check.log", "validation.log"):
            with self.subTest(relative=relative):
                path = folder / relative
                original = path.read_bytes()
                path.write_bytes(original + b"tampered after closeout")
                self.assertEqual(self.assess()["decision"], "blocked")
                with self.assertRaises(ValueError):
                    self.call("h2_status", run=run["id"])
                path.write_bytes(original)

    def test_reverting_to_initial_sources_is_still_new_drift_after_closeout(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        original = (self.project / "task.json").read_bytes()
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.closeout(assessment, run)
        (self.project / "task.json").write_bytes(original)
        self.assertEqual(self.assess()["decision"], "blocked")
        with self.assertRaises(ValueError):
            self.call("h2_status", run=run["id"])

    def test_new_passed_feedback_cannot_hide_corrupt_closeout_metadata(self):
        assessment = self.assess()
        run = self.adopted(assessment)
        (self.project / "task.json").write_text('{"numbers": [20, 23]}')
        self.closeout(assessment, run)
        value = self.disk_task(assessment)
        value["closeouts"]["outer-validation"]["contract_sha256"] = "0" * 64
        path = engine.auto_path(self.project / ".harness2", assessment["task_key"])
        path.write_text(json.dumps(value))
        result = self.closeout(assessment, run, "cannot-mask-corruption")
        self.assertEqual(result["decision"], "blocked")
        retained = self.disk_task(assessment)
        self.assertNotIn("cannot-mask-corruption", retained["closeouts"])
        self.assertIn("cannot-mask-corruption", retained["events"])

    def test_validation_hash_argument_is_bounded_and_does_not_change_events_on_bad_shape(self):
        assessment = self.assess()
        original = self.disk_task(assessment)
        for hashes in ([], {}, {"task.json": "bad"}, {"../escape": "a" * 64},
                       {str(index): "a" * 64 for index in range(51)}):
            with self.subTest(hashes=hashes), self.assertRaises(ValueError):
                self.feedback(assessment, "bad-source-hashes", outcome="passed", validated_inputs=hashes)
            self.assertEqual(self.disk_task(assessment), original)

    def test_distinct_concurrent_feedback_events_are_serialized(self):
        assessment = self.assess(complexity="standard", signals=[])
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda event: self.feedback(assessment, event),
                                       ["parallel-check-1", "parallel-check-2"]))
        self.assertEqual(sorted(result["failure_streak"] for result in results), [1, 2])
        self.assertEqual(self.disk_task(assessment)["failure_streak"], 2)
        self.assertEqual(set(self.disk_task(assessment)["events"]),
                         {"parallel-check-1", "parallel-check-2"})

    def test_interrupted_bound_run_is_unknown_blocked_and_never_recreated(self):
        for stage in ("probe", "validation"):
            with self.subTest(stage=stage):
                task = self.task + " " + stage
                assessment = self.assess(task=task)
                run = self.start(assessment, task=task)
                state = self.disk_run(run)
                if stage == "probe":
                    state["probes"]["baseline"] = {"status": "running", "evidence_hashes": {}}
                else:
                    state["validation"] = {"status": "running", "candidate": "baseline"}
                path = Path(run["run_dir"]) / "state.json"
                path.write_text(json.dumps(state))
                original = path.read_bytes()
                count = len(self.runs())
                observed = self.assess(task=task)
                self.assertEqual(observed["decision"], "blocked")
                self.assertIn("UNKNOWN", observed["next_step"])
                try:
                    repeated = self.start(assessment, task=task)
                except ValueError:
                    pass
                else:
                    self.assertEqual(repeated.get("decision"), "blocked")
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(len(self.runs()), count)

    def test_verified_old_project_experience_is_returned_before_new_experiment(self):
        with patch.object(engine, "VERSION", "0.1.0"):
            run = self.adopted()
            note = self.call("h2_reflect", run=run["id"],
                             cue="Source-backed arithmetic task",
                             lesson="Validate the actual source and output schema.",
                             limits="Deterministic local fixture, no model or improvement claim.",
                             evidence=["baseline"])
        assessment = self.assess(task="A new arithmetic source verification task")
        self.assertEqual(assessment["experience_count"], 1)
        self.assertEqual([entry["run"] for entry in assessment["experiences"]], [note["run"]])
        self.assertEqual(len(self.runs()), 1)
        unrelated = self.assess(task="Different domain task", domain="unrelated")
        self.assertEqual(unrelated["experiences"], [])
        other = Path(self.tmp.name).resolve() / "other-project"
        other.mkdir()
        self.assertEqual(self.assess(project=other)["experiences"], [])
        recalled = self.call("h2_recall", domain="arithmetic")
        self.assertEqual([entry["run"] for entry in recalled["entries"]], [note["run"]])

    def test_five_later_experiences_do_not_hide_valid_pre_task_experience(self):
        def record_experience(cue):
            run = self.adopted()
            return self.call("h2_reflect", run=run["id"], cue=cue,
                             lesson="Check the source and actual artifact schema.",
                             limits="Deterministic local fixture only.", evidence=["baseline"])

        earlier = record_experience("Verified experience before this task")
        task = "A long-running arithmetic development task"
        assessed = self.assess(task=task)
        self.assertEqual([entry["run"] for entry in assessed["experiences"]], [earlier["run"]])
        later = [record_experience(f"Later independent task {index}") for index in range(5)]
        recent = self.call("h2_recall", domain="arithmetic")["entries"]
        self.assertEqual({entry["run"] for entry in recent}, {entry["run"] for entry in later})
        reassessed = self.assess(task=task)
        self.assertEqual(reassessed["task_key"], assessed["task_key"])
        self.assertEqual(reassessed["experience_count"], 1)
        self.assertEqual([entry["run"] for entry in reassessed["experiences"]], [earlier["run"]])

    def test_symlink_auto_store_and_task_files_are_rejected(self):
        outside = Path(self.tmp.name).resolve() / "outside"
        outside.mkdir()
        (self.project / ".harness2").mkdir()
        (self.project / ".harness2/auto").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.assess()
        self.assertEqual(list(outside.iterdir()), [])
        (self.project / ".harness2/auto").unlink()
        assessment = self.assess()
        path = engine.auto_path(self.project / ".harness2", assessment["task_key"])
        target = outside / "task.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        original = target.read_bytes()
        with self.assertRaises(ValueError):
            self.feedback(assessment, "cannot-follow-link")
        self.assertEqual(target.read_bytes(), original)

    def test_real_feedback_is_retained_even_when_prior_experience_is_corrupt(self):
        run = self.adopted()
        self.call("h2_reflect", run=run["id"], cue="Arithmetic fixture",
                  lesson="Check the artifact schema.", limits="Local deterministic fixture only.",
                  evidence=["baseline"])
        assessment = self.assess(task="New task after verified prior experience",
                                 complexity="standard", signals=[])
        note = self.project / ".harness2/library/arithmetic" / (run["id"] + ".json")
        note.write_bytes(note.read_bytes() + b" ")
        try:
            result = self.feedback(assessment, "actual-failure-with-corrupt-history")
        except ValueError:
            pass
        else:
            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(result["experiences"], [])
        persisted = self.disk_task(assessment)
        self.assertEqual(persisted["failure_streak"], 1)
        self.assertEqual(persisted["events"]["actual-failure-with-corrupt-history"]["outcome"], "failed")

    def test_feedback_task_key_path_escape_is_rejected(self):
        self.assess()
        for key in ("../escape", "/tmp/harness2-escape", "./alias", "a/b", ""):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.feedback({"task_key": key}, "path-check")


if __name__ == "__main__":
    unittest.main()
