import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
rows = db.execute("select id,name,length(state_json) as n,updated_at from rooms order by updated_at desc limit 10").fetchall()
for row in rows:
    print(dict(row))
