"""Black-box gate contracts using real engine state and isolated hook events.

These tests execute the command hook, not Codex or a model. Native MCP lifecycle
payloads carry results actually produced by the engine; live-host interception is
verified separately. No user configuration, credential, or business project is used.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import select
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/harness2-local"
GATE = PLUGIN / "hooks/gate.py"
ENGINE_PATH = PLUGIN / "server/harness2_local.py"
SPEC = importlib.util.spec_from_file_location("h2_forced_hook_engine_fixture", ENGINE_PATH)
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


def tree(root):
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


class ForcedHookTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(GATE.is_file(), "The actual command-hook implementation is required")
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-forced-hook-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "codex-home"
        self.home.mkdir()
        environment = patch.dict(os.environ, {"CODEX_HOME": str(self.home),
                                             "PYTHONDONTWRITEBYTECODE": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "README.md").write_bytes(b"Demo\n")
        (self.project / "unchanged.bin").write_bytes(bytes(range(256)))
        (self.project / "unchanged.bin").chmod(0o400)
        self.other = self.base / "other-project"
        self.other.mkdir()
        (self.other / "README.md").write_bytes(b"Other\n")
        self.session = "fixture-session"
        self.turn = "fixture-turn-1"

    def event(self, name, *, project=None, turn=None, **values):
        return {"hook_event_name": name, "session_id": self.session,
                "turn_id": turn or self.turn, "cwd": str(project or self.project), **values}

    def hook(self, event, *flags):
        process = subprocess.run([sys.executable, str(GATE), "--engine", str(ENGINE_PATH), *flags],
                                 input=json.dumps(event), text=True, capture_output=True,
                                 cwd=self.project, env=dict(os.environ), timeout=15)
        try:
            payload = json.loads(process.stdout) if process.stdout.strip() else {}
        except json.JSONDecodeError as error:
            self.fail(f"Hook stdout must remain one valid JSON object: {error}: {process.stdout[:500]!r}")
        self.assertIsInstance(payload, dict)
        return process, payload

    def assert_denied(self, result):
        process, payload = result
        blocked = (process.returncode == 2 or payload.get("decision") == "block"
                   or payload.get("hookSpecificOutput", {}).get("permissionDecision") == "deny")
        self.assertTrue(blocked, f"Unassessed operation must be denied: {process.returncode}, {payload}, {process.stderr}")

    def assert_allowed(self, result):
        process, payload = result
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertNotEqual(payload.get("decision"), "block", payload)
        self.assertNotEqual(payload.get("hookSpecificOutput", {}).get("permissionDecision"), "deny", payload)

    def prompt(self, *, project=None, turn=None, text=None):
        result = self.hook(self.event("UserPromptSubmit", project=project, turn=turn,
                                      prompt=text or "只修改 README.md 第一行 Demo 为 Demo.，其它文件不变。"))
        self.assert_allowed(result)
        context = result[1].get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("h2_context", context)
        self.assertIn("h2_assess", context)
        return result

    def pre(self, tool="Bash", arguments=None, *, project=None, turn=None):
        if arguments is None:
            arguments = {"command": "python3 -c 'from pathlib import Path; Path(\"README.md\").write_text(\"Demo.\\n\")'",
                         "workdir": str(project or self.project)}
        return self.hook(self.event("PreToolUse", project=project, turn=turn,
                                    tool_name=tool, tool_input=arguments))

    def actual(self, tool, *, project=None, **arguments):
        return engine.dispatch(tool, {"project": str(project or self.project), **arguments})

    def observe(self, tool, arguments, value, *, project=None, turn=None, failed=False,
                tool_use_id=None, event_cwd=None, hook_flags=()):
        response = {"content": [{"type": "text", "text": json.dumps(value)}], "isError": failed}
        event = self.event("PostToolUse", project=project, turn=turn,
                           tool_name="mcp__harness2_local__" + tool,
                           tool_input={"project": str(project or self.project), **arguments},
                           tool_response=response)
        if tool_use_id is not None:
            event["tool_use_id"] = tool_use_id
        if event_cwd is not None:
            event["cwd"] = str(event_cwd)
        return self.hook(event, *hook_flags)

    def pair(self, *, project=None, turn=None, complexity="simple"):
        project = project or self.project
        context = self.actual("h2_context", project=project)
        self.assert_allowed(self.observe("h2_context", {}, context, project=project, turn=turn))
        arguments = {"task": ("Upgrade the fixture parser/codec roundtrip contract" if complexity == "complex"
                              else "Repair the fixture README punctuation without other business edits"),
                     "domain": "fixture-files", "complexity": complexity,
                     "signals": ["Cross-component contract fixture"] if complexity == "complex" else []}
        assessment = self.actual("h2_assess", project=project, **arguments)
        self.assert_allowed(self.observe("h2_assess", arguments, assessment, project=project, turn=turn))
        return assessment

    def patch(self, relative, content="prepared"):
        return {"command": "*** Begin Patch\n*** Add File: " + str(self.project / relative)
                + "\n+" + content + "\n*** End Patch"}

    def test_missing_assessment_blocks_shell_and_patch_even_without_prompt_event(self):
        before = tree(self.project)
        self.assert_denied(self.pre())
        self.assert_denied(self.pre("apply_patch", self.patch("new-business.py")))
        self.assertEqual(tree(self.project), before)
        self.assertFalse((self.project / ".harness2").exists())

    def test_real_native_pair_allows_simple_tools_without_creating_experiment_or_business_files(self):
        before = tree(self.project)
        self.prompt()
        self.assert_denied(self.pre())
        assessment = self.pair()
        self.assertEqual(assessment["decision"], "skip")
        self.assert_allowed(self.pre())
        self.assert_allowed(self.pre("apply_patch", self.patch("new-business.py")))
        self.assertEqual(tree(self.project), before)
        self.assertFalse((self.project / ".harness2").exists())

    def test_prompt_records_real_private_intake_without_hiding_five_genuine_goals(self):
        genuine = []
        for number in range(5):
            goal = self.actual("h2_assess", task=f"Genuine fixture goal {number}",
                               domain="fixture-files", complexity="simple", signals=[])
            genuine.append(goal["task_key"])
        before = tree(self.project)
        sensitive_sentinel = "fixture-sensitive-prompt-sentinel-27fd"
        self.prompt(text="修复本项目，输入中有不应持久化的 " + sensitive_sentinel)
        receipt = (self.home / "harness2-local/hook-gates"
                   / hashlib.sha256(self.session.encode()).hexdigest()
                   / (hashlib.sha256(self.turn.encode()).hexdigest() + ".json"))
        state = json.loads(receipt.read_text())["payload"]
        key = hashlib.sha256(str(self.project).encode()).hexdigest()
        preflight = state["preflights"][key]
        self.assertEqual(preflight["project"], str(self.project))
        self.assertEqual(preflight["decision"], "skip")
        self.assertEqual(preflight["transport"], "trusted-command-hook/shared-engine")
        self.assertTrue(preflight["semantic_goal_pending"])
        with engine.locked(str(self.project)) as (_, store):
            intake = engine.auto_load(store, preflight["task_key"])
        self.assertEqual(intake["record_kind"], "hook-intake")
        self.assertEqual(intake["domain"], "codex-kickoff")
        self.assertEqual(intake["complexity"], "standard")
        self.assertTrue(intake["task"].startswith("Codex kickoff "))
        self.assertFalse(intake.get("run"))
        context = self.actual("h2_context")
        self.assertEqual(len(context["recent_tasks"]), 5)
        self.assertEqual({v["task_key"] for v in context["recent_tasks"]}, set(genuine))
        self.assertNotIn(preflight["task_key"], {v["task_key"] for v in context["recent_tasks"]})
        for path in self.home.rglob("*.json"):
            self.assertNotIn(sensitive_sentinel, path.read_text(), path)
        self.assert_denied(self.pre())
        self.assert_denied(self.hook(self.event("Stop")))
        self.assertEqual(tree(self.project), before)
        self.assertFalse((self.project / ".harness2").exists())

    def test_successful_context_reread_does_not_revoke_an_already_assessed_goal(self):
        self.prompt()
        assessment = self.pair()
        self.assert_allowed(self.pre())
        for _ in range(2):
            context = self.actual("h2_context")
            self.assertIn(assessment["task_key"], {v["task_key"] for v in context["recent_tasks"]})
            self.assert_allowed(self.observe("h2_context", {}, context))
            self.assert_allowed(self.pre())
            self.assert_allowed(self.hook(self.event("Stop")))
        self.assertFalse((self.project / ".harness2").exists())

    def test_blocked_real_run_allows_diagnostics_but_forbids_replay_and_completion(self):
        self.prompt(text="升级 parser/schema/codec 真实契约并保持冻结证据。")
        assessment = self.pair(complexity="complex")
        (self.project / "task.json").write_text('{"value":42}\n')
        (self.project / "probe.py").write_text("print('actual frozen probe fixture')\n")
        (self.project / "validation.py").write_text("print('separate frozen validation fixture')\n")
        run = self.actual("h2_start", task=assessment["task"], domain=assessment["domain"],
                          executor="deterministic fixture, no model or probe execution claimed",
                          assessment=assessment["task_key"],
                          input_files=["task.json", "probe.py", "validation.py"],
                          baseline={"instructions.md": "Use the selected frozen fixture inputs."},
                          probe_command=[sys.executable, "probe.py"],
                          validation_command=[sys.executable, "validation.py"])
        run_state = self.project / ".harness2/runs" / run["id"] / "state.json"
        frozen_state = run_state.read_bytes()
        (self.project / "task.json").write_text('{"value":43}\n')
        arguments = {"task": assessment["task"], "domain": assessment["domain"],
                     "complexity": "complex", "signals": ["Actual fixture input changed after frozen start"]}
        blocked = self.actual("h2_assess", **arguments)
        self.assertEqual(blocked["decision"], "blocked")
        self.assert_allowed(self.observe("h2_assess", arguments, blocked))
        diagnostic = self.pre(arguments={"command": "python3 -c 'print(42)'", "workdir": str(self.project)})
        self.assert_allowed(diagnostic)
        self.assertIn("blocked", diagnostic[1].get("hookSpecificOutput", {}).get("additionalContext", ""))
        self.assert_denied(self.pre("mcp__harness2_local__h2_start",
                                   {"project": str(self.project), "assessment": assessment["task_key"]}))
        for tool in ("h2_probe", "h2_adopt", "h2_propose", "h2_reflect"):
            self.assert_denied(self.pre("mcp__harness2_local__" + tool,
                                       {"project": str(self.project), "run": run["id"]}))
        self.assert_denied(self.hook(self.event("Stop")))
        self.assertEqual(run_state.read_bytes(), frozen_state)

    def test_failed_or_out_of_order_lifecycle_results_do_not_issue_permission(self):
        self.prompt()
        arguments = {"task": "Repair the fixture README punctuation without other business edits",
                     "domain": "fixture-files", "complexity": "simple", "signals": []}
        assessment = self.actual("h2_assess", **arguments)
        self.observe("h2_assess", arguments, assessment)
        self.assert_denied(self.pre())
        context = self.actual("h2_context")
        self.observe("h2_context", {}, context, failed=True)
        self.assert_denied(self.pre())
        self.observe("h2_context", {}, context)
        self.observe("h2_assess", arguments, assessment, failed=True)
        self.assert_denied(self.pre())
        assessment = self.actual("h2_assess", **arguments)
        self.observe("h2_assess", arguments, assessment)
        self.assert_allowed(self.pre())

    def test_previous_turn_receipt_cannot_authorize_a_new_prompt_or_silent_resume(self):
        self.prompt()
        self.pair()
        self.assert_allowed(self.pre())
        second = "fixture-turn-2"
        self.assert_denied(self.pre(turn=second))
        self.prompt(turn=second)
        self.assert_denied(self.pre(turn=second))
        self.pair(turn=second)
        self.assert_allowed(self.pre(turn=second))

    def test_assessment_for_one_project_does_not_authorize_another_project(self):
        self.prompt()
        self.pair()
        self.assert_allowed(self.pre())
        before = tree(self.other)
        self.assert_denied(self.pre(project=self.other))
        self.assert_denied(self.pre(arguments={"command": "touch unrelated-file", "workdir": str(self.other)}))
        self.assertEqual(tree(self.other), before)

    def test_same_turn_changed_prompt_revokes_previous_goal_but_identical_redelivery_is_idempotent(self):
        self.prompt()
        self.pair()
        self.assert_allowed(self.pre())
        self.prompt()
        self.assert_allowed(self.pre())
        self.prompt(text="现在开始另一个目标：修复 parser 的错误定位，不沿用前一个README目标。")
        self.assert_denied(self.pre())
        self.pair()
        self.assert_allowed(self.pre())

    def test_tampered_receipt_is_denied_and_preserved_instead_of_silently_repaired(self):
        self.prompt()
        self.pair()
        before = tree(self.project)
        receipt = (self.home / "harness2-local/hook-gates"
                   / hashlib.sha256(self.session.encode()).hexdigest()
                   / (hashlib.sha256(self.turn.encode()).hexdigest() + ".json"))
        self.assertTrue(receipt.is_file())
        value = json.loads(receipt.read_text())
        value["payload"]["projects"] = {}
        corrupted = (json.dumps(value) + "\n").encode()
        receipt.write_bytes(corrupted)
        self.assert_denied(self.pre())
        self.assert_denied(self.hook(self.event("Stop")))
        self.assertEqual(receipt.read_bytes(), corrupted)
        self.assertEqual(tree(self.project), before)

    def test_stop_requires_actual_successful_pair_before_plain_final_answer(self):
        self.prompt()
        self.assert_denied(self.hook(self.event("Stop", last_assistant_message="完成。", stop_hook_active=False)))
        self.pair()
        self.assert_allowed(self.hook(self.event("Stop", last_assistant_message="完成。", stop_hook_active=True)))
        self.assertFalse((self.project / ".harness2").exists())

    def test_simple_skip_denies_h2_start_even_if_caller_requests_an_unbound_experiment(self):
        self.prompt()
        assessment = self.pair()
        self.assertEqual(assessment["decision"], "skip")
        self.assert_denied(self.pre("mcp__harness2_local__h2_start", {"project": str(self.project),
                           "task": assessment["task"], "domain": assessment["domain"],
                           "assessment": assessment["task_key"]}))
        self.assert_denied(self.pre("mcp__harness2_local__h2_start", {"project": str(self.project)}))
        self.assertFalse((self.project / ".harness2").exists())

    def test_complex_assessment_requires_preparation_scope_until_a_real_bound_start(self):
        self.prompt(text="升级 parser/schema/codec 跨模块契约，处理兼容、转义和往返一致性。")
        assessment = self.pair(complexity="complex")
        self.assertEqual(assessment["decision"], "start")
        feedback = {"project": str(self.project), "task_key": assessment["task_key"],
                    "event_id": "fixture-hook-scope-only", "outcome": "blocked",
                    "check": "Authorization-only unit fixture; feedback is not dispatched"}
        self.assert_allowed(self.pre("mcp__harness2_local__h2_feedback", feedback))
        self.assert_denied(self.pre("mcp__harness2_local__h2_feedback", {**feedback, "task_key": "0" * 24}))
        self.assert_denied(self.hook(self.event("Stop")))
        self.assert_denied(self.pre())
        self.assert_denied(self.pre("apply_patch", self.patch("implementation.py")))
        prep = ".harness2-preflight/" + assessment["task_key"]
        self.assert_allowed(self.pre("apply_patch", self.patch(prep + "/checker.py")))
        self.assert_allowed(self.pre(arguments={"command": "cat README.md", "workdir": str(self.project)}))
        self.assert_denied(self.pre(arguments={"command": "cat README.md; touch implementation.py", "workdir": str(self.project)}))
        self.assert_denied(self.pre(arguments={"command": "rg --pre='touch implementation.py' x README.md", "workdir": str(self.project)}))
        (self.project / "task.json").write_text('{"value":42}\n')
        (self.project / "probe.py").write_text("print('frozen probe fixture')\n")
        (self.project / "validation.py").write_text("print('frozen independent validation fixture')\n")
        run = self.actual("h2_start", task=assessment["task"], domain=assessment["domain"],
                          executor="deterministic unit fixture, no model", assessment=assessment["task_key"],
                          input_files=["task.json", "probe.py", "validation.py"],
                          baseline={"instructions.md": "Read the fixture inputs and produce an independent artifact."},
                          probe_command=[sys.executable, "probe.py"],
                          validation_command=[sys.executable, "validation.py"])
        self.assertTrue(run["id"])
        self.assert_allowed(self.hook(self.event("Stop")))
        self.assert_allowed(self.pre())
        self.assert_allowed(self.pre("apply_patch", self.patch("implementation.py")))

    def test_reassessment_revokes_current_grant_until_a_fresh_successful_native_result(self):
        self.prompt()
        assessment = self.pair()
        self.assert_allowed(self.pre())
        arguments = {"task": assessment["task"], "domain": assessment["domain"],
                     "complexity": "simple", "signals": []}
        before_call = self.pre("mcp__harness2_local__h2_assess",
                               {"project": str(self.project), **arguments})
        self.assert_allowed(before_call)
        self.assert_denied(self.pre())
        fresh = self.actual("h2_assess", **arguments)
        self.assertEqual(fresh["task_key"], assessment["task_key"])
        self.assert_allowed(self.observe("h2_assess", arguments, fresh))
        self.assert_allowed(self.pre())

    def test_internal_deadline_explicitly_denies_real_gate_and_engine_lock_waits(self):
        self.prompt()
        self.pair()
        context = self.actual("h2_context")
        session_lock = (self.home / "harness2-local/hook-gates"
                        / hashlib.sha256(self.session.encode()).hexdigest() / "lock")
        engine_lock = Path(context["metadata_store"]) / "lock"
        before = tree(self.project)
        holder_code = ("import fcntl,sys\n"
                       "with open(sys.argv[1], 'a+') as lock:\n"
                       " fcntl.flock(lock, fcntl.LOCK_EX)\n"
                       " print('held', flush=True)\n"
                       " sys.stdin.read()\n")
        for name, lock_path in (("session", session_lock), ("engine", engine_lock)):
            with self.subTest(lock=name):
                self.assertTrue(lock_path.is_file())
                holder = subprocess.Popen([sys.executable, "-c", holder_code, str(lock_path)],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, env=dict(os.environ))
                try:
                    ready, _, _ = select.select([holder.stdout], [], [], 4)
                    self.assertTrue(ready, "Lock holder did not reach a bounded ready state")
                    self.assertEqual(holder.stdout.readline().strip(), "held")
                    started = time.monotonic()
                    result = self.hook(self.event("PreToolUse", tool_name="Bash",
                                                 tool_input={"command": "touch must-not-exist", "workdir": str(self.project)}),
                                       "--deadline-seconds", "1")
                    self.assert_denied(result)
                    self.assertEqual(result[0].returncode, 2, "Internal timeout must fail explicitly before host timeout")
                    self.assertLess(time.monotonic() - started, 8)
                    self.assertEqual(tree(self.project), before)
                finally:
                    if holder.stdin and not holder.stdin.closed:
                        holder.stdin.close()
                    if holder.poll() is None:
                        try:
                            holder.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            holder.kill()
                            holder.wait(timeout=3)
                    holder.stdout.close()
                    holder.stderr.close()
        self.assert_allowed(self.pre())

    def fixture_bound_run(self, assessment, *, project=None):
        """Freeze an actual bound fixture run; do not claim probe execution."""
        project = project or self.project
        (project / "task.json").write_text('{"value":42}\n')
        (project / "probe.py").write_text("print('frozen fixture probe')\n")
        (project / "validation.py").write_text("print('independent frozen fixture validation')\n")
        return self.actual("h2_start", project=project, task=assessment["task"], domain=assessment["domain"],
                           executor="deterministic unit fixture, no model or probe claimed",
                           assessment=assessment["task_key"],
                           input_files=["task.json", "probe.py", "validation.py"],
                           baseline={"instructions.md": "Use the frozen fixture inputs."},
                           probe_command=[sys.executable, "probe.py"],
                           validation_command=[sys.executable, "validation.py"])

    def test_complex_preparation_rejects_process_execution_flags_and_shell_environment_overrides(self):
        self.prompt(text="升级跨模块parser/codec的复杂契约。")
        self.pair(complexity="complex")
        before = tree(self.project)
        commands = ["rg --no-config --hostname-bin=fixture-must-not-execute needle README.md",
                    "rg --no-config --hostname-bin fixture-must-not-execute needle README.md",
                    "rg --no-config --search-zip needle README.md",
                    "rg --no-config -z needle README.md",
                    "rg --no-config -nzi needle README.md",
                    "rg needle README.md"]
        for command in commands:
            with self.subTest(command=command):
                self.assert_denied(self.pre(arguments={"command": command, "workdir": str(self.project)}))
        for override in ({"shell": "/fixture/must-not-execute"}, {"shell": "/bin/zsh"},
                         {"env": {"RIPGREP_CONFIG_PATH": "/fixture/unread-config"}},
                         {"environment": {}}, {"login": True}, {"login_shell": True}, {"tty": True}):
            with self.subTest(override=override):
                self.assert_denied(self.pre(arguments={"command": "cat README.md", "workdir": str(self.project), **override}))
        with patch.dict(os.environ, {"RIPGREP_CONFIG_PATH": str(self.base / "must-not-load.conf")}):
            self.assert_denied(self.pre(arguments={"command": "rg needle README.md", "workdir": str(self.project)}))
            self.assert_allowed(self.pre(arguments={"command": "rg --no-config needle README.md", "workdir": str(self.project)}))
        self.assertEqual(tree(self.project), before)

    def test_pending_context_survives_invalid_post_project_and_requires_matching_success(self):
        self.prompt()
        assessment = self.pair()
        self.assert_allowed(self.pre())
        identifier = "pending-context-invalid-project"
        native_pre = self.event("PreToolUse", tool_name="mcp__harness2_local__h2_context",
                                tool_input={"project": str(self.project)}, tool_use_id=identifier)
        self.assert_allowed(self.hook(native_pre))
        context = self.actual("h2_context")
        self.observe("h2_context", {}, context, project=self.base / "missing-project",
                     event_cwd=self.project, tool_use_id=identifier)
        self.assert_denied(self.pre())
        self.assert_allowed(self.observe("h2_context", {}, self.actual("h2_context"), tool_use_id=identifier))
        self.assert_allowed(self.pre())  # A matching successful context restores the unchanged goal.
        self.assert_allowed(self.hook(native_pre))
        self.observe("h2_context", {}, self.actual("h2_context"))  # Missing the known Pre ID.
        self.assert_denied(self.pre())
        self.assert_allowed(self.hook(native_pre))
        self.assert_allowed(self.observe("h2_context", {}, self.actual("h2_context"), tool_use_id=identifier))
        arguments = {"task": assessment["task"], "domain": assessment["domain"], "complexity": "simple", "signals": []}
        self.assert_allowed(self.observe("h2_assess", arguments, self.actual("h2_assess", **arguments)))
        self.assert_allowed(self.pre())
        self.assert_allowed(self.hook(native_pre))
        self.observe("h2_context", {}, self.actual("h2_context"), tool_use_id="wrong-native-call")
        self.assert_denied(self.pre())
        # A mismatched response cannot grant permission; obtain a new complete native pair.
        self.pair()
        self.assert_allowed(self.pre())

    def test_context_post_timeout_in_verified_workspace_leaves_pending_until_successful_redelivery(self):
        self.prompt(text="升级跨模块parser/codec的复杂契约。")
        assessment = self.pair(complexity="complex")
        run = self.fixture_bound_run(assessment)
        workspace = Path(run["candidates"]["baseline"]["workspace"])
        context = self.actual("h2_context")
        identifier = "pending-context-engine-lock"
        native_pre = self.event("PreToolUse", tool_name="mcp__harness2_local__h2_context",
                                tool_input={"project": str(self.project)}, tool_use_id=identifier)
        self.assert_allowed(self.hook(native_pre))
        lock_path = Path(context["metadata_store"]) / "lock"
        holder_code = ("import fcntl,sys\nwith open(sys.argv[1], 'a+') as lock:\n"
                       " fcntl.flock(lock, fcntl.LOCK_EX)\n print('held', flush=True)\n sys.stdin.read()\n")
        holder = subprocess.Popen([sys.executable, "-c", holder_code, str(lock_path)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=dict(os.environ))
        try:
            ready, _, _ = select.select([holder.stdout], [], [], 4)
            self.assertTrue(ready)
            self.assertEqual(holder.stdout.readline().strip(), "held")
            post = self.observe("h2_context", {}, context, tool_use_id=identifier, event_cwd=workspace,
                                hook_flags=("--deadline-seconds", "1"))
            self.assertEqual(post[0].returncode, 0)  # Post cannot undo the completed native tool.
            self.assertIn("GateDeadline", post[1].get("systemMessage", ""))
        finally:
            holder.stdin.close()
            try:
                holder.wait(timeout=3)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.wait(timeout=3)
            holder.stdout.close()
            holder.stderr.close()
        self.assert_denied(self.pre())
        self.assert_allowed(self.observe("h2_context", {}, self.actual("h2_context"),
                                         tool_use_id=identifier, event_cwd=workspace))
        self.assert_allowed(self.pre())  # The unchanged, already-assessed goal is sufficient.

    def test_stop_checks_every_semantic_project_not_only_the_last_selected_simple_one(self):
        self.prompt(text="对多个项目分别核对开发目标。")
        complex_goal = self.pair(complexity="complex")
        self.pair(project=self.other)
        self.assert_allowed(self.pre(project=self.other))
        self.assert_denied(self.hook(self.event("Stop", project=self.other)))
        run = self.fixture_bound_run(complex_goal)
        self.assertTrue(run["id"])
        self.assert_allowed(self.hook(self.event("Stop", project=self.other)))
        (self.project / "task.json").write_text('{"value":43}\n')
        self.assert_denied(self.hook(self.event("Stop", project=self.other)))

    def test_verified_non_git_candidate_workdirs_reuse_parent_scope_and_cannot_nest(self):
        self.prompt(text="升级跨模块parser/codec的复杂契约。")
        assessment = self.pair(complexity="complex")
        run = self.fixture_bound_run(assessment)
        workspace = Path(run["candidates"]["baseline"]["workspace"])
        child = workspace / "outputs"
        child.mkdir()
        metadata_before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob("project.json"))
        tasks_before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob("auto/tasks/*.json"))
        for working in (workspace, child):
            self.assert_allowed(self.pre(arguments={"command": "python3 -c 'print(42)'", "workdir": str(working)}))
        self.assertEqual(sorted(str(p.relative_to(self.home)) for p in self.home.rglob("project.json")), metadata_before)
        self.assertEqual(sorted(str(p.relative_to(self.home)) for p in self.home.rglob("auto/tasks/*.json")), tasks_before)
        self.assertEqual(len(list((self.project / ".harness2/runs").iterdir())), 1)
        arguments = {"task": "A distinct fixture goal introduced inside the candidate workspace",
                     "domain": assessment["domain"], "complexity": "complex",
                     "signals": ["Actual separately assessed fixture goal within parent run"]}
        self.assert_allowed(self.observe("h2_context", {}, self.actual("h2_context"), event_cwd=workspace))
        different = self.actual("h2_assess", **arguments)
        self.assert_allowed(self.observe("h2_assess", arguments, different, event_cwd=workspace))
        event = self.event("PreToolUse", tool_name="mcp__harness2_local__h2_start",
                           tool_input={"project": str(self.project), "assessment": different["task_key"]})
        event["cwd"] = str(workspace)
        nested = self.hook(event)
        self.assert_denied(nested)
        self.assertIn("nested", nested[1].get("hookSpecificOutput", {}).get("permissionDecisionReason", ""))
        self.assertEqual(len(list((self.project / ".harness2/runs").iterdir())), 1)
        state_path = self.project / ".harness2/runs" / run["id"] / "state.json"
        damaged = json.loads(state_path.read_text())
        damaged["contract"]["executor"] = "tampered contract fixture"
        state_path.write_text(json.dumps(damaged))
        corrupt = self.pre(arguments={"command": "cat task.json", "workdir": str(workspace)})
        self.assert_denied(corrupt)
        self.assertIn("WorkspaceIntegrity", corrupt[1].get("hookSpecificOutput", {}).get("permissionDecisionReason", ""))

    def test_content_digest_mismatch_denies_before_any_business_change(self):
        self.prompt()
        self.pair()
        before = tree(self.project)
        event = self.event("PreToolUse", tool_name="Bash", tool_input={"command": "touch must-not-exist"})
        self.assert_denied(self.hook(event, "--expect-self-sha", "0" * 64))
        self.assert_denied(self.hook(event, "--expect-engine-sha", "0" * 64))
        self.assertEqual(tree(self.project), before)


if __name__ == "__main__":
    unittest.main()
