# v0.4.1 coexistence validation — 2026-11-02

Implementation and local verification passed. **Shared-service activation and
new/existing Git-project full-profile acceptance remain pending.** The running
Cognee service has a live connection from another project and has not been
restarted. This document does not claim that installing the adapter activates
it in an existing server process.

- 137 isolated regression tests passed, including external snapshots, async
  reader bindings, source/cache isolation, retained generations, failure
  handling, actual import/distribution discovery, installation ownership,
  symlink/concurrent-change refusal and HOME-session gate boundaries.
- A new process in the actual installed Cognee 1.6.5 / Enola CLI 0.4.30 venv
  imported Cognee successfully and used the real generation function, binary,
  parser and snapshot-identity reader. Both original-path readers resolved the
  same external generation. Source bytes, modes, mtimes and old `.enola` stayed
  unchanged. This test made no model or database call.
- A real desktop app-server turn used the actual global Codex configuration,
  with all 14 discovered hooks trusted/enabled and no isolated CODEX_HOME or
  disabled foreign hook. A new non-Git README edit obtained native
  context/assess/feedback, returned skip, changed only README and never called
  h2_start. This does not establish Git startup/Stop indexing coexistence.
- The four updated Harness² hooks were installed and verified trusted/enabled;
  unrelated configuration and foreign hooks were preserved. The optional
  adapter was installed through its owned venv `.pth`; original Cognee package
  files, global AGENTS and existing Cognee environment settings were preserved.
- 20,049 prior local evidence files were hash-checked unchanged. Earlier v0.4
  real-profile `.enola` failures remain retained. A new-process import failure
  and immutable-runtime symlink issue discovered in this iteration were
  repaired, covered and retained as failures rather than rewritten as passes.

The existing indexed Git fixture is prepared with a real completed Cognee
baseline, an old `.enola`, a legacy Harness² record and dirty-work sentinel.
After coordinated service activation, verify it and a fresh Git fixture with
the real global hooks, wait for actual code-index completion, compare the whole
business trees and old cache hashes/mtimes, and verify preserved Data/repository
identity. No stable release tag is declared by this pending validation report.

See [machine summary](validation-v0.4.1.json) and
[installation, rollback and supported scope](../plugins/harness2-local/COGNEE-COEXISTENCE.md).
