# Local tool interface

Each request includes `project`, an existing absolute project directory. The
Python CLI and MCP use the same implementation and arguments. Python 3.11 or
newer is required, including the standard-library `tomllib` used by configuration
scripts. The server uses POSIX locks.

In v0.3, automatic task metadata and locks live in a Codex-managed, project-scoped
sidecar. Full experiment runs and experience libraries remain in the project's
`.harness2/`; lightweight assessment does not create or modify that business tree.

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

## Storage and legacy compatibility

The sidecar root is:

```text
$CODEX_HOME/harness2-local/projects/<sha256(real project path)>/
```

`CODEX_HOME` defaults to `~/.codex`. The key is the full SHA-256 of the resolved
absolute project path. `project.json` binds the namespace to that project;
`lock` coordinates calls, and `auto/tasks/<task_key>.json` holds task identities,
events, failure streaks and append-only closeouts. `h2_context`, `h2_assess` and
`h2_feedback` return `metadata_store` and `metadata_external: true`. These fields
identify the external namespace, not an experiment run directory.

The sidecar must be outside the business project. If the configured location
would fall inside it, calls are rejected rather than creating business files;
choose an external `CODEX_HOME`. Full runs, frozen snapshots, checked artifacts,
logs and `library/` remain under the original project's `.harness2/`.

Existing `.harness2/auto/tasks/<task_key>.json` records are copied on demand,
without changing or deleting their source. The copy retains events and closeouts
and binds the original legacy bytes with their SHA-256. A later legacy update,
missing source or integrity mismatch blocks access; histories are not silently
merged, overwritten or reset. Context combines sidecar and legacy identities,
returning at most five recent tasks for this project. An existing project
`.harness2/lock` is opened read-only and locked for old-client compatibility;
lightweight calls never create that project lock.

Old run and library files are not migrated or replayed. Run formats 0.1.0, 0.2.0,
0.2.1 and 0.3.0 remain readable subject to the same evidence and source checks.

## Assessment decisions

- `skip`: proceed with ordinary development; no four-way comparison.
- `start`: load the workflow and start one actual bounded comparison.
- `resume`: continue only missing stages of the bound run.
- `reuse`: retain verified results or complete closeout; read `reason` and
  `next_step`. A post-application closeout must not reapply the old patch.
- `blocked`: preserve failed/UNKNOWN/tampered evidence and diagnose it.

Assess every development goal, including edits limited to specified files.
`simple` and `standard` goals without two consecutive failed implementation
attempts continue ordinary development without `h2_start`. A complex goal needs
concrete `signals`; complex goals or two failed attempts select `start`.
Returning `start` does not itself create a run. The host must follow the workflow
within the original task scope; metadata recording is not a modification of the
specified business files and does not authorize other changes.

MCP initialization supplies kickoff instructions. Optional global kickoff rules
also guide the host, but automatic routing depends on model adherence, not
mandatory hooks. Registration, schema tests or a passing isolated fixture do not
prove every natural-language request will trigger correctly.

## Feedback identity

`outcome` is `passed`, `failed`, or `blocked`. `check` is a factual summary of
at most 1000 characters, without secrets or full logs. Use one `attempt_id` for
all checks against the same implementation; any failed check makes that attempt
failed. Correcting code and checking again is a new attempt. If omitted,
`attempt_id` defaults to `event_id` for compatibility. A passing attempt resets
the streak; external authentication, network or environment blockers do not
increment it. A later passing check cannot erase a failure in the same attempt.

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
to the automatic task metadata in the external sidecar; the original run files
are not changed. Existing v0.2.1 legacy closeouts retain their event and source
bindings when copied.
This binds the caller's outer-validation report. It does **not** assert that
old probes validated new source, and it does not deploy or release the project.

Any later source change, even reverting to the opening bytes, requires another
actual outer check and a fresh event. Old events cannot re-snapshot new files.
Corrupt evidence or closeout metadata remains blocked.

## Native stdio registration

The desktop can use a direct stdio entry in the user `config.toml`, under
`CODEX_HOME` or the default `~/.codex`. From the repository root, preview first:

```bash
python3 plugins/harness2-local/scripts/register_native_mcp.py \
  --codex-bin /path/to/desktop/codex --evidence-dir ./local-native-review
```

Review the generated candidate, then explicitly apply:

```bash
python3 plugins/harness2-local/scripts/register_native_mcp.py \
  --codex-bin /path/to/desktop/codex --evidence-dir ./local-native-review --apply
```

The script appends only `[mcp_servers."harness2-local"]`, using Python and the
bundled server's `--stdio` argument. It preserves unrelated original bytes,
including comments and unknown fields, and backs up the original config.
Conflicting ownership or transport settings, a managed config symlink, an
explicitly disabled owned entry, or a detected concurrent edit stop the write.
An enabled entry with the same command and arguments is idempotent.

`--codex-bin` is report metadata only: the script neither executes that path nor
verifies a live desktop connection. Open a new Codex conversation to refresh
registration and instructions, then inspect actual tool availability. Keep
personal configuration candidates and backups out of public source control.


## Forced lifecycle hooks (v0.4)

The ten tool APIs remain unchanged. `configure_forced_hooks.py` explicitly deploys
four synchronous command hooks and, with `--apply --trust`, trusts only hashes
returned for those exact definitions by the native host. Deployment metadata is
not execution acceptance; the installer reports that distinction.

Automatic intake uses the same context and assessment implementation with
`record_kind: hook-intake`, standard complexity and no experiment. It preserves
only a prompt hash/opaque identity; semantic native goals remain distinct. Normal
`h2_context` excludes intake entries while still returning up to five real goals.

Receipts and per-session locks are outside the business tree at
`$CODEX_HOME/harness2-local/hook-gates/<session-sha256>/<turn-sha256>.json`.
They bind project and native result order, detect corruption and never grant from
shell text. Reclassification marks a pending operation before execution; only its
matching successful Post can restore access. A changed prompt within the same
turn invalidates the old goal receipt. The hook's internal deadline emits an
explicit deny before the longer host timeout.

A start decision permits only bounded preparation under
`.harness2-preflight/<task_key>/` until a bound run exists. A skip decision cannot
start or execute an experiment. Verified candidate paths map to the original
project and run; unverified run identity fails closed. Actual validation feedback
for the same assessed task remains recordable before start/closeout.

A full code/engine update requires a new content-addressed runtime and explicit
trust review; old bundles are preserved. The existing legacy migration,
validated_inputs closeout and failure/UNKNOWN retention contracts continue.
