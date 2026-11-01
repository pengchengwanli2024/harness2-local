# Harness² Local

面向本地 Codex 的 Harness² 方法插件，提供一个工作流技能与七个本地 MCP
工具，以及三个开工/失败跟踪工具。Python 3.11+，仅标准库，无 API Key、新模型服务或后台守护进程。

v0.3 支持严格编辑范围下的全局开工自动评估：本机显式安装开工规则后，已有和新建项目都会
先定位项目、恢复同一目标身份，再调用 `h2_assess`。复杂任务或连续两轮实际
实现验证失败时自动启动；简单任务执行正常开发，不创建四路实验。
优先读取本项目、同领域、早于当前目标的验证经验；保留旧版 v0.1 经验兼容。
同轮 test/lint 多项失败只计一次；通过清零，认证/网络阻塞不累计。

轻量评估、反馈和项目锁保存在业务目录之外：
`$CODEX_HOME/harness2-local/projects/<真实项目路径SHA-256>/`。
指定业务文件之外不新增 `.harness2` 或其它文件，simple 只评估、不启动实验。
旧项目的自动任务记录只读复制并绑定原字节哈希；旧客户端更新原记录时会阻断
并要求核对，不覆盖历史。完整实验与领域经验仍保留本项目 `.harness2/` 路径，
v0.2.1 的外层验证指纹收尾机制继续有效。

桌面原生 MCP 通过同一个服务器的用户级配置接入，避免依赖特定插件加载器对
本地 stdio 的发现行为。安装器只追加本服务，不重写其它 MCP 的字段：

```bash
python3 /path/to/plugin/scripts/register_native_mcp.py --codex-bin /path/to/desktop/codex --evidence-dir /path/to/evidence --apply
```

注册默认不改变审批策略。非交互会话如需授权，显式使用 `--approve-tools` 列出
已审阅的工具（简单任务为 `h2_context h2_assess h2_feedback`）；先预览再 `--apply`。
完整实验的其余七项需分别授权，probe/adopt 会执行调用者指定的本地检查命令。
只追加这些工具的 `approval_mode = "approve"`，保留已有显式策略，不放宽其它服务。
`--codex-bin` 仅用于报告，不启动 Codex 或证明连接成功。

该入口在 Codex 加载时启动同一标准库 stdio 服务，优先直接使用原生工具；
CLI 仅作未刷新会话的备用。`h2_context` 返回外置元数据路径便于核对。

需要稳定加载简短开工门控时，可选择原生 `developer_instructions` 入口：
先运行 `scripts/configure_session_gate.py --evidence-dir /path/to/evidence` 审阅，
再用 `--apply`。它把已审阅门控持久注入新会话，不需要每次在命令行覆盖指令；
仅修改自身标记块，已有他人 developer_instructions 时拒绝覆盖，并保留其它配置字节。
此入口和 AGENTS 仍依赖模型遵循指令，不是强制 hook；安装脚本不会自动授权工具。

v0.2.1 修复已采纳补丁落地后的收尾：应用补丁后先冻结本次选定输入的完整
SHA-256 映射，运行并通过原项目检查，确认这些指纹未变，再在新的 passed
`h2_feedback` 中提供 `validated_inputs`。工具追加 `auto/tasks/<task_key>.json`
中的 `closeouts` 记录，并将该验证后的输入作为当前源基线；原开工合同、
快照、探针、失败日志和验证证据不变。旧事件不能追认新源码，后续改动、
同轮失败、UNKNOWN 或证据篡改仍阻断。状态会明确提示补丁已应用，不要重复应用。
该收尾是主控报告的外层验证，不能称旧探针验证了新源码；兼容既有 v0.1/v0.2 run。

跨项目入口是 Codex 用户级 AGENTS 开工规则，按请求触发模型执行，不是后台
文件监控。原已打开对话不会被脚本强行改写上下文；新开会话加载更新配置。
配置脚本生成可审查候选并备份、保留原全局文件前缀，再原子写入：

```bash
python3 /path/to/plugin/scripts/configure_autostart.py --evidence-dir /path/to/evidence --apply
```

使用方式：在新 Codex 对话中选择 **Harness² Local**，或写：

> 用 Harness² 帮我优化这项任务：先跑原方案，再比较通用与领域候选，根据实际差异组合方案并验证，保留证据和适用经验。

流程：原方案执行 → 通用/领域方案及试跑 → 根据差异组合 → 重新执行组合方案
→ 独立验证并采纳/保留原方案 → 保存项目内经验供后续任务检索。

每次实验固定为 `k=1`，最多四个探针。Codex 负责实际完成任务；工具负责固定
条件、运行同一个检查命令、保留产物与日志。仅调用检查工具不算候选执行。
全局配置、业务文件、长期记忆均不由工具自动修改。

完整实验与领域经验保存在目标项目的 `.harness2/`；轻量记录与锁位于上述外置目录：

```text
.harness2/
  runs/<id>/state.json       # 固定条件、状态、失败及哈希
  runs/<id>/inputs/          # 选定的只读输入快照
  runs/<id>/harnesses/       # 四份执行指导
  runs/<id>/workspaces/      # 四个独立产物目录
  runs/<id>/evidence/        # 检查日志和产物副本
  runs/<id>/validation.log   # 最终独立验证
  library/<domain>/         # 有证据和适用边界的经验及完整 harness
```

输入与检查器是只读文件，输出应使用不同文件名。代码任务可先生成 patch，
由检查器在临时工作树应用并测试；最后由主 Codex 按原任务授权审查、应用。
不支持直接让四路候选修改同一个业务工作树。

检查命令是普通本地进程，没有 OS 沙箱；须限定在当前授权的项目检查范围。
工具使用 argv、超时、输出上限、文件哈希与互斥锁。目录隔离不代表权限隔离。
失败、超时和中断会保留；中断探针不会无声重跑。经验只用于当前项目和领域，
不写入 Obsidian 或 Codex 永久记忆，也不扫描用户的其它项目。

工具列表：`h2_context`、`h2_assess`、`h2_feedback`、`h2_start`、`h2_status`、`h2_propose`、`h2_probe`、`h2_adopt`、
`h2_reflect`、`h2_recall`。未刷新当前会话工具清单时可使用同实现 CLI：

```bash
python3 /path/to/plugin/server/harness2_local.py --call h2_status < request.json
```

`request.json` 例如 `{"project":"/absolute/project","run":"<run-id>"}`。

上游：[google-research/harness2](https://github.com/google-research/harness2)，
固定 commit `1cfe254e8d25b15f37048c3730134686abe60335`。
这是独立适配版，不是 Google 官方插件；仅实现 `k=1` 与提示/工具指导两个文本
表面，不包含论文的完整 benchmark 系统。采纳和检查通过不证明普遍性能提升。
详见 [方法映射](skills/harness2/references/method.md)。

卸载：`codex plugin remove harness2-local@harness2-local-marketplace`。
若已配置本插件自有原生服务，核对 command/args 仍指向本插件后，
在用户 config.toml 中只移除本服务段及其 tools 子段，保留其它配置原文。
部分 Codex 版本的 mcp remove 会重写其它服务字段，不应盲目使用。
卸载不会删除项目内实验记录；保留记录可审计，删除仅由用户另行决定。
