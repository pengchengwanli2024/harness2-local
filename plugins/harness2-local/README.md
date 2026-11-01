# Harness² Local

面向本地 Codex 的 Harness² 方法插件，提供一个工作流技能与七个本地 MCP
工具，以及三个开工/失败跟踪工具。Python 3.10+，仅标准库，无 API Key、新模型服务或后台守护进程。

v0.2 支持全局开工自动评估：本机显式安装开工规则后，已有和新建项目都会
先定位项目、恢复同一目标身份，再调用 `h2_assess`。复杂任务或连续两轮实际
实现验证失败时自动启动；简单任务执行正常开发，不创建四路实验。
优先读取本项目、同领域、早于当前目标的验证经验；保留旧版 v0.1 经验兼容。
同轮 test/lint 多项失败只计一次；通过清零，认证/网络阻塞不累计。

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

数据保存在目标项目的 `.harness2/`：

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
卸载不会删除项目内实验记录；保留记录可审计，删除仅由用户另行决定。
