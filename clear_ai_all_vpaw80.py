import json
import sqlite3
import time
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
public = [message for message in state.get("chatMessages", []) if message.get("visibility") == "public"]
marker = public[-1] if public else None
state["aiContextStartMessageId"] = str(marker.get("id") or "") if marker else ""
state["aiContextStartedAt"] = int(time.time() * 1000)
state["aiMemory"] = {"facts": [], "summaries": [], "threads": []}
state["playerCheckRequests"] = []
state["aiTurnPreview"] = None
control = state.setdefault("aiControl", {})
control["enabled"] = False
control["paused"] = True
control["busy"] = False
control["activeQueueId"] = ""
control["queue"] = []
control["autoBaselineMessageId"] = str(marker.get("id") or "") if marker else ""
ai_player = state.setdefault("aiPlayer", {})
ai_player["enabled"] = False
ai_player["running"] = False
ai_player["paused"] = True
ai_player["pendingReaction"] = False
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "marker", state["aiContextStartMessageId"], "queue", len(control["queue"]))
