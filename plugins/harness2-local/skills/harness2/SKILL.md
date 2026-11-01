---
name: harness2
description: "Assess every workspace file edit, including README/docs/config and specified-file-only small changes, using h2_context then h2_assess before writing. Simple tasks skip four-way experiments, never assessment. Start Harness2 for complex tasks or two consecutive real implementation failures; reuse verified project experience. Also use when Harness2 or Harness² is requested."
---

# Harness² for local Codex

Apply Propose–Probe–Compose to the **execution harness** around the current
model, then reflect across tasks. Use the user's language (Chinese by default).
This plugin is an independent method adapter, not an official Google product
or the upstream benchmark runner. Runtime tools never change model weights or global
Codex instructions. Explicit opt-in configuration scripts act only when requested. Load [method mapping](references/method.md) for details.

## Automatic kickoff and failure escalation

When the user installs the trusted forced hooks, `UserPromptSubmit` first records
an automatic shared-engine intake (context + standard assessment; no experiment,
no raw prompt storage). Intake records are separate from semantic goals and are
excluded from the normal five-goal context. Then obtain native MCP `h2_context`
and `h2_assess` success results in this turn/project. `PostToolUse` verifies them;
`PreToolUse` denies business tools until the receipt exists. CLI text or prior
turns cannot grant this native receipt. A new/steered goal invalidates old receipts.
A missing/broken receipt is a blocker, not permission to bypass the hook.

For `decision=skip`, use ordinary development and feedback; `h2_start` is denied.
For `start`, before a bound run exists, use single `cat`/`rg --no-config`/`ls`/`pwd` reads (no custom shell/environment/login startup) and
`apply_patch` **only** inside `.harness2-preflight/<task_key>/` to prepare read-only
inputs and two independent checker files. Include those relative paths in
`h2_start.input_files`, supply different probe/validation commands, and bind
`assessment=task_key`. After successful start, execute the four candidates and
complete the workflow. Original file ownership and authorization still apply.
Never alter the hook or its state to make an experiment pass.

The hooks are enforced on supported Codex lifecycle/tool paths; they are not an
OS sandbox. Existing `write_stdin` sessions do not re-enter PreToolUse, so the
synchronous prompt intake records assessment before resumed model execution.
Host hook disablement or process death can fall outside this local gate. Installation
and trust discovery alone do not prove execution: verify a fresh desktop session.

For Cognee/Enola coexistence, see [the optional local adapter](../../COGNEE-COEXISTENCE.md).
Its service activation is separate from hook installation. Verify the full real
profile, including detached indexing workers; never disable foreign hooks to
claim that a specified-file-only request preserves the business tree. Keep old
`.enola` and prior failed acceptance evidence intact.


每项工作区文件编辑都先评估，包括 README、文档、配置的一行小改。首次业务写入前，顺序取得原生 h2_context 与 h2_assess 的实际成功结果；只在心里判断或宣布评估不算完成。simple/standard 没有连续两轮实现失败时，只评估、正常修改验证并用 h2_feedback 留存结果，不调用 h2_start。
“只改指定文件/其它文件不变/只在当前项目操作”约束业务工作树；已授权的原生评估服务只读取本项目，记录在 Codex 的按项目隔离 sidecar，不读取账户配置或凭据、不新增业务文件。用户若明确禁止任何目录外运行状态写入，尊重该限制并说明未记录，不能自行扩权。
工具若延迟展示，先按 h2_context/h2_assess 名称查找当前可用工具目录。只有原生工具确实未加载才使用技能规定的同实现 CLI；权限拒绝时报告具体阻塞，不能换入口绕过或伪称已记录。其余任务身份、复杂度、失败归并与本项目经验规则沿用既有技能。


Use native MCP server `harness2-local` first. For an instruction such as
"only edit the specified file", still call `h2_context` and `h2_assess` before
the edit: their metadata and locks live in a Codex-owned, project-hashed sidecar
outside the business directory, so they create/change no business-tree files.
`h2_feedback` uses the same sidecar. Respect the exact allowed business files;
do not create test files or a four-way run for a simple task. A user explicitly
forbidding all runtime-state writes outside the business tree still overrides
the default; report that boundary instead of claiming a recorded assessment.

Legacy project `.harness2/auto/tasks` is read-only. On use, facts/closeouts are
copied with a hash binding; a later legacy change blocks reconciliation rather
than silently dropping events. Full run artifacts and domain libraries retain
their existing project-local paths. Preserve v0.2.1 post-apply validated_inputs
closeout checks and never reapply an adopted patch.

