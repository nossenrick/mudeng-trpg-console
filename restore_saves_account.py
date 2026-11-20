import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.execute(
    "UPDATE campaign_saves SET account_id = ? WHERE account_id = ''",
    ("account_HXrtVqodV4Rib8My",),
)
db.commit()
for row in db.execute("SELECT id, name, account_id, auto FROM campaign_saves ORDER BY updated_at DESC"):
    print(row)
