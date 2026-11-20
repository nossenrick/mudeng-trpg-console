import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()[0])
for player in state.get("players", []):
    print(player.get("name"), {k: player.get(k) for k in ["hp", "maxHp", "skillPoints", "maxSkillPoints", "san", "maxSan", "mp", "maxMp", "luck", "level", "experiences"]})