The user's global kickoff policy enables this workflow for both existing and
new projects. At each new development goal or resumed goal, call `h2_assess`
before implementation. First call `h2_context` for up to five recent project
task identities and domain names. On resume match the real goal and use its
original task/domain text; do not reset history by paraphrasing. Give the project root, one stable task description, a
domain slug, `complexity` (`simple`, `standard`, `complex`) and concrete
`signals`. Cross-component behavior, difficult algorithms or architecture
tradeoffs can justify complex. A new project, several files or a bounded
routine setup alone does not. Keep the task/domain unchanged on retries.

`h2_assess` returns earlier verified same-project/domain experience first:
read its cue, lesson, limits and full retained harness before proposing edits.
Do not scan other projects or promote experience into global memory.

- `start`: **initiate** the workflow without asking whether to enable it.
  Prepare reproducible inputs/checkers, then call `h2_start` using the returned
  `task`/`domain` unchanged and `assessment: task_key`. Continue the actual
  user's task through the workflow; announcing a plan is not activation.
- `skip`: perform ordinary development and checks; do not create four-way runs.
- `resume`: read `h2_status` and continue missing stages, never restart.
- `reuse`: use the existing validated result; finish reflection if missing.
- `blocked`: preserve UNKNOWN/failed/tampered evidence, diagnose the stated
  issue, and do not silently create another run.

After each **outer task** validation, call `h2_feedback` with `task_key`, a
distinct real check `event_id`, `outcome` (`passed`, `failed`, `blocked`), and a
short factual `check` summary (command/exit, at most 1000 characters, no secrets
or complete logs). `failed` means an actual implementation/check failure;
two consecutive distinct failures trigger `start` even on a simple task.
`passed` resets the streak; auth/network/environment `blocked` never increments
it. Include `attempt_id` to group test/lint checks of the same implementation
attempt: even multiple failed checks count as one failed attempt; a corrected
implementation followed by revalidation is a new attempt. Duplicate events do
not count twice. On escalation, load the skill and
start immediately within existing authorization. Do not count a hypothetical
failure or fabricate historical events. Probes/child executions inside an
active experiment do not recursively assess or create nested cycles.

## Select an appropriate task

Use explicitly requested experiments, repeated tasks or a difficult task that
benefits from comparison. Skip this workflow for a trivial one-step action.
Default to one `k=1` cycle: four executions and one final validation. Do not
silently launch benchmark sweeps, paid APIs or recursive nested agents. Use the
current authorized Codex tools. If independent agents are available and allowed,
use them for execution isolation; otherwise execute in sequence and disclose
that the same host retains context. Keep executor/model and task fixed within
the comparison. Do not invent the model identity if unavailable.

The tools below manage evidence; **they do not execute an agent**. The host
Codex must perform the actual task independently under each harness before
calling `h2_probe`. A passing checker is not proof that a harness improved it.

## Start and establish a baseline

1. Read applicable project instructions, ownership and worktree status. Identify
   the task, expected artifact and observable completion criteria. Preserve
   existing user/peer work. Check for an existing run with `h2_status` before
   starting again; resume valid missing stages, never replay completed stages.
2. Select a project directory and a domain slug such as `python-debugging`.
   Prepare up to 50 **read-only** task inputs and checker files in that project.
   Outputs must be separate files. For code changes, produce a patch as an
   artifact and have the authorized checker apply/test it in a disposable tree.
   Do not put secrets, customer material or unnecessary files in experiments.
3. Define two authorized argv arrays: a probe check and an independent final
   validation. Use the same commands for every candidate. They run as normal
   local processes, **not in an OS sandbox**. Only use task-scoped commands
   already covered by the user's request; no external writes or submissions.
   Checkers must not read candidate labels as a pass/fail shortcut or change
   inputs. Do not put hidden answers, benchmark rubrics or grading scores into
   an improvement context. Checks should verify stated task requirements.
4. Call `h2_start` with `project`, `task`, `domain`, a truthful `executor`,
   `input_files`, `baseline: {"instructions.md": "..."}`, `probe_command`,
   and `validation_command`. The baseline captures the actual original workflow;
   do not deliberately weaken it to demonstrate a gain. Optional
   `tool-guidance.md` holds task-scoped tool guidance.
