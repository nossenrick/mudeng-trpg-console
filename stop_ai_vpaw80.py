import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
control = state.setdefault("aiControl", {})
control["enabled"] = False
control["paused"] = True
control["busy"] = False
control["activeQueueId"] = ""
control["lastError"] = ""
for item in control.get("queue", []):
    if item.get("status") in {"pending", "processing", "error"}:
        item["status"] = "cancelled"
        item["error"] = "主机手动停止：旧队列不再执行"
ai_player = state.setdefault("aiPlayer", {})
ai_player["enabled"] = False
ai_player["running"] = False
ai_player["paused"] = True
ai_player["pendingReaction"] = False
state["aiTurnPreview"] = None
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "pending left", sum(1 for item in control.get("queue", []) if item.get("status") == "pending"))
