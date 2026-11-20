import json
import sqlite3
import time
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
public = [message for message in state.get("chatMessages", []) if message.get("visibility") == "public"]
marker = public[-1] if public else (state.get("chatMessages") or [{}])[-1]
state["aiContextStartMessageId"] = str(marker.get("id") or "")
state["aiContextStartedAt"] = int(time.time() * 1000)
state["aiMemory"] = {"facts": [], "summaries": [], "threads": []}
state["playerCheckRequests"] = []
state["aiTurnPreview"] = None
control = state.setdefault("aiControl", {})
control["enabled"] = False
control["paused"] = True
control["busy"] = False
control["activeQueueId"] = ""
for item in control.get("queue", []):
    if item.get("status") in {"pending", "processing", "error"}:
        item["status"] = "cancelled"
        item["error"] = "上下文重置，旧队列不执行"
ai_player = state.setdefault("aiPlayer", {})
ai_player["enabled"] = False
ai_player["running"] = False
ai_player["paused"] = True
ai_player["pendingReaction"] = False
state.setdefault("logs", []).append({
    "id": "l_context_reset",
    "time": time.strftime("%Y/%m/%d %H:%M:%S", time.localtime()),
    "at": int(time.time() * 1000),
    "kind": "note",
    "title": "AI 上下文已重置",
    "text": "历史聊天保留，但不再作为当前 AI 剧情上下文。",
})
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "marker", marker.get("id"), "time", marker.get("time"))
