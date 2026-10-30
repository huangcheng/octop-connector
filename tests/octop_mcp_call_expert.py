"""Octop Agent MCP 网关 call_octop_expert 实测：向通用专家发送一句话并取回响应。"""
import json
import os
import urllib.request

BASE = os.getenv("OCTOP_BASE_URL", "http://127.0.0.1:8088")
MCP = BASE + "/api/mcp/agents"
_USERNAME = os.getenv("OCTOP_USERNAME", "")
_PASSWORD = os.getenv("OCTOP_PASSWORD", "")


def req(url, data=None, headers=None, timeout=180):
    r = urllib.request.Request(
        url, data=json.dumps(data).encode() if data else None, headers=headers
    )
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        body = resp.read().decode()
        return resp.status, dict(resp.headers), (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, dict(e.headers), (json.loads(body) if body.strip() else {})


def tool_call(auth, call_id, name, arguments, timeout=180):
    payload = {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    return req(MCP, payload, auth, timeout=timeout)


def main():
    _, _, login = req(
        BASE + "/api/auth/login",
        {"username": _USERNAME, "password": _PASSWORD},
        {"Content-Type": "application/json"},
    )
    auth = {
        "Authorization": f"Bearer {login['access_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    _, headers, _ = req(
        MCP,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "workbuddy-connector-e2e", "version": "1.0.0"}}},
        auth,
    )
    auth["mcp-session-id"] = headers.get("mcp-session-id", "")
    req(MCP, {"jsonrpc": "2.0", "method": "notifications/initialized"}, auth)

    # 找到「通用专家」的 expert_id
    st, _, resp = tool_call(auth, 2, "list_octop_experts", {})
    expert = next(e for e in resp["result"]["structuredContent"]["experts"]
                  if e["name"] == "通用专家")
    print(f"目标专家: {expert['name']} ({expert['expert_id']}) state={expert['state']}")

    # 真实调用一次（新对话）
    st, _, resp = tool_call(auth, 3, "call_octop_expert", {
        "expert_id": expert["expert_id"],
        "message": "连接器链路测试，请只回复四个字：链路正常",
    })
    payload = resp["result"]["structuredContent"]
    print(f"[5] call_octop_expert: HTTP {st}, status={payload['status']}, "
          f"thread_id={payload['thread_id'][:12]}...")
    print(f"    response: {payload['response'][:200]!r}")
    if payload.get("usage"):
        print(f"    usage: {payload['usage']}")

    # 用同一个 thread_id 追问，验证会话延续
    st, _, resp = tool_call(auth, 4, "call_octop_expert", {
        "expert_id": expert["expert_id"],
        "message": "我上一句让你回复哪四个字？",
        "thread_id": payload["thread_id"],
    })
    payload2 = resp["result"]["structuredContent"]
    print(f"[6] 续话验证: HTTP {st}, status={payload2['status']}, "
          f"thread 与上一次一致: {payload2['thread_id'] == payload['thread_id']}")
    print(f"    response: {payload2['response'][:200]!r}")
    print("\n全部通过: 专家调用 + thread 会话延续 OK")


if __name__ == "__main__":
    main()
