import json
import sqlite3
import time
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
now = int(time.time() * 1000)
iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now // 1000))
entries = {
    "p_char_mvtbl1djap3rm": {
        "id": f"exp_{now}_ian",
        "at": iso,
        "campaign": "追书人",
        "module": "追书人",
        "chapter": "尾声 · 墓园道别",
        "scene": "布莱克伍德墓园",
        "summary": "伊恩受托马斯委托调查金博尔家失书，在书房撞见道格拉斯，随后带托马斯去墓园让叔侄完成最后道别。道格拉斯在黎明前回到地下。",
        "growth": ["结团时理智：45/45", "结团时生命：11/11", "结团时幸运：55"],
    },
    "p_hIwBHANkNw8": {
        "id": f"exp_{now}_cecilia",
        "at": iso,
        "campaign": "追书人",
        "module": "追书人",
        "chapter": "尾声 · 墓园道别",
        "scene": "布莱克伍德墓园",
        "summary": "塞西莉亚与伊恩一起调查金博尔家失书，在书房与道格拉斯对峙，并在墓园促成托马斯与叔叔的道别。",
        "growth": ["结团时理智：0/0（角色卡数据待修正）", "结团时生命：11/11", "结团时幸运：50"],
    },
}
for player in state.get("players", []):
    entry = entries.get(player.get("id"))
    if not entry:
        continue
    experiences = player.get("experiences") if isinstance(player.get("experiences"), list) else []
    if not any(item.get("id") == entry["id"] for item in experiences):
        experiences.append(entry)
    player["experiences"] = experiences[-30:]
state.setdefault("postGame", {})["finishedAt"] = iso
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "experiences", [(p.get("name"), len(p.get("experiences", []))) for p in state.get("players", [])])
