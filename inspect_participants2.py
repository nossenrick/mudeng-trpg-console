import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
for row in db.execute("SELECT id, name, role, player_id, account_id, device_id, last_seen_at FROM participants WHERE room_id='VPAW80'"):
    print(dict(row))
