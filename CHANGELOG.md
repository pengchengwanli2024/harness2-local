# Changelog

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
