# Harness² Local for Codex

An independent, local-first Harness² method adapter for Codex: propose, probe, compose, validate, and retain project-scoped evidence.

[![Tests](https://github.com/pengchengwanli2024/harness2-local/actions/workflows/tests.yml/badge.svg)](https://github.com/pengchengwanli2024/harness2-local/actions/workflows/tests.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

用真实执行证据改进 Codex 工作流。插件提供一个技能和十个本地 MCP 工具，
固定比较原方案、通用候选、领域候选和组合方案，并保存验证结果与适用边界。

它是对 [Google Research Harness²](https://github.com/google-research/harness2)
方法的独立本地适配，不是 Google 官方插件，没有复制上游运行时代码。
不修改模型权重、不自动调用付费模型、不运行大型 benchmark，也不宣称普遍性能提升。

## 功能

- 启用开工规则后，每项开发目标先轻量评估，包括只改指定文件的小改；复杂任务或连续两轮实际实现失败时进入有界比较。
- 固定 `k=1`：最多四个候选执行，使用相同输入与检查命令。
- 同一目标沿用原 task/domain/task_key；同轮 test/lint 失败只计一次。
- 保留输入、执行指导、产物、日志、哈希、失败和中断证据，禁止静默重放。
- 独立最终验证后采纳组合方案，或在没有增益时保留通过的原方案。
- v0.3 将轻量任务元数据和锁移到 Codex 的项目隔离 sidecar，评估不改业务工作树；完整实验与经验仍保存在本项目 `.harness2/`。
- v0.4.1 提供可选 Cognee/Enola 外置快照适配器，保留真实项目和 dataset 身份，避免自动代码索引刷新业务目录中的 `.enola`。旧缓存与失败记录保留。
- 保留 v0.2.1 应用补丁后的显式验证收尾；未经验证的变更仍会阻断，不自动写入永久记忆。

## 环境

- macOS 或 Linux，Python 3.11+；运行时只使用标准库，配置脚本使用 `tomllib`，文件锁使用 POSIX 接口。
- 支持本地 plugins、skills 和 stdio MCP 的 Codex。
- Git 用于克隆；不需要 API Key、额外模型服务或后台守护进程。

Windows 原生运行未提供支持；可在受支持的 Linux 环境中使用。

Cognee/Enola 集成独立安装到已有本地 Cognee venv，使用其 Enola binary；存在
仓库 YAML 配置时还使用该环境的 PyYAML。它不改变直接运行的 Enola 命令。
见 [安装、服务激活和边界](plugins/harness2-local/COGNEE-COEXISTENCE.md)。

## 安装

```bash
git clone https://github.com/pengchengwanli2024/harness2-local.git
cd harness2-local
codex plugin marketplace add "$PWD"
codex plugin add harness2-local@harness2-local-marketplace
```

然后在新 Codex 对话中选择 **Harness² Local**，或明确调用
`harness2-local:harness2`：

> 用 Harness² 对当前任务做一次有界比较，保留原方案、失败证据、独立验证和适用边界。

### 原生 stdio MCP 注册

如果桌面端需要直接注册原生 MCP，可使用用户配置 `config.toml` 路径。
以下脚本只追加自己的 `[mcp_servers."harness2-local"]` 段，保留无关配置、
未知字段和注释的原有字节。先生成预览：

```bash
python3 plugins/harness2-local/scripts/register_native_mcp.py \
  --codex-bin /path/to/desktop/codex \
  --evidence-dir ./local-native-review
```

审阅候选后，明确应用：

```bash
python3 plugins/harness2-local/scripts/register_native_mcp.py \
  --codex-bin /path/to/desktop/codex \
  --evidence-dir ./local-native-review --apply
```

默认目标是 `~/.codex/config.toml`；设置 `CODEX_HOME` 时使用该目录中的配置。
脚本备份原配置，拒绝受管理的 config symlink、同名其他命令或冲突传输配置，
检测到并发内容变化时停止。相同命令和参数已启用时保持幂等，不擅自启用已禁用的项。
`--codex-bin` **仅作为报告 metadata**，脚本不启动该路径，不能据此证明桌面连接成功。
实际 stdio 服务由 Python 和捆绑 server 路径启动；应用后在新 Codex 对话中刷新并核对工具。
不要把包含个人配置的备份或审阅产物提交到公开仓库。

### 无人值守工具授权（可选）

注册服务不会默认放宽工具审批。若非交互会话返回
`MCP tool call requires approval, but approval policy is never`，先核对该实例的授权；
不要改成全局跳过审批。对于已审阅并明确授权的本地服务，可逐个工具预览配置：

```bash
python3 plugins/harness2-local/scripts/register_native_mcp.py \
  --codex-bin /path/to/desktop/codex --evidence-dir ./local-native-review \
  --approve-tools h2_context h2_assess h2_feedback
```

确认候选后，对同一命令增加 `--apply`。这仅追加列出工具的
`mcp_servers."harness2-local".tools.<tool>.approval_mode = "approve"`，不改变其它服务
或全局审批；已有显式策略会保留并阻断覆盖。简单任务只需要这三项。
完整自动实验还涉及 `h2_start h2_status h2_propose h2_probe h2_adopt h2_reflect h2_recall`，
需要分别明确授权；其中 `h2_probe` 和 `h2_adopt` 能执行调用者指定的本地检查命令，
应在审阅该服务和执行范围后再授权。工具授权不扩大业务任务的权限。

配置字段见 [Codex 官方配置参考](https://developers.openai.com/codex/config-reference)。

### 可选开工规则

安装插件或注册原生 MCP 本身不会修改全局开工规则。若你明确希望每个项目自动评估，可以先预览：

```bash
python3 plugins/harness2-local/scripts/configure_autostart.py \
  --evidence-dir ./local-policy-review
```

审阅生成的候选后，明确应用，并在新对话中加载规则：

```bash
python3 plugins/harness2-local/scripts/configure_autostart.py \
  --evidence-dir ./local-policy-review --apply
```

脚本会备份全局 AGENTS，保留无关规则并检查并发修改；不要把包含个人规则的候选
提交到公开仓库。自动门控依赖模型遵循规则和 MCP instructions，**不是强制 hooks**，
不保证每次自然语言请求都自动触发。当前对话不会因写入规则文件而自动刷新；
工具调用和实际执行证据仍需核对。

### 可选会话门控

当较长的 AGENTS 未被稳定执行时，可将同一简短门控配置为 Codex 原生
`developer_instructions`，让每个新会话加载；无需每次传命令行覆盖：

```bash
python3 plugins/harness2-local/scripts/configure_session_gate.py \
  --evidence-dir ./local-policy-review/session-gate
```

审阅 `developer-gate.candidate.md` 后，对同一命令增加 `--apply`。脚本只管理前端
`HARNESS2_DEVELOPER_GATE` 标记块，保留其它配置原字节和字段，备份原文件；
已有其它所有者的 `developer_instructions` 或歧义标记时拒绝覆盖。此步骤不改变工具审批。
它是附加指令，仍受平台和用户授权约束，仍不是强制 hook；新对话需验证真实调用。

## 强制开工门禁（v0.4，可选安装）

v0.3 的 AGENTS/会话指令依赖模型遵循；v0.4 增加实际生命周期 hooks。
先完成上面的原生 MCP 注册及已审阅工具授权，再预览四项门禁：

```bash
python3 plugins/harness2-local/scripts/configure_forced_hooks.py \
  --codex-bin /path/to/desktop/codex --evidence-dir ./local-policy-review/forced-hooks
```

审阅自有脚本、哈希和候选后，对同一命令增加 `--apply --trust`。
安装器通过实际 `hooks/list` 读取四个自有定义的 `currentHash`，只更新对应的
`hooks.state.<key>.trusted_hash`，再次核验 trusted/enabled；不跳过 hook 信任。
其它 hooks 的 handler 内容与顺序保留，无关 TOML 原文不重写；检测到并发变化停止。
两文件部署不是跨文件事务，报告会保留部分安装状态。`verified_active` 只证明发现与信任，
`execution_verified` 不会据此置真；请开新会话验真实执行。

- `UserPromptSubmit` 同步执行共享引擎的 context/standard intake 评估，记录在项目外；
  不保存原始 prompt、不创建实验。Intake 不替代真实目标的语义复杂度评估，也不进入最近五个目标。
- 模型随后通过原生 MCP 成功调用 `h2_context → h2_assess`；`PostToolUse` 复核实际结果、
  项目、顺序与引擎记录，生成当轮回执。CLI 打印或旧轮次结果不能冒充回执。
- `PreToolUse` 在回执缺失、待处理、损坏或超时时显式拒绝业务工具；不是只输出提示。
  `skip` 任务不能调用 `h2_start`，同轮中途换目标和新轮次都不能沿用旧授权。
- `start` 前只允许受限单条读取或用 `apply_patch` 写
  `.harness2-preflight/<task_key>/` 准备输入及两个独立检查器，随后必须绑定 `assessment=task_key`。
  简单任务不创建该目录。已验证候选目录映射回父项目与同一 run，禁止嵌套实验。
- `Stop` 校验本轮涉及的语义目标，不能用另一个已评估项目掩盖尚未评估的目标。
  真正的失败、UNKNOWN 和已验证补丁收尾规则继续有效。

门禁和引擎部署为按内容哈希命名的固定副本，运行时再次核对两个文件。
更新插件后应重新运行安装／信任并新开会话；不要直接改已部署副本。
本版在桌面捆绑 Codex `0.166.0-alpha.5.1` 实测，需要支持对应生命周期和 `hooks/list` 的宿主。
使用明确的 Git 根目录或非 Git 项目目录，且 `CODEX_HOME` 必须在业务项目之外。

这是受支持 Codex 工具路径上的门禁，**不是 OS 安全沙箱**。已有 `write_stdin` 会话
不会再次触发 Pre；同步 prompt intake 在模型继续前记录轻量评估。hosted/部分专用路径、
关闭 hooks、旧的未刷新会话或宿主进程被杀，不属于完整强制边界。其它插件自己的 hook
副作用也不由本插件控制。实际验证范围与失败保留见 [v0.4 验证](docs/VALIDATION-0.4.0.md)。

## 存储与迁移

`h2_context`、`h2_assess`、普通 `h2_feedback` 以及应用后 closeout 的任务记录写入：

```text
$CODEX_HOME/harness2-local/projects/<sha256(real project path)>/
  project.json          项目身份
  lock                  外部项目锁
  auto/tasks/           目标、事件、失败计数和追加收尾记录
```

`CODEX_HOME` 默认 `~/.codex`；项目按解析后的真实绝对路径隔离。轻量接口返回
`metadata_store` 和 `metadata_external: true`，不会为了评估在业务目录新建 `.harness2`。
若 sidecar 本身落在业务项目内部，工具会拒绝；请使用项目外的 `CODEX_HOME`。
完整实验的 run、快照、日志、产物和项目经验 library 仍保留在原项目 `.harness2/`，
只有真正启动实验才需要写入这些实验目录；评估返回 `start` 本身不创建实验。

旧版 `.harness2/auto/tasks/` 按需只读复制到 sidecar，保留原 events 和 closeouts，
并记录 legacy 源文件原字节的 SHA-256。之后 legacy 源变化会阻断，需显式核对两份历史；
不会自动覆盖或丢弃任一方事实。已有 `.harness2/lock` 只读获取同一锁以兼容旧客户端，
不会为轻量调用新建项目锁。旧 run/library 不迁移、不重放。

## 使用流程

1. `h2_context`：读取本项目最近目标和领域名，恢复原任务身份。
2. `h2_assess`：评估复杂度并返回同项目、同领域、早于本任务的可信经验。
3. 按需 `h2_start`：冻结输入、检查器和原始执行指导。
4. Codex 在隔离目录中实际执行任务，再通过 `h2_probe` 检查产物。
5. `h2_propose` 提出通用、领域和组合指导；每个候选重新执行，不能复制答案冒充独立执行。
6. `h2_adopt` 运行独立最终验证；`h2_reflect` 保存证据支持的项目内经验。
7. 主控审查并应用产物，运行项目原有检查，再报告外层验证结果。

`simple`/`standard` 且未连续两轮独立实现验证失败时仅评估，继续普通开发，
不调用 `h2_start`。复杂任务或两轮失败才进入实验；原任务范围、指定文件约束、
项目所有权和发布门禁继续优先，不能由评估扩大授权。轻量 metadata 记录不是修改指定业务文件。

这些工具负责状态和检查，**不会替你执行智能体**。只有运行检查器不算候选执行。
目录隔离也不是 OS 沙箱；检查命令仍须遵守当前任务授权。

### 应用补丁后收尾

不要为了收尾覆盖原始哈希。应用补丁后，冻结所有选定输入的 SHA-256，运行并通过
真实项目检查，确认检查后指纹相同，再用一个新的 passed `h2_feedback` 事件提交
完整 `validated_inputs` 映射。

只有 run 已 adopted、独立验证 passed、无 UNKNOWN、原冻结证据完整、该 attempt
没有 failed，才会追加收尾基线。它明确标为 `reported_outer_validation`，不代表
旧探针验证过新源码。旧事件不能追认新源码；后续改动或回退仍需重新验证。
已经落地的补丁不要重复应用。

详见 [工具接口](docs/API.md)、[技能流程](plugins/harness2-local/skills/harness2/SKILL.md)
与 [方法映射和限制](plugins/harness2-local/skills/harness2/references/method.md)。

## CLI 备用入口

若当前对话尚未刷新 MCP 工具，可调用相同实现：

```bash
python3 plugins/harness2-local/server/harness2_local.py --call h2_context <<'JSON'
{"project":"/absolute/path/to/your/project"}
JSON
```

也可用 `--stdio` 启动 MCP 服务。协议输出只写 stdout，具体配置见
[mcp.json](plugins/harness2-local/mcp.json)。

## 测试

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

回归覆盖状态顺序、重放保护、路径/符号链接、失败与 UNKNOWN、证据篡改、任务恢复、
事件幂等、同轮失败归并、应用后收尾、sidecar 迁移、业务树完整性及原生配置安全。
测试使用隔离的临时项目、`CODEX_HOME` 和确定性检查器，不调用模型或远端服务。
配置测试会运行真实注册脚本，但只针对临时配置；它不等同于原生桌面或自然语言触发验收。
CI 配置检查 Python 3.11 和 3.13，具体通过结果以实际运行记录为准。

v0.3 的真实四路迭代、六类原生触发验收与限制见
[验证记录](docs/VALIDATION-0.3.0.md)。

## 仓库内容

```text
.agents/plugins/marketplace.json   本地 marketplace
plugins/harness2-local/            技能、MCP服务、配置与许可证
tests/                            临时项目回归测试
docs/API.md                       工具与收尾接口
CHANGELOG.md                      版本记录
```

公开仓库不包含本机配置、项目运行记录、个人记忆、私有验证材料或上游研究副本。

## 许可与来源

采用 [Apache License 2.0](LICENSE)，署名与方法来源见 [NOTICE](NOTICE)。
参考上游固定提交 `1cfe254e8d25b15f37048c3730134686abe60335`；本地适配范围见
[UPSTREAM.json](plugins/harness2-local/UPSTREAM.json)。

贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。
