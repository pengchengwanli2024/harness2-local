# Contributing

讨论或提交修改前，请先阅读 README 与技能流程，说明可复现问题、预期行为和
实际检查结果。不要在 issue、PR、截图或测试中提交凭据、个人全局规则、项目
私有运行记录、客户数据或完整会话。

## 本地验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

测试必须使用临时目录。改状态或哈希逻辑时，需要覆盖失败、UNKNOWN、篡改、
重复事件和禁止重放；不能通过删除断言或改写原失败证据制造通过。

改插件版本时同步 `plugins/harness2-local/plugin.json`、
`plugins/harness2-local/.codex-plugin/plugin.json` 与服务版本；保留已支持的旧 run
格式。不要直接改已安装缓存；从源目录重新安装并验证实际 MCP 发现和调用。

新功能或方法变化请明确本地适配与上游的差异。确定性测试不算模型 benchmark，
检查通过不证明通用质量提升。项目维持一个有界 k=1 流程；不要默认增加付费调用、
后台守护进程或跨项目经验共享。
