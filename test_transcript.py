import json
import sqlite3
import urllib.request
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select id, token from participants where room_id='VPAW80' and role='gm'").fetchone()
print("participant", row["id"])
url = f"http://127.0.0.1:8000/api/rooms/VPAW80/transcript?participant_id={row['id']}"
request = urllib.request.Request(url, headers={"X-Participant-Token": row["token"]})
with urllib.request.urlopen(request, timeout=10) as response:
    data = response.read().decode("utf-8")
    print("status", response.status, "chars", len(data), "lines", data.count("\n"))
    Path("transcript_test.txt").write_text(data, encoding="utf-8")
print("files", [p.name for p in Path("transcripts").glob("VPAW80*")])
