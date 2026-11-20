import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
print("ACCOUNTS")
for row in db.execute("select id,account_no,display_name,created_at,last_seen_at from accounts order by created_at"):
    print(dict(row))
print("Saves")
for row in db.execute("select id,name,account_id,auto,updated_at from campaign_saves order by updated_at desc limit 20"):
    print(dict(row))
print("Devices")
for row in db.execute("select id,name,account_id,last_seen_at from devices order by last_seen_at desc limit 10"):
    print(dict(row))
