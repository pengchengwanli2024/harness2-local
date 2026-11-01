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

- 每项开发目标先轻量评估；复杂任务或连续两轮实际实现失败时启动有界比较。
- 固定 `k=1`：最多四个候选执行，使用相同输入与检查命令。
- 同一目标沿用原 task/domain/task_key；同轮 test/lint 失败只计一次。
- 保留输入、执行指导、产物、日志、哈希、失败和中断证据，禁止静默重放。
- 独立最终验证后采纳组合方案，或在没有增益时保留通过的原方案。
- 经验仅保存在本项目 `.harness2/`，不会自动写入全局或永久记忆。
- v0.2.1 支持应用补丁后的显式验证收尾；未经验证的变更仍会阻断。

## 环境

- macOS 或 Linux，Python 3.10+；运行时只使用标准库，使用 POSIX 文件锁。
- 支持本地 plugins、skills 和 stdio MCP 的 Codex。
- Git 用于克隆；不需要 API Key、额外模型服务或后台守护进程。

Windows 原生运行未提供支持；可在受支持的 Linux 环境中使用。

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

安装插件本身不会修改全局开工规则。若你明确希望每个项目自动评估，可以先预览：

```bash
python3 plugins/harness2-local/scripts/configure_autostart.py \
  --evidence-dir ./local-policy-review
```

审阅生成的候选后，再决定是否用 `--apply` 写入。脚本会备份全局 AGENTS，
保留无关规则并检查并发修改；不要把包含个人规则的候选提交到公开仓库。

## 使用流程

1. `h2_context`：读取本项目最近目标和领域名，恢复原任务身份。
2. `h2_assess`：评估复杂度并返回同项目、同领域、早于本任务的可信经验。
3. 按需 `h2_start`：冻结输入、检查器和原始执行指导。
4. Codex 在隔离目录中实际执行任务，再通过 `h2_probe` 检查产物。
5. `h2_propose` 提出通用、领域和组合指导；每个候选重新执行，不能复制答案冒充独立执行。
6. `h2_adopt` 运行独立最终验证；`h2_reflect` 保存证据支持的项目内经验。
7. 主控审查并应用产物，运行项目原有检查，再报告外层验证结果。

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

当前包含56项回归，覆盖状态顺序、重放保护、路径/符号链接、失败与 UNKNOWN、
证据篡改、任务恢复、事件幂等、同轮失败归并、应用后收尾和旧版兼容。
测试使用临时项目和确定性检查器，不调用模型、远端服务或安装命令。

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
