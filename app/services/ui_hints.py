from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List
from functools import lru_cache
import yaml

# Dossiers
APP_DIR = Path(__file__).resolve().parents[1]
RULES_DIR = APP_DIR.parent / "rules"

SYNTEC_IDCC = 1486


@lru_cache(maxsize=128)
def _load_yaml_cached(path_str: str) -> Dict[str, Any]:
    p = Path(path_str)
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


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


def _match_list_or_scalar(value, cond) -> bool:
    if cond is None:
        return True
    if isinstance(cond, list):
        return value in cond
    return value == cond


def _norm_category_for_hints(idcc: Optional[int], categorie: str) -> str:
    """
    Politique d’harmonisation des libellés catégorie pour filtrage UI hints:
      - Syntec (1486): mappe 'cadre' -> 'IC', 'non-cadre' -> 'ETAM'
      - Autres CCN: conserve 'cadre' / 'non-cadre' (si repérés), sinon renvoie tel quel
    """
    c = (categorie or "").strip().lower()
    is_non_cadre = c in {"non-cadre", "non cadre", "noncadre", "ouvrier", "etam"}
    is_cadre = c in {"cadre", "ic", "ingenieur", "ingénieur", "agent de maitrise", "agent de maîtrise"}

    if idcc == SYNTEC_IDCC:
        if is_non_cadre:
            return "ETAM"
        if is_cadre:
            return "IC"
        return categorie

    if is_non_cadre:
        return "non-cadre"
    if is_cadre:
        return "cadre"
    return categorie


def _hint_matches(h: Dict[str, Any], ctx: Dict[str, Any], idcc: Optional[int]) -> bool:
    w = h.get("when") or {}
    cat_norm = _norm_category_for_hints(idcc, ctx.get("categorie") or "")

    # Catégorie
    if "category" in w:
        cond = w["category"]
        val = str(cat_norm).strip().lower()
        if isinstance(cond, list):
            allowed = {str(x).strip().lower() for x in cond}
            if val not in allowed:
                return False
        else:
            if val != str(cond).strip().lower():
                return False

    # Mode de temps de travail
    if "work_time_mode" in w and not _match_list_or_scalar((ctx.get("work_time_mode") or "").lower(), w["work_time_mode"]):
        return False

    # Coefficient borné
    coeff = ctx.get("coeff")
    if "coeff_min" in w and (coeff is None or int(coeff) < int(w["coeff_min"])):
        return False
    if "coeff_max" in w and (coeff is None or int(coeff) > int(w["coeff_max"])):
        return False

    return True


