import json
import sqlite3
import time
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
now_ms = int(time.time() * 1000)
now_text = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())
text = (
    "【结团 · 提问与复盘】\n"
    "正片已经结束。接下来只进行提问和复盘，不再推进剧情、不再要求判定，也不会自动生成下一幕。\n\n"
    "你们可以先问：\n"
    "1. 道格拉斯现在到底算什么？他还会回来吗？\n"
    "2. 地下那些“朋友”是什么？他们和失书有什么关系？\n"
    "3. 托马斯之后会怎么处理这件事？\n"
    "4. 还有哪些线索没有解开？\n\n"
    "问完后，我再做整体复盘和结局总结。"
)
message_id = f"postgame_{now_ms}"
state.setdefault("chatMessages", []).append({
    "id": message_id,
    "speakerId": "gm",
    "speakerName": "主持人",
    "role": "gm",
    "visibility": "public",
    "text": text,
    "time": now_text,
})
state["postGame"] = {
    "qaOpen": True,
    "startedAt": now_ms,
    "summary": "",
}
state["aiContextStartMessageId"] = message_id
state["aiContextStartedAt"] = now_ms
state["aiMemory"] = {"facts": [], "summaries": [], "threads": []}
state["playerCheckRequests"] = []
control = state.setdefault("aiControl", {})
control["enabled"] = False
control["paused"] = True
control["busy"] = False
control["queue"] = []
control["activeQueueId"] = ""
control["autoBaselineMessageId"] = message_id
state.setdefault("logs", []).append({
    "id": f"postgame_{now_ms}",
    "time": now_text,
    "at": now_ms,
    "kind": "note",
    "title": "进入结团复盘",
    "text": "剧情结束，开放玩家提问与复盘。AI 托管关闭。",
})
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "postgame", message_id)
