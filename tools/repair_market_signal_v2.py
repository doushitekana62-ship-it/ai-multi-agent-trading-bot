from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_if_present(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


paper_cycle = ROOT / "fronted/paper_cycle.py"

# The market observation repair is already present in main. This action is
# intentionally idempotent and only fixes the syntax error in _reasoning.
bad_reasoning = '    return f"{text} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4], separators=(\",\", \":\"))}".strip() if alerts else text\n'
good_reasoning = '    return f"{text} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4], separators=(\',\', \':\'))}".strip() if alerts else text\n'

changed = replace_if_present(paper_cycle, bad_reasoning, good_reasoning)
print("Fixed _reasoning f-string syntax" if changed else "_reasoning f-string already fixed")
