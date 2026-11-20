import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
facts = {
    "module_import_mvtald99cdmbp_npc_3": "已经与托马斯在墓园见面；托马斯已经知道他不是活人，也知道他在地下生活。不要再让道格拉斯说“别告诉托马斯”“帮我转告托马斯”之类的话。他现在接受托马斯知道真相，目标改为回到地下、保护地下群体；对托马斯不再隐瞒。",
    "module_import_mvtald99cdmbp_npc_1": "已经与道格拉斯在墓园见面并完成道别；托马斯已经知道叔叔在地下活着。不要再让托马斯请求调查员“帮我转告叔叔”或把见面当成未发生。",
}
for npc in state.get("npcs", []):
    if npc.get("id") in facts:
        npc["currentFacts"] = facts[npc["id"]]
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision)
