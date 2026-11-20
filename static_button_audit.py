import re
from pathlib import Path

html = Path("index.html").read_text(encoding="utf-8")
js = Path("app.js").read_text(encoding="utf-8")
ids = re.findall(r'id="([^"]+)"', html)
print("duplicate ids", sorted({i for i in ids if ids.count(i) > 1}))
missing = []
for i in ids:
    if f'#{i}' in js or f'getElementById("{i}")' in js or f"getElementById('{i}')" in js:
        continue
    missing.append(i)
print("ids without js reference", missing)
buttons = re.findall(r'<button[^>]*id="([^"]+)"[^>]*>', html)
print("button ids", len(buttons))
print("buttons without direct js id ref", [b for b in buttons if f'#{b}' not in js])
