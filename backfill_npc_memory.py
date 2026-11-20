import json
import sqlite3
import time
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
npcs = {str(npc.get("id")): npc for npc in state.get("npcs", []) if isinstance(npc, dict)}
now = int(time.time() * 1000)
iso = "2026-10-30T09:36:27+00:00"

def remember(npc_id, first, last, known, events):
    npc = npcs.get(npc_id)
    if not npc:
        return
    memory = npc.get("memory") if isinstance(npc.get("memory"), dict) else {}
    if not memory.get("events"):
        memory["events"] = []
    memory["met"] = True
    memory["firstMet"] = memory.get("firstMet") or first
    memory["lastMet"] = last
    memory["knownToPlayers"] = memory.get("knownToPlayers") or known
    for scene, summary in events:
        if not any(item.get("scene") == scene and item.get("summary") == summary for item in memory["events"]):
            memory["events"].append({"at": iso, "scene": scene, "summary": summary, "attitude": npc.get("attitude", "")})
    memory["events"] = memory["events"][-20:]
    npc["memory"] = memory

remember("module_import_mvtald99cdmbp_npc_1", "第一章 · 金博尔家书房", "尾声 · 墓园",
         "托马斯委托调查失书；调查员在墓园让他与道格拉斯完成道别。",
         [("金博尔家书房", "托马斯接受调查员，允许查看书房和失书现场。"),
          ("墓园", "托马斯见到道格拉斯，完成了最后的道别。")])
remember("module_import_mvtald99cdmbp_npc_2", "第一章 · 金博尔家书房", "金博尔家书房",
         "邻居莉拉；调查员在书房与她打过照面。",
         [("金博尔家书房", "莉拉询问失书和书房里的访客，调查员与她交谈。")])
remember("module_import_mvtald99cdmbp_npc_3", "第一章 · 金博尔家书房", "尾声 · 墓园",
         "调查员知道道格拉斯已变成食尸鬼并住在地下；托马斯在墓园与他道别。",
         [("金博尔家书房", "道格拉斯回书房取书，被调查员和托马斯撞见。"),
          ("墓园", "道格拉斯向托马斯解释自己的选择，黎明前回到地下。")])
jefferson = npcs.get("module_import_mvtald99cdmbp_npc_4")
if jefferson:
    jefferson["memory"] = {
        "met": False, "firstMet": "", "lastMet": "",
        "knownToPlayers": "", "relationship": jefferson.get("relationship", ""), "events": []
    }
state["storyEvents"] = [
    {"id": "backfill_thomas_study", "at": iso, "scene": "金博尔家书房", "location": "金博尔家书房",
     "action": "调查员接受托马斯委托", "summary": "托马斯说明失书经过，允许调查员查看书房。",
     "npcIds": ["module_import_mvtald99cdmbp_npc_1"], "npcNames": ["托马斯·金博尔"]},
    {"id": "backfill_douglas_study", "at": iso, "scene": "金博尔家书房", "location": "金博尔家书房",
     "action": "调查员在书房撞见道格拉斯", "summary": "道格拉斯回书房取书，承认自己住在地下。",
     "npcIds": ["module_import_mvtald99cdmbp_npc_3"], "npcNames": ["道格拉斯·金博尔"]},
    {"id": "backfill_cemetery", "at": iso, "scene": "墓园", "location": "布莱克伍德墓园",
     "action": "调查员带托马斯去墓园见道格拉斯", "summary": "托马斯与道格拉斯完成最后道别，道格拉斯在黎明前回到地下。",
     "npcIds": ["module_import_mvtald99cdmbp_npc_1", "module_import_mvtald99cdmbp_npc_3"],
     "npcNames": ["托马斯·金博尔", "道格拉斯·金博尔"]},
]
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "npcs", [(npc.get("id"), npc.get("memory", {}).get("met")) for npc in state.get("npcs", [])])
