"""重新登录 Octop 并更新 ~/.workbuddy/mcp.json 里的 Bearer token。

Octop 的 access_token 默认 24 小时过期，过期后 WorkBuddy 调用会返回 401。
运行本脚本即可用最新 token 更新 WorkBuddy 的自定义 MCP 配置。

用法: python3 refresh_workbuddy_token.py [base_url] [username] [password]
或设置环境变量 OCTOP_BASE_URL / OCTOP_USERNAME / OCTOP_PASSWORD
默认 base_url: http://127.0.0.1:8088
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("OCTOP_BASE_URL", "http://127.0.0.1:8088")
USER = sys.argv[2] if len(sys.argv) > 2 else os.getenv("OCTOP_USERNAME", "")
PASS = sys.argv[3] if len(sys.argv) > 3 else os.getenv("OCTOP_PASSWORD", "")
if not USER or not PASS:
    sys.exit("missing credentials: pass [username] [password] or set OCTOP_USERNAME / OCTOP_PASSWORD")
MCP_CONFIG = Path.home() / ".workbuddy" / "mcp.json"
if not MCP_CONFIG.exists():
    sys.exit(f"not found: {MCP_CONFIG}")

r = urllib.request.Request(
    BASE + "/api/auth/login",
    data=json.dumps({"username": USER, "password": PASS}).encode(),
    headers={"Content-Type": "application/json"},
)
login = json.loads(urllib.request.urlopen(r, timeout=10).read().decode())
token = login["access_token"]

cfg = json.load(open(MCP_CONFIG))
if "octop" not in cfg.get("mcpServers", {}):
    cfg.setdefault("mcpServers", {})["octop"] = {
        "type": "streamableHttp",
        "url": BASE + "/api/mcp/agents",
        "timeout": 300000,
    }
entry = cfg["mcpServers"]["octop"]
entry["url"] = BASE + "/api/mcp/agents"
entry["headers"] = {"Authorization": f"Bearer {token}"}

json.dump(cfg, open(MCP_CONFIG, "w"), indent=2, ensure_ascii=False)
print(f"octop token 已刷新: {token[:12]}...（写入 {MCP_CONFIG}）")
