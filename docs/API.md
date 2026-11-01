# Local tool interface

Each request includes `project`, an existing absolute project directory. All
state is stored under that project's `.harness2/`. The Python CLI and MCP use
the same implementation and arguments.

| Tool | Purpose | Additional inputs |
| --- | --- | --- |
| `h2_context` | Read up to five recent project task identities and domains | none |
| `h2_assess` | Assess kickoff and recall earlier verified experience | `task`, `domain`, `complexity`, `signals` |
| `h2_feedback` | Record an actual outer implementation-check result | `task_key`, `event_id`, `outcome`, `check`; optional `attempt_id`, `validated_inputs` |
| `h2_start` | Freeze one bounded k=1 comparison | `task`, `domain`, `executor`, `input_files`, `baseline`, `probe_command`, `validation_command`; optional `assessment` |
| `h2_status` | Verify and inspect retained run state | `run` |
| `h2_propose` | Retain a general/domain/composed harness | `run`, `candidate`, `harness`, `rationale` |
| `h2_probe` | Check actual independently produced artifacts | `run`, `candidate`, `artifacts`, `observation`; optional `timeout_seconds` |
| `h2_adopt` | Independently validate and select baseline/composed | `run`, `candidate`, `rationale` |
| `h2_reflect` | Save evidence-supported project-local experience | `run`, `cue`, `lesson`, `limits`, `evidence` |
| `h2_recall` | Read up to five earlier verified domain entries | `domain`; optional `before_run` |

The server's `tools/list` response is the machine-readable schema. No tool
executes an agent or switches its model. Probe and validation commands are argv
arrays, run as ordinary local processes within the existing task authorization.

## Assessment decisions

- `skip`: proceed with ordinary development; no four-way comparison.
- `start`: load the workflow and start one actual bounded comparison.
- `resume`: continue only missing stages of the bound run.
- `reuse`: retain verified results or complete closeout; read `reason` and
  `next_step`. A post-application closeout must not reapply the old patch.
- `blocked`: preserve failed/UNKNOWN/tampered evidence and diagnose it.

## Feedback identity

`outcome` is `passed`, `failed`, or `blocked`. `check` is a factual summary of
at most 1000 characters, without secrets or full logs. Use one `attempt_id` for
all checks against the same implementation; any failed check makes that attempt
failed. Correcting code and checking again is a new attempt.

An `event_id` is immutable. Repeating the exact event is idempotent; changing
its outcome, summary, attempt, or validation hashes is rejected.

## Post-application closeout

After applying an adopted patch to the actual project:

1. Read the bound run's `contract.inputs` path list.
2. Freeze the SHA-256 of every listed current project file.
3. Run the actual outer project checks and verify those hashes again.
4. Send a **new** passed `h2_feedback` event with that exact map as
   `validated_inputs`.

The map must contain 1–50 canonical relative file paths and lowercase 64-digit
SHA-256 strings. It must cover the complete selected input set and match the
current bytes. The run must be adopted with independent validation passed,
without UNKNOWN stages or a failed check in the outer attempt. All original
frozen evidence remains checked.

Successful closeout returns `reason: verified_post_apply_closeout` and
`source_baseline.kind: reported_outer_validation`. The new baseline is appended
to the automatic task metadata; the original run files are not changed.
This binds the caller's outer-validation report. It does **not** assert that
old probes validated new source, and it does not deploy or release the project.

Any later source change, even reverting to the opening bytes, requires another
actual outer check and a fresh event. Old events cannot re-snapshot new files.
Corrupt evidence or closeout metadata remains blocked.
