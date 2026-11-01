# Method and upstream mapping

Source: https://github.com/google-research/harness2
Pinned commit: `1cfe254e8d25b15f37048c3730134686abe60335`.
Reviewed: 2026-11-01, Asia/Shanghai.

| Upstream | Local adapter |
|---|---|
| Fixed model, editable execution harness | The current Codex model/tools; fixed executor identity per run |
| INV and DOM proposals | One `general` and one `domain` instruction/tool-guidance candidate |
| Propose–Probe–Compose | Host executes task four times in isolated directories; tool runs real checks and retains artifacts |
| Composition with behavioral contrasts | Saved rationale with all three probe parents, followed by a new composed execution |
| Persistent per-domain improvement harness | Earlier project/domain lessons with full adopted harness, retrieved before later tasks |
| Evidence cache/resume | Contract, input, harness, artifact and log hashes; completed probes never replay |

Upstream references: `harness2/core/recursion.py`, `prompts.py`, `selection.py`,
`library.py`, and `docs/EXPERIMENTS.md`. No upstream runtime code is copied into
this adapter. The plugin uses the same method at a narrower editable surface.

Differences from upstream:

- This release supports one bounded `k=1` cycle. It does not implement full
  parallel/sequential `k>1` sweeps, the eight executable surface types, upstream
  benchmark adapters, model bridges or benchmark judging. Its two editable
  files are text guidance. The host interprets them under normal authorization.
- Upstream k=1 has four executor rollouts plus three improvement sessions and
  reflection. The adapter's authoring is handled by the host rather than paid
  nested model calls; checks alone do not count as executor rollouts.
- Upstream selection considers composed finals only, and k=1 adopts the sole
  final. This adapter adds a conservative baseline-retention option and a
  separate final validation. Those are local engineering additions, not a
  reproduction of the paper's selection procedure.
- Operational check results and the user's explicit completion requirements
  may inform this local workflow. Hidden ground-truth answers and benchmark
  grader feedback must stay out of the improvement context.
- Directory isolation is not an OS sandbox. Probe check processes inherit the
  host's environment/permissions; they run only caller-authorized argv without
  shell parsing. Runtime provides no external API or automatic model call.
- A single Codex host can retain prior context between sequential executions.
  Use independent authorized agents for stronger context isolation when useful;
  disclose same-host comparisons. No independence or model equality is proven
  solely by recording a caller-provided executor name.
- Reflection is local experimental data, not a user-confirmed global rule.
  Retrieval verifies retained evidence and excludes entries after the current
  run's creation time. Never change global/permanent memory automatically.

No benchmark gain or model-quality improvement is claimed by installing or
testing this plugin. Report actual task observations and their limits.
