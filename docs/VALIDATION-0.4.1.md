# v0.4.1 coexistence validation — 2026-11-02

Implementation, local verification, shared-service activation and new/existing
Git-project full-profile acceptance passed. The user approved a bounded restart
after the shared-service connection check. The old process and four children
exited before a replacement started on the same port with the original launch
environment. Health and authenticated reads passed; environment file bytes and
permissions stayed unchanged. No Cognee package upgrade was performed.

- 137 isolated regression tests passed, including external snapshots, async
  reader bindings, source/cache isolation, retained generations, failure
  handling, actual import/distribution discovery, installation ownership,
  symlink/concurrent-change refusal and HOME-session gate boundaries.
- A new process in the actual installed Cognee 1.6.5 / Enola CLI 0.4.30 venv
  imported Cognee successfully and used the real generation function, binary,
  parser and snapshot-identity reader. Both original-path readers resolved the
  same external generation. Source bytes, modes, mtimes and old `.enola` stayed
  unchanged. This test made no model or database call.
- Three real desktop app-server turns used the actual global Codex configuration,
  with all 14 discovered hooks trusted/enabled and no isolated CODEX_HOME or
  disabled foreign hook. Each obtained native context/assess/feedback, returned
  skip and never called h2_start:

  | Project | Actual change | Result |
  | --- | --- | --- |
  | New non-Git project | README only | Passed |
  | New Git project | arithmetic.py only; existing check passed | Passed |
  | Existing indexed Git project | arithmetic.py only; existing check passed | Passed; old Harness² evidence and dirty work retained |

  The two Git cases also completed actual Cognee code-index pipelines. Fresh
  external generations were observed for both real project paths. Full business
  trees were compared again **after pipeline completion**, with the same single
  allowed edit and no new repository `.enola`. Existing `.enola` bytes, modes and
  mtimes stayed unchanged. Each dataset retained one Data row; the existing
  Data ID and CodeRepository ID were preserved, both repository paths remained
  the actual source paths, and freshness fingerprints matched the final source.
- The four updated Harness² hooks were installed and verified trusted/enabled;
  unrelated configuration and foreign hooks were preserved. The optional
  adapter was installed through its owned venv `.pth`; original Cognee package
  files, global AGENTS and existing Cognee environment settings were preserved.
- 20,049 prior local evidence files were hash-checked unchanged. Earlier v0.4
  real-profile `.enola` failures remain retained. A new-process import failure
  and immutable-runtime symlink issue discovered in this iteration were
  repaired, covered and retained as failures rather than rewritten as passes.

The existing indexed Git fixture started from a real completed Cognee baseline,
an old `.enola`, a legacy Harness² record and a dirty-work sentinel. These were
retained rather than replacing the old failure controls. Post-restart read-only
inspection found one service listener and database holders belonging only to the
replacement and its child. The maintenance chat resumed through its normal
SessionStart lifecycle; other sessions were not impersonated or force-registered.

This verifies the tested installed Cognee 1.6.5 / Enola CLI 0.4.30 and supported
Codex lifecycle paths. It does not cover every third-party hook, direct standalone
Enola calls, OS-level isolation or untested package upgrades. An incompatible
async pipeline loses its snapshot binding explicitly rather than falling back
to an old business-tree cache. Git metadata is omitted from external snapshots.

See [machine summary](validation-v0.4.1.json) and
[installation, rollback and supported scope](../plugins/harness2-local/COGNEE-COEXISTENCE.md).
