# app/services/ccn_registry.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml
import re

APP_DIR = Path(__file__).resolve().parents[1]
RULES_DIR = APP_DIR.parent / "rules"

# Quelques libellés sûrs en fallback si on ne trouve rien dans les YAML
FALLBACK_LABELS = {
    1486: "Bureaux d’études techniques (Syntec)",
    1979: "Hôtels, cafés, restaurants (HCR)",
    44:   "Métallurgie (ingénieurs et cadres)",
    1518: "Commerce de détail et de gros à prédominance alimentaire",
}

def _load_meta_label(d: Path) -> Optional[str]:
    """Essaye de lire meta.label depuis classification.yml, remuneration.yml, ou temps_travail.yml."""
    for name in ("classification.yml", "remuneration.yml", "temps_travail.yml"):
        p = d / name
        if p.exists():
            try:
                y = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                meta = y.get("meta") or {}
                label = meta.get("label")
                if isinstance(label, str) and label.strip():
                    return label.strip()
            except Exception:
                continue
    # si rien, on tente depuis le slug
    m = re.search(r"\d{3,4}-(.+)", d.name)
    if m:
        slug = m.group(1).replace("-", " ").strip()
        return slug.title()
    return None

def list_ccn_raw() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    root = RULES_DIR / "ccn"
    if root.exists():
        for d in root.iterdir():
            if not d.is_dir():
                continue
            try:
                idcc = int(d.name.split("-")[0])
            except Exception:
                continue
            label = _load_meta_label(d) or FALLBACK_LABELS.get(idcc) or d.name
            out.append({"idcc": idcc, "label": label, "slug": d.name})
    # Assure au moins nos CCN pivots
    have = {x["idcc"] for x in out}
    for k, v in FALLBACK_LABELS.items():
        if k not in have:
            out.append({"idcc": k, "label": v, "slug": str(k)})
    # dédoublonnage par idcc (garde le premier)
    uniq: Dict[int, Dict[str, Any]] = {}
    for it in out:
        uniq.setdefault(it["idcc"], it)
    return sorted(uniq.values(), key=lambda x: x["label"].lower())

def search_ccn(q: Optional[str]) -> List[Dict[str, Any]]:
    items = list_ccn_raw()
    if not q:
        return items
    s = str(q).strip().lower()
    if not s:
        return items
    res = []
    for it in items:
        if s in str(it["idcc"]) or s in (it.get("label","").lower()):
            res.append(it)
        else:
            # quelques alias usuels
            txt = (it.get("label","").lower())
            aliases = []
            if it["idcc"] == 1979:
                aliases = ["hcr", "hotel", "hôtellerie", "cafés", "restaurants", "chr", "restauration"]
            if any(a in s for a in aliases) or any(a in txt for a in [s]):
                if it not in res:
                    res.append(it)
    return res
