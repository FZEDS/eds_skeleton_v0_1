# app/services/doc_registry.py
from pathlib import Path
from typing import List, Dict, Optional
import yaml

APP_DIR = Path(__file__).resolve().parents[1]  # .../app
ROOT = APP_DIR.parent                           # repo root
CATALOG = ROOT / "docs" / "catalog.yml"

def _load_yaml(p: Path) -> dict:
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def list_documents() -> List[Dict]:
    data = _load_yaml(CATALOG)
    docs = data.get("documents") or []
    out = []
    for d in docs:
        out.append({
            "key": d.get("key"),
            "label": d.get("label") or d.get("key"),
            "template": d.get("template"),        # ex: "cdi_form.html.j2"
            "pdf_template": d.get("pdf_template"),
            "status": d.get("status") or "ready", # "ready" | "wip"
            "description": d.get("description") or "",
            "icon": d.get("icon") or None,
        })
    return out

def get_document(key: str) -> Optional[Dict]:
    for d in list_documents():
        if d["key"] == key:
            return d
    return None
