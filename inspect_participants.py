import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
for row in db.execute("select id,name,role,player_id,device_id from participants where room_id='VPAW80'"):
    print(dict(row))
