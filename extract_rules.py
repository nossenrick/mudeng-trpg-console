from pathlib import Path
import re
import unicodedata
from pypdf import PdfReader


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


for name in ("coc7e-keeper", "dnd5e-srd"):
    source = Path("rules") / f"{name}.pdf"
    if not source.exists():
        print(f"missing {source}")
        continue
    reader = PdfReader(str(source))
    parts = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = normalize_text(page.extract_text() or "")
        except Exception as error:
            text = f"[extraction error: {error}]"
        parts.append(f"\n\n[PAGE {index}]\n{text}")
    output = Path("rules") / f"{name}.txt"
    output.write_text("".join(parts), encoding="utf-8")
    print(name, len(reader.pages), output.stat().st_size)
