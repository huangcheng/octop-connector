#!/usr/bin/env python3
"""Test the full HITL approval loop end-to-end via MCP.

Safely flips instance policy (hitl.enabled + tool_guard.mode) and ALWAYS
restores the original policy in finally, even on failure.
Task is harmless: create + `mv` rename a temp file (trips TOOL_CMD_DANGEROUS_MV, HIGH).
"""
import json
import os
import sys
import urllib.request

BASE = os.getenv("OCTOP_BASE_URL", "http://127.0.0.1:8088")
MCP = BASE + "/api/mcp/agents"
SEC = BASE + "/api/admin/security"
USERNAME = os.getenv("OCTOP_USERNAME", "")
PASSWORD = os.getenv("OCTOP_PASSWORD", "")
if not USERNAME or not PASSWORD:
    sys.exit("missing credentials: set OCTOP_USERNAME / OCTOP_PASSWORD")


def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                               headers=headers or {}, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=280)
        body = resp.read().decode()
        return resp.status, dict(resp.headers), (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, dict(e.headers), (json.loads(body) if body.strip() else {})
        except Exception:
            return e.code, dict(e.headers), {"raw": body[:300]}


def main():
    _, _, login = req(BASE + "/api/auth/login", {"username": USERNAME, "password": PASSWORD},
                      {"Content-Type": "application/json"})
    H = {"Authorization": "Bearer " + login["access_token"],
         "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}

    # ---- snapshot current policy ----
    st, _, pol = req(SEC, headers=H)
    if st != 200:
        print(f"cannot read security policy: {st} {pol}"); sys.exit(1)
    orig_hitl = pol["hitl"]
    orig_guard = pol["tool_guard"]
    print(f"[0] policy snapshot: hitl={orig_hitl} tool_guard={orig_guard}")

    # ---- MCP session ----
    _, hd, _ = req(MCP, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "wb-test", "version": "1.0.0"}}}, H)
    H["mcp-session-id"] = hd.get("mcp-session-id", "")
    req(MCP, {"jsonrpc": "2.0", "method": "notifications/initialized"}, H)

    seq = [2]

    def call(name, args):
        st_, _, r = req(MCP, {"jsonrpc": "2.0", "id": seq[0], "method": "tools/call",
                               "params": {"name": name, "arguments": args}}, H)
        seq[0] += 1
        res = r["result"]
        return res.get("structuredContent") or res

    # find the coach expert (known to actually execute shell/python)
    experts = call("list_octop_experts", {})["experts"]
    coach = next(e for e in experts if "教练" in e["name"] and e["state"] == "running")
    eid = coach["expert_id"]
    print(f"[1] target: {coach['name']} ({eid[:8]}...)")

    ok = False
    try:
        # ---- flip policy: HITL on + tool_guard require_approval ----
        st, _, _ = req(SEC, {"hitl": {"enabled": True},
                             "tool_guard": {"enabled": True, "mode": "require_approval"}},
                       H, method="PUT")
        if st != 200:
            print(f"[2] policy flip FAILED: {st}"); sys.exit(1)
        print("[2] policy flipped: hitl.enabled=true, tool_guard=require_approval")

        # ---- fire harmless flagged task ----
        res = call("call_octop_expert", {"expert_id": eid,
            "message": "请执行：先创建空文件 /tmp/octop_approval_a.txt，然后用 mv 把它重命名为 /tmp/octop_approval_b.txt，最后告诉我重命名是否成功。"})
        print(f"[3] call_octop_expert: status={res['status']} thread={res.get('thread_id','')[:16]}...")
        if res["status"] == "completed":
            print(f"    no approval triggered; response: {res['response'][:200]}")
            print("    => HITL policy not honored on MCP path — flag as Octop issue")
            return
        if res["status"] != "approval_required":
            print(f"    failed: {res.get('error', {})}"); return

        ap = res["approval"]
        actions = ap["request"]["action_requests"]
        print(f"[4] approval_required: pending_id={ap['pending_id'][:16]}...")
        for i, ar in enumerate(actions):
            print(f"    action[{i}]: {ar['name']} args={json.dumps(ar.get('args', {}), ensure_ascii=False)[:120]}")

        # ---- approve ----
        res2 = call("resume_octop_expert", {"expert_id": eid, "thread_id": res["thread_id"],
                                             "decisions": [{"type": "approve"} for _ in actions]})
        print(f"[5] resume_octop_expert(approve): status={res2['status']}")
        if res2["status"] == "completed":
            print(f"    expert replied: {res2['response'][:300]}")
            ok = True
            print("\n>>> APPROVAL LOOP FULLY VERIFIED: call -> approval_required -> resume(approve) -> completed")
        elif res2["status"] == "approval_required":
            print(f"    paused again (multi-step): {[ar['name'] for ar in res2['approval']['request']['action_requests']]}")
        else:
            print(f"    failed: {res2.get('error', {})}")
    finally:
        # ---- restore policy no matter what ----
        st, _, p2 = req(SEC, {"hitl": orig_hitl, "tool_guard": orig_guard}, H, method="PUT")
        now_hitl = p2.get("hitl") if st == 200 else "?"
        now_guard = p2.get("tool_guard") if st == 200 else "?"
        print(f"[6] policy restored (http {st}): hitl={now_hitl} tool_guard={now_guard}")


if __name__ == "__main__":
    main()
