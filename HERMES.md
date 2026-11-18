# Hermes 宿主安装说明

Hermes 没有 Codex 的生命周期钩子，也没有 plugin marketplace 清单；技能就是
`SKILL.md` + 同目录资源。安装 = 复制目录 + （可选）注册 MCP。

## 安装技能

```bash
mkdir -p ~/.hermes/skills/software-development/harness2
cp -R plugins/harness2-local/skills/harness2/. ~/.hermes/skills/software-development/harness2/
mkdir -p ~/.hermes/skills/software-development/harness2/server
cp plugins/harness2-local/server/harness2_local.py ~/.hermes/skills/software-development/harness2/server/
```

## 注册 MCP 服务器（推荐）

```bash
hermes mcp add harness2-local --command python3 \
  --args "$HOME/.hermes/skills/software-development/harness2/server/harness2_local.py" --stdio
```

成功标志：`✓ Connected! Found 10 tool(s)`（`h2_context` … `h2_recall`）→ 确认启用 10/10。

## 状态根（sidecar）

`server/harness2_local.py` 按 `HARNESS2_HOME` → `HERMES_HOME` → `CODEX_HOME` → `~/.codex`
的顺序解析宿主状态目录，Hermes 下默认落到 `~/.hermes/harness2-local/projects/<项目哈希>`，
仍然不写入业务工作树。

## 验证

```bash
cd plugins/harness2-local/skills/harness2   # 或在安装目录
echo '{"project":"<绝对项目路径>","task":"验证","domain":"hermes","complexity":"simple","signals":["docs"]}' \
  | python3 server/harness2_local.py --call h2_assess
```

回归测试（需要 Python 3.11+，`tomllib`）：

```bash
uv run --python 3.13 --with pytest pytest tests/ -q
```
