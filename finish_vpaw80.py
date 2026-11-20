import json
import sqlite3
import time
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
messages = state.get("chatMessages", [])
keep_until = None
for index, message in enumerate(messages):
    if str(message.get("time") or "") == "2026/10/30 17:36:27":
        keep_until = index
if keep_until is None:
    raise SystemExit("good message not found")
state["chatMessages"] = messages[:keep_until + 1]
ending_text = (
    "【尾声】\n"
    "陵墓的石板在黎明前合拢，道格拉斯抱着那几本书走进黑暗，托马斯站在墓园门口，直到再也听不见里面的脚步声。"
    "他没有追上去，只把那盏灯举高了一点，像是替叔叔照完最后一段路。"
    "你们离开时，东边的天已经泛白，草叶上的露水打湿了鞋面。墓园重新安静下来，只剩下风穿过白杨的声音。"
    "道格拉斯去了哪里、那些书最终能不能回到书架，已经不是今晚能回答的事了；但托马斯终于见到了他，也把该说的话说完了。"
)
ending_id = f"ending_{int(time.time() * 1000)}"
now_ms = int(time.time() * 1000)
now_text = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())
state["chatMessages"].append({
    "id": ending_id,
    "speakerId": "gm",
    "speakerName": "主持人",
    "role": "gm",
    "visibility": "public",
    "text": ending_text,
    "time": now_text,
})
scene = state.setdefault("scene", {})
scene["title"] = "尾声：墓园道别"
scene["location"] = "布莱克伍德墓园"
scene["time"] = "黎明前"
scene["focus"] = "道格拉斯回到地下，托马斯完成了道别，调查员准备离开墓园。"
scene["publicText"] = "石板已经合拢，天光从墓园围墙后透出来。道格拉斯回到地下，托马斯提着灯站在门口，调查员终于可以离开。"
play = state.setdefault("playFlow", {})
play["phase"] = "ended"
play["currentObjective"] = "本战役已结束：墓园道别"
play["suggestedActions"] = []
state["aiContextStartMessageId"] = ending_id
state["aiContextStartedAt"] = now_ms
state["aiMemory"] = {"facts": [], "summaries": [], "threads": []}
state["aiTurnPreview"] = None
state["playerCheckRequests"] = []
control = state.setdefault("aiControl", {})
control["enabled"] = False
control["paused"] = True
control["busy"] = False
control["activeQueueId"] = ""
control["queue"] = []
control["autoBaselineMessageId"] = ending_id
ai_player = state.setdefault("aiPlayer", {})
ai_player["enabled"] = False
ai_player["running"] = False
ai_player["paused"] = True
ai_player["pendingReaction"] = False
state.setdefault("logs", []).append({
    "id": f"end_{now_ms}",
    "time": now_text,
    "at": now_ms,
    "kind": "note",
    "title": "战役结束",
    "text": "已收束到墓园道别后的尾声。AI 托管已关闭。",
})
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "messages", len(state["chatMessages"]), "ending", ending_id)
