<p align="center">
  <img src="connector/icon.svg" width="96" alt="Octop connector icon">
</p>

<h1 align="center">Octop × WorkBuddy 连接器</h1>

<p align="center">把 <a href="https://github.com/TencentCloud/Octop">Octop</a> 的专家（Agent）接入 WorkBuddy：列出专家、派发任务、多轮续话、处理工具审批。</p>

---

## 这是什么

[Octop](https://github.com/TencentCloud/Octop) 是腾讯云开源的自托管 AI 助手平台，内置多种「专家」（挂载了工具、技能、知识库的 Agent）。它自带 Agent MCP Gateway，暴露三个工具。本仓库是把该网关封装成 **WorkBuddy 市场连接器**的完整源码。

| 工具 | 作用 |
|------|------|
| `list_octop_experts` | 列出当前账号下可见的专家（含运行状态、模型、是否共享） |
| `call_octop_expert` | 向某个专家派发任务（新会话）；传入 `thread_id` 则继续已有对话 |
| `resume_octop_expert` | 恢复等待审批/输入的专家线程，支持 `approve` / `edit` / `reject` / `respond` 四种决策 |

## 连接方式

连接器使用 `streamableHttp` 直连 Octop 的 `/api/mcp/agents`，**一个连接器同时覆盖本地桌面端与云端实例**——地址和令牌由用户在连接时填写：

| 表单字段 | 说明 | 默认值 |
|----------|------|--------|
| 协议 `SCHEMA` | 本地签 `http`，云端 HTTPS 部署签 `https` | `http` |
| 实例地址 `OCTOP_HOST` | 不含协议头。端口可在 `~/.octop/config.json` 的 `port` 字段修改 | `127.0.0.1:8088` |
| 访问令牌 `OCTOP_ACCESS_TOKEN` | 登录接口返回的 `access_token` | — |

模板填充后等价于：

```json
{
  "type": "streamableHttp",
  "url": "http://127.0.0.1:8088/api/mcp/agents",
  "headers": { "Authorization": "Bearer <access_token>" },
  "timeout": 300000
}
```

> `timeout` 设为 300 秒：单个专家回合会同步执行多步工具调用，可能跑数分钟。

### 获取访问令牌

```bash
curl -X POST http://127.0.0.1:8088/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"你的用户名","password":"你的密码"}'
# 取返回 JSON 中的 access_token 字段
```

默认有效期 **24 小时**，过期后重新获取并在连接器表单里更新即可。

## 仓库结构

```
connector/                        # 连接器本体，提交 WorkBuddy 市场时只打包这个目录
├── connector-meta.json           # 名称、介绍、版本、示例话术
├── mcp.json                      # MCP Server 定义（streamableHttp + 占位符）
├── token-schema.json             # 连接表单字段
├── icon.svg                      # 图标（取自 Octop 官方 logo mark）
└── skills/octop-experts/
    └── SKILL.md                  # 给 AI 的使用说明：thread 管理、审批循环、错误恢复

tests/                            # 本地回归脚本，不随连接器提交
├── octop_mcp_e2e.py              # 登录 → initialize → tools/list → list_octop_experts
├── octop_mcp_call_expert.py      # 专家调用 + thread_id 续话验证
├── octop_mcp_approval.py         # HITL 审批全链路（含实例策略快照/自动还原）
└── refresh_workbuddy_token.py    # 刷新 ~/.workbuddy/mcp.json 里的 Bearer token
```

## 本地实测

脚本依赖 Python 3.9+，无需第三方包。凭证通过环境变量或命令行参数传入：

```bash
export OCTOP_BASE_URL=http://127.0.0.1:8088
export OCTOP_USERNAME=your-user
export OCTOP_PASSWORD=your-pass

python3 tests/octop_mcp_e2e.py           # 网关连通性与工具集
python3 tests/octop_mcp_call_expert.py   # 真实专家调用与多轮续话
python3 tests/octop_mcp_approval.py      # 审批流（会临时改实例策略，finally 中还原）
```

> 想把连接器接入本机 WorkBuddy 做界面实测，可把等价的 `streamableHttp` 条目写入 `~/.workbuddy/mcp.json` 后信任该自定义 MCP；`tests/refresh_workbuddy_token.py` 可一键续期 token。

## 已知限制

| 限制 | 说明 |
|------|------|
| 令牌 24h 过期 | Octop 目前无长效 Personal Access Token，需定期重新获取 |
| 仅 `running` 专家可调用 | `state=stopped` 的专家未加载进 harness，调用会失败——请先在 Octop 控制台启动 |
| 审批需实例开启 HITL | `hitl.enabled=false` 或 `tool_guard.mode=warn` 时工具直接执行，不会出现审批卡片 |
| 会话归属 | `thread_id` 仅能续 MCP 侧创建的会话，不能接管控制台里已存在的对话 |

## 状态

已提交 WorkBuddy 连接器市场审核（ID `oc_a77208de4ae19c72`，v1.0.0）。

## 相关链接

- Octop 项目：<https://github.com/TencentCloud/Octop>
- WorkBuddy 连接器开发规范：<https://open.workbuddy.cn/docs/connector>
