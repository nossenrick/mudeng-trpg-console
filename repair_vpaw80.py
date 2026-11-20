import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
room = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
snap = db.execute("select state_json from room_snapshots where room_id='VPAW80' and revision=124 order by created_at desc limit 1").fetchone()
state = json.loads(room["state_json"])
snap_state = json.loads(snap["state_json"])
players = snap_state.get("players", [])
ian = next(player for player in players if player.get("id") == "p_char_mvtbl1djap3rm")
cecilia = next(player for player in players if player.get("id") == "p_hIwBHANkNw8")
state["players"] = [ian, cecilia]
old_duplicate_ids = {"p1"}
for message in state.get("chatMessages", []):
    speaker = str(message.get("speakerId") or "")
    if speaker in old_duplicate_ids:
        message["speakerId"] = "p_hIwBHANkNw8"
        message["speakerName"] = cecilia.get("name")
game_map = state.setdefault("map", {})
tokens = []
seen = set()
for token in game_map.get("tokens", []):
    if not isinstance(token, dict):
        continue
    token_id = str(token.get("id") or "")
    if token_id in old_duplicate_ids:
        token = {**token, "id": "p_hIwBHANkNw8", "name": cecilia.get("name")}
        token_id = "p_hIwBHANkNw8"
    if token_id in seen:
        continue
    seen.add(token_id)
    tokens.append(token)
for player in (ian, cecilia):
    if player.get("id") not in seen:
        tokens.append({
            "id": player["id"],
            "name": player.get("name"),
            "type": "player",
            "npcId": "",
            "row": 1 if player["id"] == ian.get("id") else 2,
            "col": 1,
        })
game_map["tokens"] = tokens
combat = state.setdefault("combat", {})
combat["turnOrder"] = ["p_char_mvtbl1djap3rm", "p_hIwBHANkNw8"]
combat["actionPoints"] = {}
state.setdefault("selections", {})["playerId"] = "p_char_mvtbl1djap3rm"
new_revision = int(room["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), new_revision))
db.execute("update participants set player_id='p_hIwBHANkNw8' where room_id='VPAW80' and role='player'")
db.commit()
print(json.dumps({"revision": new_revision, "players": [{"id": p["id"], "name": p["name"]} for p in state["players"]], "tokens": tokens, "participants": [dict(r) for r in db.execute("select id,player_id from participants where room_id='VPAW80'")]}, ensure_ascii=False, indent=2))
