import json
import sqlite3
import re
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()[0])
for clue in state.get("clues", []):
    title = str(clue.get("title") or "").strip()
    source = str(clue.get("source") or "").strip()
    content = str(clue.get("objective") or clue.get("text") or "").strip()
    phrases = [p.strip() for p in re.split(r"[，。；：、\n]", content) if 6 <= len(p.strip()) <= 36]
    hit = False
    reason = ""
    for message in state.get("chatMessages", []):
        if message.get("visibility") != "public":
            continue
        text = str(message.get("text") or "")
        if len(title) >= 3 and title in text:
            hit = True; reason = "title"; break
        if len(source) >= 3 and source in text:
            hit = True; reason = "source"; break
        if sum(1 for p in phrases if p in text) >= 2:
            hit = True; reason = "phrases"; break
    if hit:
        print("HIT", title, "|", source, "|", reason)