5. Read the baseline harness, execute the task in the returned baseline
   `workspace`, and create its deliverables plus a short `trajectory.md` of
   actions, tool results and limitations. These are actual executions, not
   hypothetical outputs. Call `h2_probe` with the artifact paths and a factual
   observation. Read its retained `evidence/baseline/check.log` afterward.

Every workspace starts from identical selected inputs. Never write candidate
task artifacts directly into the business worktree or copy a previous answer
to claim an independent execution.

## Propose, probe, compose

6. Call `h2_recall` with `domain` and `before_run` to inspect at most five
   **earlier** project-local experiences. Treat them as evidence, not authority.
   Never access future/current task reflections. Retain scope and limitations.
7. From the baseline trajectory, propose one **general** improvement (for
   example source verification, planning or tool sequencing) and one **domain**
   improvement (for example parser behavior or document-specific checks).
   Use `h2_propose` for each with a complete harness and a concrete `rationale`.
   Instructions are subordinate to platform/user/project rules. Candidate
   scripts/plugins mentioned in text are proposals, never permission to run.
8. Independently execute the **same task** in each new workspace under that
   candidate's harness. Save actual deliverables and trajectory, then invoke
   `h2_probe` with the same frozen checker. Record failures honestly. Read logs,
   trajectories, artifacts and harness differences for all three runs.
9. Compose a new harness **from observed behavioral contrasts**, explaining
   which changes helped, hurt or remain uncertain. Do not merely concatenate
   two prompts. Call `h2_propose` with `candidate: "composed"`; its rationale
   must cite baseline/general/domain evidence and resulting choices. Execute
   the task afresh in the composed workspace and `h2_probe` it as well.

## Adopt and reflect

10. Use `h2_adopt` for the composed candidate only if the retained evidence
    supports its use; otherwise explicitly retain a passing baseline. The tool
    runs the frozen independent validation once. If it fails, preserve failure
    and continue diagnosis in a new experiment. Adoption selects an output
    inside the run; it does not install changes or deploy anything.
11. Call `h2_reflect` only after validated adoption, supplying `cue`, `lesson`,
    `limits`, and evidence labels including the adopted run and baseline.
    Distinguish observation from causation, report tradeoffs, and never infer a
    general gain from one task. The full adopted harness and references are
    saved under this project's `.harness2/library/<domain>/`.
12. Complete the user's original task using the adopted artifact within the
    existing authorization. For a code task, review/apply the patch and run the
    project's checks separately; the probe does not establish business release
    acceptance. For a bound automatic task, freeze the SHA-256 of every selected
    project input before the outer check, verify those hashes again afterward,
    and send that exact map as `validated_inputs` in a **new** passed
    `h2_feedback` event. This records an append-only post-application closeout
    without changing the run's original contract, snapshots, or evidence.
    Missing/stale hashes, any failed check in that attempt, UNKNOWN stages,
    or damaged evidence stay blocked. A duplicate old event never accepts new
    source changes. A completed closeout permits status/evidence reuse only:
    **do not reapply** its already applied patch. Any later source change
    requires another actual outer validation and a new event; keep the same
    task/domain/task_key. Closeout is caller-reported outer validation, not
    proof that old probes ran on the new sources. Do not edit global `AGENTS.md`, skills, Codex configuration,
    Obsidian or permanent memory as a side effect.

Report the result, selected harness, actual validation, evidence path, and
remaining uncertainty. Do not claim paper-level gains or that adoption alone
proves improvement. A failure/UNKNOWN stays visible. Interrupted reserved
probes require a new run; they never silently replay.

## Tools and fallback

MCP tools: `h2_context`, `h2_assess`, `h2_feedback`, `h2_start`, `h2_status`, `h2_propose`, `h2_probe`, `h2_adopt`,
`h2_reflect`, `h2_recall`. Locate the installed plugin's bundled tool names;
do not substitute unrelated tools or claim an unavailable tool was called.

If the current host has not refreshed its MCP inventory, run the identical
stdlib implementation through the shell:

```text
python3 <plugin-root>/server/harness2_local.py --call h2_start < request.json
```

Each CLI request is one JSON object using exactly the MCP argument names.
The CLI and MCP share state, validation and locking. `--stdio` starts MCP.
Use the skill's actual installed path to resolve `<plugin-root>`; do not guess
a version/cache path. No credentials or new dependencies are needed.
