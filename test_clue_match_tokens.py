import json
import sqlite3
import re
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()[0])
stop = set("调查员 玩家 线索 事情 地方 里面 然后 现在 可能 出现 发现 获得 一个 他们 你们 我们 什么 没有 已经 自己".split())
for clue in state.get("clues", []):
    title = str(clue.get("title") or "").strip()
    source = str(clue.get("source") or "").strip()
    content = str(clue.get("objective") or clue.get("text") or "").strip()
    phrases = [p.strip() for p in re.split(r"[，。；：、\n]", content) if 6 <= len(p.strip()) <= 36]
    tokens = list(dict.fromkeys([p.strip() for p in re.split(r"[的与和·：:，,\s/、]", f"{title} {source}") if len(p.strip()) >= 2 and p.strip() not in stop]))
    hit = False; reason = ""
    for message in state.get("chatMessages", []):
        if message.get("visibility") != "public": continue
        text = str(message.get("text") or "")
        if (len(title) >= 3 and title in text) or (len(source) >= 3 and source in text):
            hit = True; reason = "exact"; break
        if sum(1 for p in phrases if p in text) >= 2:
            hit = True; reason = "phrases"; break
        if sum(1 for t in tokens if t in text) >= 2:
            hit = True; reason = "tokens"; break
    if hit:
        print("HIT", title, "|", source, "|", reason)
