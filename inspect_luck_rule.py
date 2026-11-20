from pathlib import Path

t = Path("rules/coc7e-keeper.txt").read_text(encoding="utf-8")
out = [str(len(t)), str(t.count("幸运")), str(t.count("幸运值"))]
for term in ("幸运值", "幸运检定", "花费幸运"):
    i = t.find(term)
    out.append(f"TERM {term} {i}")
    if i >= 0:
        out.append(t[max(0, i - 200):i + 1200])
        out.append("---")
Path("luck_rule_output.txt").write_text("\n".join(out), encoding="utf-8")
