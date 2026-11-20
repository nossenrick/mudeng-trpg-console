import re
from collections import Counter
from pathlib import Path

html = Path("index.html").read_text(encoding="utf-8")
classes = Counter()
for match in re.finditer(r"<button([^>]*)>", html):
    attributes = match.group(1)
    class_match = re.search(r'class="([^"]*)"', attributes)
    classes.update((class_match.group(1) if class_match else "(none)").split())
for name, count in classes.most_common():
    print(count, name)
