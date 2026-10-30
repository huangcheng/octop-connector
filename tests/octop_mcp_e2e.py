"""Octop Agent MCP 网关端到端测试：模拟 WorkBuddy 连接器的完整调用路径。

用法: python3 octop_mcp_e2e.py [base_url] [username] [password]
或设置环境变量 OCTOP_BASE_URL / OCTOP_USERNAME / OCTOP_PASSWORD
默认 base_url: http://127.0.0.1:8088
"""
import json
import os
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("OCTOP_BASE_URL", "http://127.0.0.1:8088")
USER = sys.argv[2] if len(sys.argv) > 2 else os.getenv("OCTOP_USERNAME", "")
PASS = sys.argv[3] if len(sys.argv) > 3 else os.getenv("OCTOP_PASSWORD", "")
if not USER or not PASS:
    sys.exit("missing credentials: pass [username] [password] or set OCTOP_USERNAME / OCTOP_PASSWORD")
MCP = BASE + "/api/mcp/agents"


def req(url, data=None, headers=None, timeout=60):
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


def main():
    # [1] 登录获取 access_token
    st, _, login = req(
        BASE + "/api/auth/login",
        {"username": USER, "password": PASS},
        {"Content-Type": "application/json"},
    )
    token = login.get("access_token", "")
    assert st == 200 and token, f"login failed: {st} {login}"
    print(f"[1] 登录: HTTP {st}, role={login.get('role')}, token len={len(token)}")

    auth = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    # [2] MCP initialize（streamableHttp，取 mcp-session-id）
    st, headers, resp = req(
        MCP,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "workbuddy-connector-e2e", "version": "1.0.0"},
            },
        },
        auth,
    )
    assert st == 200, f"initialize failed: {st} {resp}"
    info = resp["result"]["serverInfo"]
    session = headers.get("mcp-session-id", "")
    auth["mcp-session-id"] = session
    print(f"[2] initialize: HTTP {st}, protocol={resp['result']['protocolVersion']}, "
          f"server={info['name']}@{info['version']}, session={session[:10]}...")

    req(MCP, {"jsonrpc": "2.0", "method": "notifications/initialized"}, auth)  # 202 空响应体

    # [3] tools/list
    st, _, resp = req(MCP, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, auth)
    tools = [t["name"] for t in resp["result"]["tools"]]
    expected = ["list_octop_experts", "call_octop_expert", "resume_octop_expert"]
    assert st == 200 and tools == expected, f"tools/list mismatch: {tools}"
    print(f"[3] tools/list: HTTP {st}, tools={tools}")

    # [4] tools/call list_octop_experts
    st, _, resp = req(
        MCP,
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "list_octop_experts", "arguments": {}}},
        auth,
    )
    result = resp["result"]
    payload = result["structuredContent"]
    assert st == 200 and not result.get("isError"), f"list experts failed: {payload}"
    print(f"[4] list_octop_experts: HTTP {st}, count={payload['count']}")
    for expert in payload["experts"]:
        print(f"    - {expert['name']} | state={expert['state']} | "
              f"shared={expert['shared']} | model={expert['default_model']}")

    print("\n全部通过: 登录 -> initialize -> tools/list -> list_octop_experts 端到端 OK")
    return payload


if __name__ == "__main__":
    main()
