import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
print([row[0] for row in db.execute("select name from sqlite_master where type='table'")])
for name in ("rooms", "room_members", "participants"):
    try:
        rows = list(db.execute(f"select * from {name} limit 5"))
    except Exception as error:
        print(name, error)
        continue
    print("TABLE", name, "COUNT", len(rows))
    for row in rows:
        data = dict(row)
        print({key: (str(value)[:120] if key in {"state", "snapshot", "data"} else value) for key, value in data.items()})
