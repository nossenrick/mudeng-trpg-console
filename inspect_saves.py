import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
print("room snapshots oldest")
row = db.execute("select min(created_at), max(created_at), count(*) from room_snapshots where room_id='VPAW80'").fetchone()
print(dict(row))
print("campaign saves")
for row in db.execute("select id,name,summary,auto,created_at,length(state_json) as size from campaign_saves order by created_at desc limit 20"):
    print(dict(row))
