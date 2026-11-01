# Changelog

## 0.4.0 — 2026-11-02

- Add opt-in trusted synchronous UserPromptSubmit, PreToolUse, PostToolUse and Stop hooks.
- Record automatic privacy-preserving intake; require native per-turn/project semantic receipts before business tools.
- Deny experiment starts for skip goals, unbound/nested runs, stale/tampered receipts and incomplete reclassification.
- Restrict preparation commands; verify candidate workspace ownership and preserve multi-project completion checks.
- Add internal fail-closed lock deadlines and content-pinned runtime deployment with exact native trust review.
- Preserve existing hook handlers, unrelated configuration and older run/closeout evidence.
- Retain 0.3.0 run support and distinguish tool-path enforcement from an OS sandbox.

## 0.3.0 — 2026-11-02

- Move lightweight task metadata and project locks into
  `$CODEX_HOME/harness2-local/projects/<sha256(real project path)>/`, with
  `CODEX_HOME` defaulting to `~/.codex`. Context, assessment and ordinary feedback
  do not create or modify files in the business project.
- Keep full experiment runs and libraries in the project's original `.harness2/`.
  Copy legacy task metadata read-only, retain events and closeouts, bind its
  original bytes by SHA-256, and block later legacy changes. Open existing legacy
  locks read-only; do not create project locks for lightweight calls.
- Preserve v0.2.1 `validated_inputs` and append-only post-application closeout,
  including frozen-evidence checks and compatibility with older runs.
- Add kickoff MCP instructions covering edits limited to specified files,
  project context recovery and assessment before implementation. Automatic
  routing remains model-guided, not enforced by hooks or guaranteed for every
  natural-language request.
- Support direct native desktop stdio registration through user `config.toml`.
  The registration script previews before explicit application, appends only its
  owned section, preserves unrelated original bytes, and refuses conflicting
  ownership/transport, managed config symlinks and detected concurrent edits.
  `--codex-bin` is report metadata, not execution or live desktop verification.
- Add opt-in, named per-tool approval configuration; preserve existing explicit
  policies and other servers. Never grant blanket trust by default.
- Add a separately reviewed, opt-in developer session gate matching the tested
  instruction loading layer; preserve foreign developer instructions and all
  unrelated config bytes. This remains instruction-guided, not a forced hook.
- Require Python 3.11+ for standard-library `tomllib`; configure CI for 3.11 and
  3.13. Expand isolated storage and registration safety regressions without
  treating them as live desktop or natural-language acceptance.

## 0.2.1 — 2026-11-02

First public release of the local Codex adapter.

- Fix post-application closeout: a new passing outer-validation event can bind
  the complete, verified `validated_inputs` SHA-256 map.
- Preserve the original run contract, snapshots, artifacts, logs and failures.
- Keep unverified drift, stale/duplicate events, mixed failed attempts,
  UNKNOWN stages and damaged evidence blocked.
- Reject further source changes, including reverting to the original inputs,
  until another real outer validation is reported.
- Preserve compatibility with existing 0.1.0 and 0.2.0 runs.
- Include 56 deterministic regression tests and a POSIX CI workflow.

## 0.2.0

- Add project kickoff context, automatic assessment and implementation feedback.
- Escalate after two distinct implementation failures; group checks from the
  same implementation attempt.
- Restore stable task identity and retrieve verified earlier project experience.

## 0.1.0

- Add the bounded local baseline → general/domain → composed workflow.
- Retain frozen inputs, harnesses, checked artifacts, logs and hashes.
- Add independent validation, baseline retention and project-local reflection.
