# app/services/clauses_library.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import html
import re
import unicodedata

APP_DIR = Path(__file__).resolve().parents[1]
RULES_DIR = APP_DIR.parent / "rules"


def _load_yaml(p: Path) -> Dict[str, Any]:
    """
    Charge un YAML robuste, et normalise les différentes formes possibles :
      - liste brute de clauses -> {"clauses":[...]}
      - {"items":[...]}        -> {"clauses":[...]}
      - {"clauses":[...]}      -> inchangé
    """
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

    if isinstance(data, list):
        return {"clauses": data}
    if isinstance(data, dict):
        if "items" in data and "clauses" not in data:
            data["clauses"] = data.get("items") or []
        return data
    return {}


def _index_by_key(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for it in items or []:
        k = (it.get("key") or "").strip()
        if k:
            out[k] = it
    return out


def _merge_catalogs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge par clé : les clauses de override remplacent celles de base à clé identique.
    Les métadonnées (meta) sont fusionnées, override prioritaire.
    """
    base_items = _index_by_key(base.get("clauses") or [])
    ov_items = _index_by_key(override.get("clauses") or [])
    merged = {**base_items, **ov_items}
    meta = {**(base.get("meta") or {}), **(override.get("meta") or {})}
    return {"meta": meta, "clauses": list(merged.values())}


def _find_ccn_dir(idcc: Optional[int]) -> Optional[Path]:
    if not idcc:
        return None
    root = RULES_DIR / "ccn"
    if not root.exists():
        return None
    for d in root.iterdir():
        if d.is_dir() and str(d.name).split("-")[0] == str(idcc):
            return d
    return None


def _norm_param_spec(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise la spécification d'un paramètre de clause pour le front.
    Champs retournés (selon type) :
      key, label, type, required, placeholder, help, default, min, max, step, options[ {value,label} ]
    Types supportés : text (defaut), number, money, percent, enum, textarea, boolean
    """
    t = str(p.get("type") or "text").lower()
    spec: Dict[str, Any] = {
        "key": p.get("key"),
        "label": p.get("label") or p.get("title") or p.get("key"),
        "type": t,
        "required": bool(p.get("required", False)),
        "placeholder": p.get("placeholder") or "",
        "help": p.get("help") or "",
        "default": p.get("default"),
    }
    if t in ("number", "percent", "money"):
        if p.get("min") is not None:
            spec["min"] = p["min"]
        if p.get("max") is not None:
            spec["max"] = p["max"]
        if p.get("step") is not None:
            spec["step"] = p["step"]
    if t == "enum":
        opts = []
        for o in (p.get("options") or []):
            opts.append(
                {"value": o.get("value"), "label": o.get("label") or str(o.get("value"))}
            )
        spec["options"] = opts
    return spec


def _norm_clause_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise une clause (pour UI + PDF). On conserve text_html ici
    (il ne sera juste pas renvoyé au front dans load_clauses_catalog).
    """
    flags = raw.get("flags") or {}
    return {
        "key": raw.get("key"),
        "label": raw.get("label") or raw.get("title"),
        "synopsis": raw.get("synopsis") or raw.get("summary"),
        "learn_more_html": raw.get("learn_more_html") or "",
        "text_html": raw.get("text_html") or "",  # contenu prêt pour le PDF (avec placeholders)
        "source_ref": raw.get("source_ref"),
        "url": raw.get("url"),
        "flags": {
            "needs_parameters": bool(flags.get("needs_parameters", False)),
            "sensitive": bool(flags.get("sensitive", False)),
        },
        # --- NOUVEAU : spécification des paramètres (pour le front) ---
        "params": [_norm_param_spec(p) for p in (raw.get("params") or [])],
    }


def load_clauses_catalog(idcc: Optional[int] = None) -> Dict[str, Any]:
    """
    Charge un catalogue fusionné : common.yml + (éventuel) ccn/<idcc>/clauses.yml
    Sortie front :
      {
        "items":[
          {key,label,synopsis,learn_more_html,flags,params:[...]},
          ...
        ],
        "meta": {...}
      }
    (NB : on n'expose PAS text_html ici pour alléger le payload)
    """
    common = _load_yaml(RULES_DIR / "clauses" / "common.yml")
    merged = common
    d = _find_ccn_dir(idcc)
    if d and (d / "clauses.yml").exists():
        merged = _merge_catalogs(common, _load_yaml(d / "clauses.yml"))

    items = [_norm_clause_item(x) for x in (merged.get("clauses") or [])]

    ui_items = [
        {
            "key": it["key"],
            "label": it["label"],
            "synopsis": it["synopsis"],
            "learn_more_html": it["learn_more_html"],
            "source_ref": it["source_ref"],
            "url": it["url"],
            "flags": it["flags"],
            # on expose la spec des paramètres
            "params": it["params"],
        }
        for it in items
    ]

    return {"items": ui_items, "meta": merged.get("meta") or {}}


# -----------------------
# Remplacement sécurisé des placeholders
# -----------------------

# Placeholders reconnus :
#   {{cle}}   — style Jinja
#   [[cle]]   — style wiki
#   [cle]     — style simple (y compris <em>[cle]</em>)
_TOKEN_PATTERNS = [
    re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}"),
    re.compile(r"\[\[\s*([a-zA-Z0-9_]+)\s*\]\]"),
    re.compile(r"(?:<em>)?\[([a-zA-Z0-9_]+)\](?:</em>)?", flags=re.IGNORECASE),
]


def _fill_placeholders(text: str, params: Optional[Dict[str, Any]]) -> str:
    """
    Remplace les tokens dans text avec valeurs issues de params.
    - Échappe systématiquement en HTML (html.escape).
    - Pour un select/enum, si le front a envoyé param__label, on privilégie ce libellé.
    - Si une clé est absente, on laisse le placeholder tel quel (repérable visuellement).
    """
    if not text or not params:
        return text or ""

    def repl(m: "re.Match[str]") -> str:
        k = m.group(1)
        value = params.get(f"{k}__label", params.get(k))
        if value is None:
            return m.group(0)
        return html.escape(str(value))

    for pat in _TOKEN_PATTERNS:
        text = pat.sub(repl, text)
    return text


def get_clause_texts(
    idcc: Optional[int],
    keys: List[str],
    params_by_key: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Retourne, pour un ensemble de clés, les textes prêts à injecter dans le PDF.
    - 'keys' : liste des identifiants de clauses.
    - 'params_by_key' (optionnel) : mapping { "<key>": { "<param>": value, "<param>__label": "Libellé (enum)" } }
      Si absent, aucun remplacement n'est effectué (compat ascendante).
    """
    # Index UI (pour titres/refs)
    cat = load_clauses_catalog(idcc)
    by_key_ui = {it["key"]: it for it in (cat.get("items") or [])}

    # Version complète avec text_html (pour les contenus)
    common_full = _load_yaml(RULES_DIR / "clauses" / "common.yml")
    full = _index_by_key(common_full.get("clauses") or [])
    d = _find_ccn_dir(idcc)
    if d and (d / "clauses.yml").exists():
        ov_full = _index_by_key(_load_yaml(d / "clauses.yml").get("clauses") or [])
        full.update(ov_full)

    out: List[Dict[str, Any]] = []
    for k in keys or []:
        ui = by_key_ui.get(k)
        if not ui:
            continue
        raw = full.get(k) or {}
        html_text = raw.get("text_html") or ""
        filled = _fill_placeholders(html_text, (params_by_key or {}).get(k))

        out.append(
            {
                "key": k,
                "title": ui["label"],
                "text_html": filled,
                "source_ref": ui.get("source_ref"),
                "url": ui.get("url"),
                "flags": ui.get("flags") or {},
            }
        )

    return out
