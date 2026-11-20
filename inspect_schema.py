import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
for row in db.execute("select name, sql from sqlite_master where type='table' and name in ('devices','campaign_saves','participants')"):
    print(row[0], row[1])
