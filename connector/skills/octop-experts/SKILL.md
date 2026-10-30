---
name: octop-experts
description: 通过 Octop Agent MCP 网关调用 Octop 专家：列出专家、发起或继续隔离的专家对话、处理工具审批暂停。当用户提到 Octop、其 Octop 实例/专家，或需要推进一个 Octop 专家任务时使用。
---

# Octop 专家调用指南

## 概述

Octop 是腾讯云开源的自托管多智能体 AI 助手（本地或云端部署）。本连接器经其认证的 Agent MCP 网关（`<实例地址>/api/mcp/agents`，Streamable HTTP + JWT Bearer）调用**当前用户可见的专家**——写作、研究、运维、代码评审等专职 Agent。

**前置条件**：
- Octop 实例必须在线（本地 `octop run`、桌面端、或云端部署均可）
- 访问令牌必须有效（默认 24 小时过期）。收到 401 / `AUTH_FAILED` 时，引导用户重新调用 `POST /api/auth/login` 获取 `access_token` 并更新连接器凭证后重试

## 工具

### 1. list_octop_experts

无参数。返回 `{"experts": [...], "count": N}`，每个专家含：`expert_id`、`name`、`description`、`state`、`default_model`、`template_name`、`shared`。

用户没有指明具体专家时，先调用此工具；把候选专家的名称和描述呈现给用户选择。

### 2. call_octop_expert

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `expert_id` | string | 是 | 专家 ID（来自 list_octop_experts） |
| `message` | string | 是 | 任务内容，最长 100000 字符 |
| `thread_id` | string | 否 | 传入则继续该对话；**省略则开启新的隔离对话** |

返回：`{"status", "expert_id", "thread_id", "response", "error?", "approval?", "usage?"}`

- `status`：`completed`（回复在 `response`）/ `approval_required`（见下文审批流程）/ `failed`（读 `error.message`）
- **必须保存返回的 `thread_id`**：后续追问、补充材料、继续任务都要带上它
- **只调用 `state == "running"` 的专家**：`stopped` 状态的专家未加载进运行时，网关不会自动拉起，调用只会得到 `模型调用失败` 错误。遇到 `stopped` 专家时，换用同类 `running` 专家，或引导用户在 Octop 控制台打开该专家使其启动后再试

### 3. resume_octop_expert

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `expert_id` | string | 是 | 同上 |
| `thread_id` | string | 是 | 处于审批暂停的对话 |
| `decisions` | array | 是 | 1–16 个决策，与 `action_requests` 一一对应 |

每个 decision：`{"type": "approve"|"edit"|"reject"|"respond", "message"?, "edited_action"?}`

- `approve`：按原样放行该动作
- `edit`：放行修改后的版本，**必须**附 `edited_action` 对象
- `reject`：拒绝该动作
- `respond`：回答专家的提问，**必须**附非空 `message`

## 标准调用流程

1. 不确定用哪个专家 → `list_octop_experts`，让用户选
2. `call_octop_expert`（不带 `thread_id`）发起任务
3. 记录返回的 `thread_id`
4. `status == "approval_required"` → 向用户展示待批动作 → 按用户决定 `resume_octop_expert`
5. 用户追问同一任务 → `call_octop_expert`（带 `thread_id`）

## 审批处理（HITL，人工在环）

`status == "approval_required"` 时：

- 读 `approval.pending_id` 和 `approval.request`：
  - `action_requests`：待批动作数组，每项 `{name, args, description?}`（如 shell 命令、文件写入、外发消息）
  - `review_configs`：审核配置数组
- **禁止自动批准**。将每个动作的名称、参数、说明完整呈现给用户，由用户决定；尤其 shell 命令、删除/覆写文件、对外发送类动作必须逐条确认
- 专家发起提问（`action_requests` 中 `name == "ask_user_question"`）时，其 `args.questions` 含问题与选项：把问题转述给用户，用 `respond` 决策回答
- 恢复后可能**再次暂停**：循环处理直到 `completed` 或 `failed`

## 错误与恢复

| 现象 | 处理 |
|------|------|
| 401 / `AUTH_FAILED` | 令牌过期（默认 24h）→ 引导用户获取新 `access_token` 并更新连接器凭证 |
| `模型调用失败：'<expert_id>'` | **通常不是模型问题**，而是该专家处于 `stopped` 状态、未加载进运行时。改用 `state == "running"` 的同类专家，或让用户在 Octop 控制台启动该专家后重试 |
| 专家不存在 / 不可访问 | 重新 `list_octop_experts`，可能不在当前用户可见范围 |
| "expert is disabled" | 引导用户在 Octop 控制台启用该专家 |
| "thread is not accessible" / "only MCP-created threads..." | MCP 网关只能继续**经 MCP 创建**的对话，不能接入 Dashboard/CLI/IM 的历史会话 → 重新发起任务 |
| 专家调用未触发审批、命令直接执行 | Octop 实例的 HITL 可能未开启。审批暂停要求实例安全策略 `hitl.enabled=true`（且 `tool_guard.mode=require_approval` 时对中高风险命令生效）。引导用户在 Octop 控制台「安全设置」中开启后重试 |
| 超时 | 专家回合可能运行数分钟（连接器超时设为 300 秒）；提示用户耐心等待，或建议拆小任务 |
| `status == "failed"` | 读 `error.message` 向用户解释 |

## 确认规则（高风险操作）

以下情况必须在调用前获得用户明确同意：
- `decisions` 含 `approve`/`edit` 且动作涉及 shell 命令执行、文件删除或覆写、对外发送（邮件/IM 消息）
- 长时间任务（预期超过 1 分钟）前告知用户
- 用户未明确表态时，一律 `reject` 或继续询问

## 示例

新任务：

```json
call_octop_expert({
  "expert_id": "exp_01J...",
  "message": "帮我根据以下要点写一份本周工作周报：..."
})
```

继续对话（追问）：

```json
call_octop_expert({
  "expert_id": "exp_01J...",
  "message": "第二条展开写详细一点",
  "thread_id": "01JZZY..."
})
```

批准一个 shell 命令、拒绝一个文件写入：

```json
resume_octop_expert({
  "expert_id": "exp_01J...",
  "thread_id": "01JZZY...",
  "decisions": [
    {"type": "approve"},
    {"type": "reject", "message": "不要覆盖该文件"}
  ]
})
```
