# v0.4.0 forced-hook validation — 2026-11-02

118 local regressions passed. The same four content-pinned command hooks were installed and marked trusted/enabled by the real desktop-bundled Codex 0.166.0-alpha.5.1. Native discovery alone is recorded separately from the execution acceptance below.

## What is forced

UserPromptSubmit synchronously records a real shared-engine context and standard intake assessment, without starting an experiment or storing the raw prompt. Intake is explicitly not semantic goal classification. PostToolUse validates actual native context/assessment results and stored engine facts for this turn/project. Business tools require that semantic receipt. A skip decision cannot start a run. Complex preparation is restricted until a bound run exists. Pending/failed reclassification, changed prompts, stale turns and corrupt receipts cannot keep old authorization. Stop checks all semantic scopes.

## Actual desktop execution

Seven fresh, ephemeral desktop app-server scenarios passed using the installed **same engine and gate bytes**, configured model `gpt-6.1-sol`, medium reasoning:

| Scenario | Observed result |
| --- | --- |
| New non-Git README-only edit | Intake, native context/assess/feedback; initial unassessed call denied; only README changed, no run |
| New non-Git code-only fix | Same native gate and actual refusal/recovery; existing check passed, no run |
| Existing Git project code-only fix | Actual refusal/recovery, same-project context, original legacy records and dirty sentinel unchanged; only target code changed |
| New complex non-Git project | Native complex assessment and bound start; premature preparation call denied; actual pwd in the verified baseline workspace succeeded without a nested project/run |
| Existing complex project | One earlier verified same-project/domain experience returned, then bound native start |
| Two actual fixture implementation failures | Same task key/failure streak retained, then bound native start |
| Startup injector absent and native service unavailable | Fallback intake still recorded; actual PreToolUse denied the call; business tree unchanged and no experiment |

The last row is an expected-denial test, not a completed user task. Three trigger scenarios were deliberately interrupted after start; they do not claim the synthetic parser/square projects were fully implemented. Full method iteration from v0.3 is documented separately.

The runtime is installed in the user's normal configuration and its four definitions were separately rechecked. Final execution tests used temporary **isolated Codex homes** with only those same four hooks. Normal signed-in CLI auth was reused via a private symlink, never copied, and temporary links were removed. This controlled configuration was necessary because an earlier strict-tree test in the normal profile failed when pre-existing memory/cache hooks created `.enola` files. That failure remains retained; assertions were not weakened and those unrelated hooks were neither changed nor removed globally. Coexistence metadata is audited separately; the plugin does not claim control over foreign hook side effects.

## Regression and integrity coverage

- Native result success/order, Pre/Post operation identity, missing/mismatched IDs and persistent pending state.
- Same-turn steering, new-turn and cross-project isolation; Stop cannot mask an unfinished scope with another project.
- Explicit denial of startup for skip, unbound/nested runs and unsafe preparation executors/rg flags/environment.
- Verified parent mapping for non-Git candidates and rejection of damaged contracts.
- Real gate/project-lock waits converted to explicit denial by the internal deadline before the host timeout.
- Privacy of intake, normal five-goal context, corruption preservation, older run support and validated-input closeout.
- Exact owned-hook trust, immutable runtime bundles, unrelated configuration preservation, conflict/concurrency handling and partial-install reporting.

A real v0.3.0 adopted run was also read using the v0.4.0 engine; validation stayed passed and original run state bytes were unchanged. Machine-readable path-free outcomes are in [validation-v0.4.0.json](validation-v0.4.0.json).

## Scope

These are supported local lifecycle/tool guards, not an OS sandbox or universal security guarantee. Existing write_stdin sessions do not re-enter PreToolUse; synchronous prompt intake records evaluation before continued model execution in a selected project. Hosted/specialized opt-outs, disabled/unrefreshed hooks, host process death and foreign hooks remain boundaries. Use an actual project directory with CODEX_HOME outside it and verify a fresh chat. See [official hook behavior](https://developers.openai.com/codex/hooks).
