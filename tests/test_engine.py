"""Independent local-method tests. Fixtures are real artifacts, never model rollouts.

Run: python3 -m unittest discover -s tests -p test_engine.py -v
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "harness2_local_under_test", ROOT / "plugins/harness2-local/server/harness2_local.py"
)
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)

CHECKER = '''import json
from pathlib import Path
with Path("invocations.txt").open("a") as f:
    f.write("probe\\n")
task = json.loads(Path("task.json").read_text())
result = json.loads(Path("answer.json").read_text())
print("checked actual answer", result, flush=True)
assert result["answer"] == sum(task["numbers"]), "wrong sum"
'''

VALIDATOR = '''import json
from pathlib import Path
with Path("invocations.txt").open("a") as f:
    f.write("validation\\n")
task = json.loads(Path("task.json").read_text())
result = json.loads(Path("answer.json").read_text())
assert set(result) == {"answer", "sources"}
assert isinstance(result["answer"], int)
assert result["sources"] == ["task.json"]
assert result["answer"] == task["numbers"][0] + task["numbers"][1]
print("independent schema and arithmetic validation passed", flush=True)
'''


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-independent-test-")
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "project"
        self.project.mkdir()
        self.write_inputs(self.project)

    def write_inputs(self, project, checker=CHECKER, validator=VALIDATOR):
        (project / "task.json").write_text(json.dumps({"numbers": [19, 23]}))
        (project / "checker.py").write_text(checker)
        (project / "validator.py").write_text(validator)

    def call(self, name, run=None, project=None, **kwargs):
        args = {"project": str(project or self.project), **kwargs}
        if run is not None:
            args["run"] = run["id"] if isinstance(run, dict) else run
        return engine.dispatch(name, args)

    def start(self, project=None, domain="arithmetic", **overrides):
        args = dict(task="Compute the sum from task.json, cite the source, retain a trajectory.",
                    domain=domain, executor="deterministic fixture host; no model invoked",
                    input_files=["task.json", "checker.py", "validator.py"],
                    baseline={"instructions.md": "Read task.json and produce the requested answer."},
                    probe_command=[sys.executable, "checker.py"],
                    validation_command=[sys.executable, "validator.py"])
        args.update(overrides)
        return self.call("h2_start", project=project, **args)

    def host_write(self, run, label, answer=42, sources=None):
        """Simulate the host writing task artifacts; the checker itself is a real process."""
        cwd = Path(run["candidates"][label]["workspace"])
        (cwd / "answer.json").write_text(json.dumps({
            "answer": answer, "sources": ["task.json"] if sources is None else sources
        }))
        (cwd / "trajectory.md").write_text(
            f"Fixture host independently read frozen task.json in {label}; answer={answer}.\n"
            "No model or agent execution is claimed by this test.\n")
        return cwd

    def probe(self, run, label, answer=42, sources=None, **kwargs):
        self.host_write(run, label, answer, sources)
        return self.call("h2_probe", run, candidate=label,
                         artifacts=["answer.json", "trajectory.md"],
                         observation=f"Actual fixture artifacts for {label}; inspect subprocess evidence.",
                         **kwargs)

    def propose(self, run, label, **overrides):
        args = dict(candidate=label,
                    harness={"instructions.md": f"{label}: inspect frozen source; verify arithmetic."},
                    rationale="Compared baseline/general/domain trajectories, outputs and checker logs; "
                              "retain source checks and schema validation; causal gain remains unproven.")
        args.update(overrides)
        return self.call("h2_propose", run, **args)

    def four_probes(self, **kwargs):
        run = self.start(**kwargs)
        run = self.probe(run, "baseline")
        for label in ("general", "domain", "composed"):
            run = self.propose(run, label)
            run = self.probe(run, label)
        return run

    def adopt(self, run, label="composed"):
        return self.call("h2_adopt", run, candidate=label,
                         rationale="Actual output, source checks and independent final validation support local use.")

    def reflect(self, run):
        return self.call("h2_reflect", run, cue="A small source-backed arithmetic task",
                         lesson="Check the cited source and final artifact schema before local use.",
                         limits="Deterministic fixture; no model rollout or improvement effect established.",
                         evidence=list(run["probes"]))

    def disk_state(self, run):
        return json.loads((Path(run["run_dir"]) / "state.json").read_text())

    def test_real_four_way_flow_retains_hashes_and_local_reflection(self):
        run = self.four_probes()
        self.assertEqual(list(run["probes"]), list(engine.LABELS))
        self.assertEqual(run["candidates"]["composed"]["parents"],
                         ["baseline", "general", "domain"])
        spaces = [Path(c["workspace"]) for c in run["candidates"].values()]
        self.assertEqual(len(set(spaces)), 4)
        for label, probe in run["probes"].items():
            self.assertEqual(probe["status"], "passed")
            self.assertEqual(probe["returncode"], 0)
            self.assertGreater(probe["seconds"], 0)
            for name, expected in probe["evidence_hashes"].items():
                self.assertEqual(hashlib.sha256((Path(run["run_dir"]) / name).read_bytes()).hexdigest(), expected)
            self.assertIn("checked actual answer", (Path(run["run_dir"]) / "evidence" / label / "check.log").read_text())
        run = self.adopt(run)
        self.assertEqual(run["status"], "adopted")
        self.assertEqual(run["rollback"], "baseline")
        self.assertEqual(run["validation"]["status"], "passed")
        self.assertEqual((spaces[-1] / "invocations.txt").read_text(), "probe\nvalidation\n")
        note = self.reflect(run)
        self.assertFalse(note["proven_general_gain"])
        self.assertEqual(note["harness"]["instructions.md"],
                         (Path(run["run_dir"]) / "harnesses/composed/instructions.md").read_text())
        self.assertEqual(self.call("h2_status", run)["status"], "adopted")
        self.assertEqual(sorted(p.name for p in self.project.iterdir()),
                         [".harness2", "checker.py", "task.json", "validator.py"])

    def test_stage_order_and_missing_execution_evidence(self):
        run = self.start()
        with self.assertRaisesRegex(ValueError, "baseline"):
            self.propose(run, "general")
        with self.assertRaisesRegex(ValueError, "Create the candidate"):
            self.call("h2_probe", run, candidate="general", artifacts=["answer.json"], observation="missing")
        with self.assertRaisesRegex(ValueError, "Reflect only"):
            self.reflect(run)
        run = self.probe(run, "baseline")
        with self.assertRaisesRegex(ValueError, "Compose needs"):
            self.propose(run, "composed")
        run = self.propose(run, "general")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.propose(run, "general")
        with self.assertRaisesRegex(ValueError, "Adopt composed"):
            self.adopt(run, "general")

    def test_missing_artifact_does_not_reserve_or_execute_probe(self):
        run = self.start()
        (Path(run["candidates"]["baseline"]["workspace"]) / "empty.json").write_bytes(b"")
        for paths in ([], ["missing.json"], ["task.json"], ["./task.json"], ["empty.json"]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.call("h2_probe", run, candidate="baseline", artifacts=paths, observation="no output")
            self.assertEqual(self.disk_state(run)["probes"], {})
        self.assertFalse((Path(run["candidates"]["baseline"]["workspace"]) / "invocations.txt").exists())

    def test_missing_executable_retains_error_and_cannot_replay(self):
        run = self.start(probe_command=[str(self.project / "nonexistent-executable")])
        run = self.probe(run, "baseline")
        self.assertEqual(run["probes"]["baseline"]["status"], "failed")
        self.assertIsNone(run["probes"]["baseline"]["returncode"])
        self.assertTrue(run["probes"]["baseline"]["evidence_hashes"])
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.call("h2_probe", run, candidate="baseline", artifacts=["answer.json"], observation="retry")

    def test_failed_probe_preserved_and_never_replayed(self):
        run = self.probe(self.start(), "baseline", answer=-1)
        failed = run["probes"]["baseline"]
        self.assertEqual(failed["status"], "failed")
        self.assertNotEqual(failed["returncode"], 0)
        self.assertIn("wrong sum", (Path(run["run_dir"]) / "evidence/baseline/check.log").read_text())
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.call("h2_probe", run, candidate="baseline", artifacts=["answer.json"], observation="retry")
        self.assertEqual(self.call("h2_status", run)["probes"]["baseline"], failed)
        cwd = Path(run["candidates"]["baseline"]["workspace"])
        self.assertEqual((cwd / "invocations.txt").read_text(), "probe\n")
        with self.assertRaisesRegex(ValueError, "successful actual probe"):
            self.adopt(run, "baseline")

    def test_passing_baseline_can_be_explicitly_retained(self):
        run = self.probe(self.start(), "baseline")
        run = self.adopt(run, "baseline")
        self.assertEqual(run["adopted"], "baseline")
        self.assertEqual(run["status"], "adopted")

    def test_validation_failure_is_retained_and_not_replayed(self):
        run = self.probe(self.start(), "baseline", sources=["wrong-source"])
        run = self.adopt(run, "baseline")
        self.assertEqual(run["validation"]["status"], "failed")
        self.assertNotIn("adopted", run)
        with self.assertRaisesRegex(ValueError, "never silently replay"):
            self.adopt(run, "baseline")
        cwd = Path(run["candidates"]["baseline"]["workspace"])
        self.assertEqual((cwd / "invocations.txt").read_text(), "probe\nvalidation\n")

    def test_timeout_is_failed_not_replayed(self):
        (self.project / "checker.py").write_text("import time\nprint('started', flush=True)\ntime.sleep(10)\n")
        run = self.probe(self.start(), "baseline", timeout_seconds=1)
        self.assertEqual(run["probes"]["baseline"]["reason"], "timeout")
        self.assertEqual(run["probes"]["baseline"]["status"], "failed")
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.call("h2_probe", run, candidate="baseline", artifacts=["answer.json"], observation="retry")

    def test_tampered_source_snapshot_harness_evidence_and_contract_reject_resume(self):
        run = self.probe(self.start(), "baseline")
        run_dir = Path(run["run_dir"])
        paths = [self.project / "task.json", run_dir / "inputs/task.json",
                 run_dir / "harnesses/baseline/instructions.md",
                 run_dir / "evidence/baseline/check.log",
                 run_dir / "evidence/baseline/artifacts/answer.json"]
        for path in paths:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"tamper")
                try:
                    with self.assertRaisesRegex(ValueError, "changed"):
                        self.call("h2_status", run)
                finally:
                    path.write_bytes(original)
        state_path = run_dir / "state.json"
        original = state_path.read_bytes()
        state = json.loads(original)
        state["contract"]["task"] = "different task"
        state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "contract changed"):
            self.call("h2_status", run)
        state_path.write_bytes(original)
        self.assertEqual(self.call("h2_status", run)["probes"]["baseline"]["status"], "passed")

    def test_mutated_workspace_artifact_cannot_be_adopted(self):
        run = self.probe(self.start(), "baseline")
        (Path(run["candidates"]["baseline"]["workspace"]) / "answer.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "artifacts changed"):
            self.adopt(run, "baseline")
        self.assertNotIn("validation", self.disk_state(run))

    def test_tampered_validation_and_library_are_rejected(self):
        run = self.adopt(self.probe(self.start(), "baseline"), "baseline")
        self.reflect(run)
        log = Path(run["run_dir"]) / "validation.log"
        original = log.read_bytes()
        log.write_bytes(b"fake pass")
        with self.assertRaisesRegex(ValueError, "Validation evidence changed"):
            self.call("h2_status", run)
        log.write_bytes(original)
        note = Path(self.disk_state(run)["reflection"]["path"])
        note.write_bytes(note.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Experience entry changed"):
            self.call("h2_recall", domain="arithmetic")

    def test_path_escape_and_symlink_inputs_are_rejected(self):
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text("private outside fixture")
        (self.project / "alias.json").symlink_to(outside)
        (self.project / "alias-dir").symlink_to(self.project, target_is_directory=True)
        for name in ("../outside.json", str(outside), "alias.json", "alias-dir/task.json",
                     ".env", ".harness2/anything", "auth.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.start(input_files=[name])

    def test_symlink_store_harness_and_artifact_are_rejected(self):
        run = self.start()
        cwd = self.host_write(run, "baseline")
        (cwd / "alias.json").symlink_to(cwd / "answer.json")
        for name in ("alias.json", "../answer.json", str(cwd / "answer.json")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.call("h2_probe", run, candidate="baseline", artifacts=[name], observation="path check")
        harness_path = Path(run["run_dir"]) / "harnesses/baseline/instructions.md"
        original = harness_path.read_text()
        harness_path.unlink()
        target = self.project / "same-harness.txt"
        target.write_text(original)
        harness_path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.call("h2_status", run)
        other = Path(self.tmp.name) / "other-project"
        other.mkdir()
        (other / ".harness2").symlink_to(self.project / ".harness2", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.call("h2_recall", project=other, domain="arithmetic")

    def test_interrupted_probe_is_unknown_and_never_replayed(self):
        run = self.start()
        state = self.disk_state(run)
        state["probes"]["baseline"] = {"status": "running", "evidence_hashes": {}}
        (Path(run["run_dir"]) / "state.json").write_text(json.dumps(state))
        observed = self.call("h2_status", run)
        self.assertIn("baseline", observed["interrupted"])
        self.assertIn("UNKNOWN", observed["next_step"])
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.call("h2_probe", run, candidate="baseline", artifacts=["answer.json"], observation="retry")

    def test_recall_is_scoped_by_project_domain_and_prior_run_time(self):
        earlier = self.adopt(self.probe(self.start(), "baseline"), "baseline")
        self.reflect(earlier)
        later = self.adopt(self.probe(self.start(), "baseline"), "baseline")
        self.reflect(later)
        notes = self.call("h2_recall", domain="arithmetic", before_run=later["id"])["entries"]
        self.assertEqual([n["run"] for n in notes], [earlier["id"]])
        self.assertEqual(self.call("h2_recall", domain="arithmetic", before_run=earlier["id"])["entries"], [])
        self.assertEqual(self.call("h2_recall", domain="unrelated")["entries"], [])
        other = Path(self.tmp.name) / "other-project"
        other.mkdir()
        self.assertEqual(self.call("h2_recall", project=other, domain="arithmetic")["entries"], [])

    def test_invalid_proposal_does_not_poison_a_valid_retry(self):
        run = self.probe(self.start(), "baseline")
        with self.assertRaisesRegex(ValueError, "rationale"):
            self.propose(run, "general", rationale="")
        self.assertNotIn("general", self.disk_state(run)["candidates"])
        recovered = self.propose(run, "general")
        self.assertIn("general", recovered["candidates"])

    def test_checker_deleted_input_retains_failed_result_and_log(self):
        (self.project / "checker.py").write_text(
            "from pathlib import Path\nprint('deleting input', flush=True)\nPath('task.json').unlink()\n")
        run = self.probe(self.start(), "baseline")
        self.assertEqual(run["probes"]["baseline"]["status"], "failed")
        self.assertTrue(run["probes"]["baseline"]["evidence_hashes"])
        self.assertEqual(self.call("h2_status", run)["probes"]["baseline"]["status"], "failed")

    def test_validator_deleted_artifact_retains_failed_result_and_log(self):
        (self.project / "validator.py").write_text(
            "from pathlib import Path\nprint('deleting artifact', flush=True)\nPath('answer.json').unlink()\n")
        run = self.probe(self.start(), "baseline")
        run = self.adopt(run, "baseline")
        self.assertEqual(run["validation"]["status"], "failed")
        self.assertTrue(run["validation"]["evidence_hashes"])
        self.assertNotIn("adopted", run)

    def test_interrupted_validation_is_reported_unknown(self):
        run = self.probe(self.start(), "baseline")
        state = self.disk_state(run)
        state["validation"] = {"status": "running", "candidate": "baseline"}
        (Path(run["run_dir"]) / "state.json").write_text(json.dumps(state))
        observed = self.call("h2_status", run)
        self.assertIn("UNKNOWN", observed["next_step"])
        self.assertTrue(observed["interrupted"])
        with self.assertRaisesRegex(ValueError, "never silently replay"):
            self.adopt(run, "baseline")


if __name__ == "__main__":
    unittest.main()
