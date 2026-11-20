import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()["state_json"])
module = state.get("module", {})
print("module", module.get("title"), module.get("ruleSystem"))
print("scene", state.get("scene", {}).get("title"), state.get("scene", {}).get("location"))
print("playFlow", state.get("playFlow"))
for node in state.get("scenarioNodes", []) or module.get("scenarioNodes", []) or []:
    print("NODE", node.get("id"), node.get("title"), node.get("status"), str(node.get("publicText") or "")[:60])
print("snapshots", len(state.get("snapshots", [])), "logs", len(state.get("logs", [])), "messages", len(state.get("chatMessages", [])))
