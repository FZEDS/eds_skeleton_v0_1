#!/usr/bin/env python3
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules"

def load_yaml(p: Path):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERR] YAML invalide: {p}: {e}")
        return None

def check_ui_hints(p: Path, data):
    if not isinstance(data, dict) or "hints" not in data:
        print(f"[ERR] {p}: doit contenir une clé 'hints: [...]'")
        return False
    ok = True
    for i, h in enumerate(data["hints"]):
        for k in ["slot","kind","when","text"]:
            if k not in h:
                print(f"[ERR] {p}: hint #{i} manque '{k}'")
                ok = False
        if not isinstance(h.get("when"), dict):
            print(f"[ERR] {p}: hint #{i} 'when' doit être un objet")
            ok = False
    return ok

def main():
    ok = True
    for p in RULES.rglob("*.yml"):
        data = load_yaml(p)
        if data is None:
            ok = False
            continue
        if p.name == "ui_hints.yml":
            ok = check_ui_hints(p, data) and ok
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