def load_ui_hints(idcc: Optional[int], theme: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Charge les micro-textes CCN (ui_hints.yml) et filtre selon le contexte.
    Sortie: [{slot, kind, text, ref?, url?}]
    """
    if not idcc:
        return []
    ccn_dir = _find_ccn_dir(idcc)
    if not ccn_dir:
        return []

    hints_doc = _load_yaml_cached(str(ccn_dir / "ui_hints.yml"))
    raw_hints = hints_doc.get("hints") if isinstance(hints_doc, dict) else (hints_doc or [])
    if not isinstance(raw_hints, list):
        return []

    out: List[Dict[str, Any]] = []
    for h in raw_hints:
        if h.get("theme") != theme:
            continue
        if not _hint_matches(h, ctx, idcc):
            continue
        out.append({
            "slot": h.get("slot") or "",
            "kind": (h.get("kind") or "info").lower(),
            "text": h.get("text") or "",
            "ref": (h.get("ref") or {}).get("label") if isinstance(h.get("ref"), dict) else h.get("ref"),
            "url": (h.get("ref") or {}).get("url") if isinstance(h.get("ref"), dict) else None,
        })
    return out


def build_rule_explain(theme: str, data: Dict[str, Any], rule: Optional[Dict[str, Any]], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Génère des encarts d’explication normalisés en fonction du thème et des données calculées."""
    if not rule:
        return []

    def _kind(default="info"):
        return "ccn" if (rule and str(rule.get("source")).lower() == "ccn") else default

    out: List[Dict[str, Any]] = []

    if theme == "periode_essai" and data.get("max_months") is not None:
        out.append({
            "kind": _kind("info"),
            "slot": "step7.card",
            "text": f"Plafond : {data['max_months']} mois.",
            "ref": rule.get("source_ref"),
            "url": rule.get("url"),
        })
        return out

    if theme == "preavis":
        d = data.get("demission"); l = data.get("licenciement")
        out.append({
            "kind": _kind("info"),
            "slot": "step8.card",
            "text": f"Minima : démission {d if d is not None else '—'} mois · licenciement {l if l is not None else '—'} mois.",
            "ref": rule.get("source_ref"),
            "url": rule.get("url"),
        })
        return out

    if theme == "remuneration" and data.get("monthly_min_eur") is not None:
        base = data.get("base_min_eur"); parts = []
        if isinstance(base, (int, float)):
            parts.append(f"Base (coefficient) : {float(base):.2f} €.")
        parts.append(f"Plancher applicable : {float(data['monthly_min_eur']):.2f} €.")
        out.append({
            "kind": _kind("info"),
            "slot": "step6.footer",
            "text": " ".join(parts),
            "ref": rule.get("source_ref"),
            "url": rule.get("url"),
        })
        # Transparence SMAG 216 j/an (2216, cadres, forfait-jours)
        try:
            if (ctx.get("idcc") == 2216
                and (ctx.get("work_time_mode") or "").lower() == "forfait_days"
                and (ctx.get("categorie") or "").lower() in {"cadre", "ic"}
                and isinstance(data.get("applied"), list)
                and "fj_smag_216" in data.get("applied")):
                m = ctx.get("anciennete_months")
                if isinstance(m, int):
                    col = "premiers 36 mois" if m < 36 else "36 mois et +"
                else:
                    col = "colonne la plus favorable disponible"
                out.append({
                    "kind": _kind("ccn"),
                    "slot": "step6.more.minima",
                    "text": f"SMAG 216 j/an — colonne utilisée : {col} (mensualisation annuelle ÷ 12).",
                    "ref": rule.get("source_ref"),
                    "url": rule.get("url"),
                })
        except Exception:
            pass
        return out

    if theme == "temps_travail":
        if data.get("weekly_hours_min") is not None or data.get("weekly_hours_max") is not None:
            mn = data.get("weekly_hours_min"); mx = data.get("weekly_hours_max")
            txt = (
                f"Hebdomadaire : min {mn} h/sem · max {mx} h/sem." if (mn is not None and mx is not None)
                else (f"Hebdomadaire : min {mn} h/sem." if mn is not None
                      else (f"Hebdomadaire : max {mx} h/sem." if mx is not None else ""))
            )
            avg12 = data.get("average_12_weeks_max")
            if avg12 is not None:
                txt += f" Moyenne 12 semaines : {avg12} h/sem."
            out.append({
                "kind": _kind("info"),
                "slot": "step5.header",
                "text": txt,
                "ref": rule.get("source_ref"),
                "url": rule.get("url"),
            })
            return out
        if data.get("days_per_year_max") is not None:
            out.append({
                "kind": _kind("info"),
                "slot": "step5.header",
                "text": f"Plafond jours/an : {data['days_per_year_max']}.",
                "ref": rule.get("source_ref"),
                "url": rule.get("url"),
            })
            return out

    if theme == "conges" and data.get("min_days") is not None:
        unit = (ctx.get("unit") or "ouvrés"); sug = data.get("suggested_days")
        out.append({
            "kind": _kind("info"),
            "slot": "step8.conges",
            "text": f"Minimum légal : {data['min_days']} {unit}." + (f" Suggestion : {sug}." if isinstance(sug, int) else ""),
            "ref": rule.get("source_ref"),
            "url": rule.get("url"),
        })
        return out

    return out

