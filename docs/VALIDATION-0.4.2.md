# v0.4.2 gate reliability validation

Public release preparation: 2026-11-03. Local implementation and desktop
acceptance were performed on 2026-11-02. The installed build was
`0.4.2+codex.20261102`; public manifests use `0.4.2`. Gate and engine bytes are
identical; publication does not reinstall hooks or refresh existing chats.

## Changed behavior

- HOME and its ancestors, and CODEX_HOME and its ancestors/descendants, are
  rejected as project roots. A HOME-based chat can explicitly select a valid
  existing project, including when CODEX_HOME is outside HOME.
- Native Git calls require the repository root. Candidate calls require their
  verified bound parent project. Invalid identities are rejected before the
  engine creates metadata; ordinary commands may use verified subdirectories.
- Project-selection errors explain how to correct the directory while retaining
  the same goal. Runtime-file integrity, receipt integrity and timeouts have
  separate diagnostics. Unknown errors disclose stage/type only. Refusals remain
  fail closed and do not echo the original tool input or require reinstallation
  solely because validation failed.
- Lifecycle events include verified gate/engine SHA-256 fingerprints.

## Verification layers

The copied public source is checked again with the complete 143-test isolated
regression suite. This includes directory rejection and recovery, native root
identity, invalid receipt preservation, runtime hash refusal, private-input
redaction, original task identity and the existing start/skip/UNKNOWN contracts.
These tests use temporary projects and synthetic lifecycle events; they do not
stand in for desktop host interception.

The retained local installation evidence separately records:

- 143 source tests passed, with source hashes unchanged during the check.
- All 29 isolated hook tests passed against the exact installed content-pinned
  gate/engine files under Python 3.11.9. These are synthetic lifecycle events
  with real engine state, rather than native-host fault injection.
- Native installation listed all four owned hooks as trusted and enabled.
- Two fresh temporary desktop sessions used the new runtime fingerprints,
  completed native context then assessment, and ran ordinary commands. Their
  fixtures were unchanged and no four-way experiment was created. The actual
  global configuration was used; foreign hooks were not disabled.
- Foreign hooks, unrelated configuration, previous runtime bundles and original
  failure records were preserved. Installed plugin bytes matched local source.

## Retained failures and limits

The initial local suite had one timeout-diagnostic compatibility assertion
failure. Its original log remains; after correction, 143 tests passed.

Two combined model-driven checks requested an intentional HOME selection. Both
models selected a valid directory instead. Their strict combined results remain
**not passed**; the expected native-host bad-directory injection was not observed.
Their normal execution evidence is usable at that narrower scope. Invalid-scope
rejection, corrective recovery and tamper refusal were instead checked against
the exact installed files with deterministic isolated events. No further model
retries were used to turn those combined results into passes.

The maintenance chat still had its old hook snapshot immediately after the local
installation; fresh sessions loaded the new runtime. Existing chats need reload
or a new session. No application-wide restart or interruption of other chats was
performed. This release does not claim OS isolation, universal model-quality
improvement or a new production-business-project acceptance run.

Prior [Cognee coexistence](VALIDATION-0.4.1.md) and
[four-way activation](VALIDATION-FOURWAY-2026-11-02.md) reports remain unchanged;
they describe their original versions and tested configurations. This release's
regressions cover retained routing behavior, without presenting those older
desktop runs as new v0.4.2 four-way experiments.

See the [machine summary](validation-v0.4.2.json). Public artifacts contain no
private configuration, model traces, raw prompts or project execution history.
