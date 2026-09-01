from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_if_present(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


paper_cycle = ROOT / "fronted/paper_cycle.py"
app = ROOT / "fastapi_cloud_app.py"

# This repair is idempotent. The runtime market-observation fix is already in
# main; keep the syntax repair available for old generated copies.
bad_reasoning = '    return f"{text} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4], separators=(\",\", \":\"))}".strip() if alerts else text\n'
good_reasoning = '    return f"{text} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4], separators=(\',\', \':\'))}".strip() if alerts else text\n'
changed = replace_if_present(paper_cycle, bad_reasoning, good_reasoning)

# Preserve the real exception type/message in the AI-engine response while
# debugging the production contract. This is removed once the failing path is
# corrected, but is intentionally deterministic for CI diagnosis.
old_catch = '    except Exception as exc:\n        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI engine analysis failed: {type(exc).__name__}") from exc\n'
new_catch = '    except Exception as exc:\n        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI engine analysis failed: {type(exc).__name__}: {exc}") from exc\n'
app_changed = replace_if_present(app, old_catch, new_catch)
print("Fixed _reasoning f-string syntax" if changed else "_reasoning f-string already fixed")
print("Added AI engine exception detail" if app_changed else "AI engine exception detail already enabled")
