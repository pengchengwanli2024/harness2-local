# Cognee / Enola coexistence

Cognee's local code-graph pipeline normally runs Enola inside the indexed
repository and reads `<repo>/.enola` again when loading edges. Both startup
indexing and Stop-hook refresh can therefore change files outside a requested
one-file edit, even when Harness² itself only writes external metadata.

The optional adapter redirects **generation and both snapshot readers** to a
project-hashed external cache. Cognee still receives the original repository
path: dataset selection, Data row identity, repository paths and freshness
fingerprints retain their original inputs. The source snapshot has the same
directory basename, so Enola's repository labels remain comparable. No original
`.enola`, Harness² record or failure artifact is deleted, migrated or rewritten.

## Install into an existing local Cognee runtime

Preview, review the output, then add `--apply` to the same command:

```bash
python3 plugins/harness2-local/scripts/configure_cognee_coexistence.py \
  --venv "$HOME/.cognee-plugin/venv" \
  --cache-root "$HOME/.cognee-plugin/enola-sidecars" \
  --evidence-dir ./local-cognee-review
```

This adds one owned `.pth` file to the selected venv. It references an immutable
adapter/config bundle under `$CODEX_HOME/harness2-local/cognee-runtime/` (default
`~/.codex`). It never edits Cognee package files, installed plugin caches,
credentials, model settings or hooks. The installer does not stop or start a
service. A running Cognee process must be restarted through its existing
supervisor at an agreed idle point before the adapter is active. Do not start a
second process against the same embedded graph database.

The adapter is loaded lazily only for Cognee's Enola module. It pins the exact
installed `enola.py` SHA-256. An incompatible upgrade blocks code indexing until
review/reinstallation; ordinary memory imports remain available. Rebuilding the
Cognee venv removes this optional installation, so reapply and reverify it.

## Storage and limits

`<cache-root>/projects/<sha256(real source path)>/<generation>/<source basename>/`
contains an independent regular-file copy and the generated `.enola`. Each
generation retains its manifest, hashes and passed/failed result; it is sealed
read-only after generation. No hardlinks or symlinks point back into business
files. The original `.git`, `.enola`, `.harness2`, dependencies, build caches and
recognized secret filenames are excluded. This is a bounded source-index view,
not a complete backup or a credentials scanner. Source code in these private
snapshots should receive the same access protection as the source repository.

Safe repository-local `mcp-arch.yaml` extraction settings are copied. Cluster
`repos`, repository overrides, custom output/history locations, executable
providers and symlink configuration are rejected instead of indexing a different
scope or falling back to writing the original tree. PyYAML is required only to
validate an existing YAML configuration; the core Harness² runtime remains
standard-library only. Native Windows is unsupported.

The reader mapping is scoped to the async indexing context. A pipeline that
loses that binding fails explicitly; it must never read an old original `.enola`
as the new result. Verify the actual installed Cognee pipeline after activation.
External snapshots omit Git metadata, so Git-related snapshot provenance can
differ. This adapter does not change direct standalone Enola invocations or
unrelated hook programs.

## Verify and rollback

Use the real Codex configuration with all existing hooks enabled. Test a new Git
project and an indexed existing project with an old `.enola`, comparing complete
business trees and old cache hashes/mtimes before and after startup, the task,
Stop and completed code-index refresh. Confirm native context/assessment before
editing, `decision=skip`, ordinary feedback, and no new Harness² run for simple
work. Discovery and isolated adapter tests alone are insufficient.

To remove the optional integration, remove only
`<venv site-packages>/harness2_cognee_external.pth`, then restart the service at an
agreed idle point. Keep all external snapshots and previous runtime bundles for
review. Upstream indexing will again write repository `.enola` after rollback.
