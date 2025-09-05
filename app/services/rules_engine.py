# app/services/rules_engine.py
from __future__ import annotations

from pathlib import Path
from datetime import date
from typing import Optional, Tuple, List, Dict, Any
import yaml
from functools import lru_cache
import os


# Dossiers
APP_DIR = Path(__file__).resolve().parents[1]   # .../app
RULES_DIR = APP_DIR.parent / "rules"            # .../rules

# Constantes CCN
SYNTEC_IDCC = 1486


# -------- utilitaires généraux --------

def _parse_date(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None

def _within_effective(rule: Dict[str, Any], d: date) -> bool:
    """Vérifie si la règle est applicable à la date d."""
    eff = rule.get("effective") or {}
    f = _parse_date(eff.get("from"))
    t = _parse_date(eff.get("to"))
    if f and d < f:
        return False
    if t and d > t:
        return False
    return True

def _to_int(val: Any) -> Optional[int]:
    """Convertit proprement vers int si possible, sinon None."""
    if val is None:
        return None
    try:
        return int(str(val).strip())
    except Exception:
        return None

def _to_float(val: Any) -> Optional[float]:
    """Convertit proprement vers float (supporte les virgules), sinon None."""
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ".").strip())
    except Exception:
        return None

def _normalize_category(idcc: Optional[int], categorie: str) -> str:
    """
    Normalise la catégorie UI selon la CCN :
      - Syntec (IDCC 1486) : 'non-cadre' -> 'ETAM', 'cadre' -> 'IC'
      - Autres CCN : on garde 'cadre' / 'non-cadre' (normalisés) pour matcher leurs YAML.
    """
    c = (categorie or "").strip().lower()

    # Normalisation générique "cadre / non-cadre"
    is_non_cadre = c in {"non-cadre", "non cadre", "noncadre", "ouvrier", "etam"}
    is_cadre     = c in {"cadre", "ic", "ingenieur", "ingénieur", "agent de maitrise", "agent de maîtrise"}

    if idcc == SYNTEC_IDCC:
        if is_non_cadre:
            return "ETAM"
        if is_cadre:
            return "IC"
        # sinon on remonte tel quel (pour compat rare)
        return categorie

    # Hors Syntec : on reste sur les libellés usuels pour matches YAML
    if is_non_cadre:
        return "non-cadre"
    if is_cadre:
        return "cadre"
    return categorie

def _category_match(rule_category: Any, normalized: str) -> bool:
    """Match de catégorie tolérant à la casse/espaces; None => sans contrainte."""
    if rule_category in (None, ""):
        return True
    return str(rule_category).strip().lower() == str(normalized).strip().lower()

def _coeff_match(rule: Dict[str, Any], coeff: Optional[int]) -> bool:
    """
    Renvoie True si la règle matche le coefficient :
    - coeff_in : liste précise
    - coeff_range : intervalle inclusif min/max
    - sinon : pas de contrainte sur le coeff
    """
    if "coeff_in" in rule:
        if coeff is None:
            return False
        return coeff in set(rule["coeff_in"])
    if "coeff_range" in rule:
        if coeff is None:
            return False
        rg = rule["coeff_range"] or {}
        lo = _to_int(rg.get("min"))
        hi = _to_int(rg.get("max"))
        return (lo is None or coeff >= lo) and (hi is None or coeff <= hi)
    return True

def _anciennete_match(rule: Dict[str, Any], months: Optional[int]) -> bool:
    """
    Pour le thème 'préavis' : filtre par ancienneté si la règle le prévoit.
    Convention : [min, max) (max exclusif). Si max absent => borne ouverte.
    """
    if "anciennete_months" not in rule:
        return True
    if months is None:
        return False
    rng = rule["anciennete_months"] or {}
    lo = _to_int(rng.get("min")) or 0
    hi = _to_int(rng.get("max"))
    if hi is None:
        return months >= lo
    return lo <= months < hi

def _score_specificity(rule: Dict[str, Any]) -> int:
    """Pour classer les règles CCN : coeff_in > coeff_range > générique."""
    if "coeff_in" in rule:
        return 3
    if "coeff_range" in rule:
        return 2
    return 1


# -------- chargement des YAML --------

def _find_ccn_dir(idcc: int) -> Optional[Path]:
    root = RULES_DIR / "ccn"
    if not root.exists():
        return None
    for d in root.iterdir():
        if not d.is_dir():
            continue
        # accepte '1486', '1486-syntec', etc.
        if str(d.name).split("-")[0] == str(idcc):
            return d
    return None

def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0

@lru_cache(maxsize=256)
def _load_yaml_cached(path_str: str, mtime: float):
    p = Path(path_str)
    if not p.exists():
        return [], {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return [], {}
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        items = data.get("rules") or []
        extras = {k: v for k, v in data.items() if k != "rules"}
        return items, extras
    return [], {}


def _load_yaml(p: Path):
    """Chargement YAML avec cache (clé: chemin + mtime)."""
    return _load_yaml_cached(str(p), _mtime(p))


def _load_rules_bundle(theme: str, idcc: Optional[int]) -> Dict[str, Any]:
    """
    Charge le paquet de règles pour un thème donné :
    - code_items / code_extras
    - ccn_items / ccn_extras
    """
    bundle = {"code_items": [], "code_extras": {}, "ccn_items": [], "ccn_extras": {}}

    # Code du travail
    code_path = RULES_DIR / "code_travail" / f"{theme}.yml"
    code_items, code_extras = _load_yaml(code_path)
    bundle["code_items"] = code_items
    bundle["code_extras"] = code_extras

    # CCN
    if idcc:
        d = _find_ccn_dir(idcc)
        if d:
            ccn_path = d / f"{theme}.yml"
            ccn_items, ccn_extras = _load_yaml(ccn_path)
            bundle["ccn_items"] = ccn_items
            bundle["ccn_extras"] = ccn_extras

    return bundle


# -------- extraction des bornes / notices --------

def _extract_bounds_from_rule(rule: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Unifie les structures différentes :
    - CCN -> 'bounds' + 'renewal_allowed' (bool)
    - Code du travail -> 'constraint' {max_months, max_total_months, renewals_allowed(bool|int)}
    """
    if "bounds" in rule:
        b = rule["bounds"] or {}
        return {
            "max_months": _to_float(b.get("max_months")),
            "max_total_months": _to_float(b.get("max_total_months")),
            "renewals_allowed": 1 if rule.get("renewal_allowed") else 0 if rule.get("renewal_allowed") is not None else None,
        }
    if "constraint" in rule:
        c = rule["constraint"] or {}
        ra = c.get("renewals_allowed")
        if isinstance(ra, bool):
            ra = 1 if ra else 0
        return {
            "max_months": _to_float(c.get("max_months")),
            "max_total_months": _to_float(c.get("max_total_months")),
            "renewals_allowed": _to_int(ra) if ra is not None else None,
        }
    return {"max_months": None, "max_total_months": None, "renewals_allowed": None}


# ========================
#  API du moteur (bas niveau)
# ========================

def compute_probation_bounds(
    idcc: Optional[int],
    categorie: str,
    contract_start: str,
    coeff: Optional[int] = None,
) -> Tuple[Dict[str, Optional[float]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    PÉRIODE D'ESSAI — Retourne (bounds, chosen_rule, considered_rules)
    - bounds: {"max_months", "max_total_months", "renewals_allowed"}
    - chosen_rule: {"source","source_ref","bloc","raw"} ou None
    - considered_rules: liste des règles candidates (debug)
    Logique : CCN prime, sinon Code du travail (ordre public).
    """
    d = date.fromisoformat(contract_start)
    cat_key = _normalize_category(idcc, categorie)
    bundle = _load_rules_bundle("periode_essai", idcc)

    # 1) CCN (si présente) — filtre par date, catégorie et coefficient
    ccn_candidates = [
        r for r in bundle["ccn_items"]
        if _within_effective(r, d)
        and _category_match(r.get("category"), cat_key)
        and _coeff_match(r, coeff)
    ]
    if ccn_candidates:
        ccn_candidates.sort(key=_score_specificity, reverse=True)  # la plus spécifique d'abord
        chosen = ccn_candidates[0]
        bounds = _extract_bounds_from_rule(chosen)
        return bounds, {
            "source": "ccn",
            "source_ref": chosen.get("source_ref"),
            "bloc": "bloc_1",
            "raw": chosen,
        }, ccn_candidates

    # 2) Fallback CCN -> defaults.fallback du YAML CCN (optionnel)
    fb = (bundle["ccn_extras"].get("defaults") or {}).get("fallback") if bundle["ccn_extras"] else None
    if fb:
        fb_cat = fb.get(cat_key)
        if fb_cat:
            bounds = {
                "max_months": _to_float(fb_cat.get("max_months")),
                "max_total_months": _to_float(fb_cat.get("max_total_months")),
                "renewals_allowed": None,
            }
            return bounds, {
                "source": "ccn",
                "source_ref": (bundle["ccn_extras"].get("meta") or {}).get("source", {}).get("article"),
                "bloc": "bloc_1",
                "raw": {"_synthetic": True, **fb_cat},
            }, []

    # 3) Code du travail — format "legacy" (scope.categorie)
    code_candidates = [
        r for r in bundle["code_items"]
        if _within_effective(r, d)
        and (r.get("scope", {}).get("categorie") in (None, categorie))
    ]
    if code_candidates:
        chosen = code_candidates[0]
        bounds = _extract_bounds_from_rule(chosen)
        return bounds, {
            "source": "code_travail",
            "source_ref": chosen.get("source_ref"),
            "bloc": "ordre_public",
            "raw": chosen,
        }, code_candidates

    # 4) Rien trouvé
    return {"max_months": None, "max_total_months": None, "renewals_allowed": None}, None, []


def compute_notice_bounds(
    idcc: Optional[int],
    categorie: str,
    anciennete_months: Optional[int],
    coeff: Optional[int] = None,
    as_of: Optional[str] = None,
) -> Tuple[Dict[str, Optional[float]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    PRÉAVIS — Retourne (notice, chosen_rule, considered_rules)
    - notice: {"demission": mois|None, "licenciement": mois|None}
    """
    d = date.fromisoformat(as_of) if as_of else date.today()
    cat_key = _normalize_category(idcc, categorie)
    bundle = _load_rules_bundle("preavis", idcc)

    # CCN d'abord
    ccn_candidates = [
        r for r in bundle["ccn_items"]
        if _within_effective(r, d)
        and _category_match(r.get("category"), cat_key)
        and _coeff_match(r, coeff)
        and _anciennete_match(r, anciennete_months)
    ]
    if ccn_candidates:
        ccn_candidates.sort(key=_score_specificity, reverse=True)
        chosen = ccn_candidates[0]
        nm = chosen.get("notice_months", {}) or {}
        notice = {
            "demission": _to_float(nm.get("demission")),
            "licenciement": _to_float(nm.get("licenciement")),
        }
        return notice, {
            "source": "ccn",
            "source_ref": chosen.get("source_ref"),
            "bloc": "bloc_1",
            "raw": chosen,
        }, ccn_candidates

    # Code du travail — filtré par ancienneté
    code_candidates = [
        r for r in bundle["code_items"]
        if _within_effective(r, d)
        and (r.get("scope", {}).get("categorie") in (None, categorie))
        and _anciennete_match(r, anciennete_months)
    ]
    if code_candidates:
        # plus spécifique : ancienneté min la plus élevée
        def _min_months(x):
            rng = (x.get("anciennete_months") or {})
            return _to_int(rng.get("min")) or 0
        chosen = sorted(code_candidates, key=_min_months, reverse=True)[0]
        nm = chosen.get("notice_months", {}) or {}
        notice = {
            "demission": _to_float(nm.get("demission")),
            "licenciement": _to_float(nm.get("licenciement")),
        }
        return notice, {
            "source": "code_travail",
            "source_ref": chosen.get("source_ref"),
            "bloc": "suppletif",
            "raw": chosen,
        }, code_candidates

    return {"demission": None, "licenciement": None}, None, []


# --- SMIC (code du travail / salaire) -----------------------------------------

def _pick_smic(as_of: date) -> Optional[Dict[str, Any]]:
    """
    Retourne le bloc SMIC applicable à la date donnée, ou None.
    Attendu dans rules/code_travail/salaire.yml
    """
    items, _ = _load_yaml(RULES_DIR / "code_travail" / "salaire.yml")
    for r in items:
        eff = r.get("effective") or {}
        f = _parse_date(eff.get("from")) or date.min
        t = _parse_date(eff.get("to")) or date.max
        if f <= as_of <= t:
            return r.get("smic") or {}
    return None

def _syntec_coeff_to_position_label(coeff: Optional[int]) -> Optional[str]:
    """Syntec uniquement : retourne '1.1','1.2','2.1','2.2','2.3','3.1','3.2','3.3' à partir du coeff."""
    if coeff is None:
        return None
    m = {
        240: "1.1", 250: "1.2", 275: "2.1", 310: "2.2",
        355: "2.3", 400: "3.1", 450: "3.2", 500: "3.3",
        95: "1.1", 100: "1.2", 105: "2.1", 115: "2.1",
        130: "2.2", 150: "2.3", 170: "3.1", 210: "3.2", 270: "3.3",
    }
    try:
        c = int(coeff)
    except Exception:
        return None
    return m.get(c)

# --- RÉMUNÉRATION -------------------------------------------------------------

def compute_salary_minimum(
    idcc: Optional[int],
    categorie: str,
    coeff: Optional[int],
    work_time_mode: Optional[str] = None,   # 'standard' | 'forfait_hours' | 'forfait_hours_mod2' | 'forfait_days' | 'part_time'
    weekly_hours: Optional[float] = None,
    forfait_days_per_year: Optional[int] = None,
    classification_level: Optional[str] = None,
    has_13th_month: Optional[bool] = False,  # support 13e mois
    as_of: Optional[str] = None,
) -> Tuple[Dict[str, Optional[float]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    RÉMUNÉRATION — Unifiée (SMIC vs CCN + multiplicateurs + ratio mensuel CCN).
    Retourne (minima, rule, considered)
      minima = {"monthly_min_eur": float|None, "base_min_eur": float|None, "applied": [labels], "details": {...}}
      rule   = {source, source_ref, url?, bloc, effective?, raw?}
    """
    d = date.fromisoformat(as_of) if as_of else date.today()
    cat_key = _normalize_category(idcc, categorie)

    # ---------- 1) SMIC ----------
    smic_block = _pick_smic(d)
    smic_found = bool(smic_block)
    smic_m35   = float(smic_block.get("monthly_35h_eur") or 0.0) if smic_found else 0.0

    def _prorata_35(m35: float, wh: Optional[float]) -> float:
        try:
            return round(m35 * float(wh) / 35.0, 2) if (wh is not None) else m35
        except Exception:
            return m35

    smic_prorata = _prorata_35(smic_m35, weekly_hours) if smic_found else None

    # ---------- 2) CCN ----------
    ccn_base: Optional[float] = None
    applied_labels: List[str] = []

    bundle = _load_rules_bundle("remuneration", idcc) if idcc else {"ccn_extras": {}, "ccn_items": []}
    extras = (bundle.get("ccn_extras") or {})
    grid   = (extras.get("grid") or {})
    meta   = (extras.get("meta") or {})
    mults  = (extras.get("multipliers") or {})

    # Politique (supporte 'policy' et legacy 'compliance')
    policy = (extras.get("policy") or extras.get("compliance") or {})
    ratios = (policy.get("monthly_floor_ratio") or {})
    ratio_default    = float(ratios.get("default") or 1.0)
    ratio_with_13    = float(ratios.get("with_13th_month") or ratio_default)
    ratio_without_13 = float(ratios.get("without_13th_month") or ratio_default)
    if has_13th_month is True:
        ratio_used = ratio_with_13
    elif has_13th_month is False and "without_13th_month" in ratios:
        ratio_used = ratio_without_13
    else:
        ratio_used = ratio_default

    # Grille : supporte 2 formes
    #  a) imbriquée par catégorie : grid[cat_key][str(coeff)]
    #  b) plate :                   grid[str(coeff)]
    if isinstance(grid, dict) and coeff is not None:
        node = grid.get(cat_key)
        if isinstance(node, dict) and str(coeff) in node:
            ccn_base = float(node[str(coeff)])
        elif str(coeff) in grid:
            ccn_base = float(grid[str(coeff)])

    if ccn_base is None and idcc:
        # Fallback ancien 'smh_table'
        dccn = _find_ccn_dir(idcc)
        if dccn:
            ccn_items, _ = _load_yaml(dccn / "remuneration.yml")
            grid_rule = next((r for r in ccn_items if "smh_table" in r), None)
            if grid_rule and coeff is not None:
                table = grid_rule.get("smh_table") or {}
                key_fmt = (grid_rule.get("mapping") or {}).get("key_format") or "{cat}-{coeff}"
                key = key_fmt.format(cat=cat_key, coeff=coeff)
                val = table.get(key)
                if val is not None:
                    ccn_base = float(val)

    # Ajustements CCN selon le mode (Syntec uniquement pour forfait-jours / modalité 2)
    ccn_min: Optional[float] = None
    mode = (work_time_mode or "").lower()
    if ccn_base is not None:
        ccn_val = float(ccn_base)

        # Prorata heures/semaine pour standard / forfait_hours / modalité 2 / part_time
        if mode in {"standard", "forfait_hours", "forfait_hours_mod2", "part_time"} and weekly_hours:
            ccn_val = _prorata_35(ccn_val, weekly_hours)

        # Forfait-jours (cadres Syntec)
        if idcc == SYNTEC_IDCC and mode == "forfait_days" and str(cat_key).upper() == "IC":
            pos_label = _syntec_coeff_to_position_label(coeff) or ""
            is_23 = ("2.3" in (classification_level or "")) or (pos_label == "2.3")
            fj = (mults.get("forfait_jours") or {})
            mult = float(fj.get("p23" if is_23 else "generic") or (1.22 if is_23 else 1.20))
            ccn_val = round(ccn_val * mult, 2)
            applied_labels.append("forfait_jours_122pct" if is_23 else "forfait_jours_120pct")

        # Modalité 2 (cadres Syntec)
        if idcc == SYNTEC_IDCC and mode == "forfait_hours_mod2" and str(cat_key).upper() == "IC":
            m2 = float((mults.get("modalite_2") or {}).get("generic") or 1.15)
            ccn_val = round(ccn_val * m2, 2)
            if "modalite2_115pct" not in applied_labels:
                applied_labels.append("modalite2_115pct")

        ccn_min = ccn_val  # minimum CCN mensuel "brut" (après prorata & éventuels multiplicateurs)

    # Ratio mensuel CCN (après multiplicateurs)
    ccn_monthly_floor: Optional[float] = None
    if ccn_min is not None:
        ccn_monthly_floor = round(ccn_min * ratio_used, 2)
        if ratio_used != 1.0:
            applied_labels.append(f"ccn_monthly_ratio_{ratio_used:.2f}")

    # ---------- 3) Arbitrage plancher ----------
    # Règle : floor = max(SMIC_prorata, CCN_monthly_floor)
    if ccn_monthly_floor is None and smic_prorata is None:
        return {"monthly_min_eur": None, "base_min_eur": None, "applied": applied_labels}, None, []

    if smic_prorata is None:
        floor = ccn_monthly_floor
        source, source_ref, bloc = "ccn", (meta.get("source", {}) or {}).get("article"), "bloc_1"
    elif ccn_monthly_floor is None:
        floor = smic_prorata
        source, source_ref, bloc = "code_travail", "SMIC (35h proratisé)", "ordre_public"
    else:
        floor = max(smic_prorata, ccn_monthly_floor)
        if ccn_monthly_floor >= smic_prorata:
            source, source_ref, bloc = "ccn", (meta.get("source", {}) or {}).get("article"), "bloc_1"
        else:
            source, source_ref, bloc = "code_travail", "SMIC (35h proratisé)", "ordre_public"

    res = {
        "monthly_min_eur": float(round(floor, 2)),
        "base_min_eur": float(round(ccn_base, 2)) if ccn_base is not None else None,  # référence hiérarchique CCN
        "applied": applied_labels,
        "details": {
            "ccn_monthly_floor_eur": ccn_monthly_floor,
            "ratio_used": ratio_used,
        }
    }
    rule = {
        "source": source,
        "source_ref": source_ref,
        "url": (meta.get("source", {}) or {}).get("url"),
        "extension_jorf": (meta.get("source", {}) or {}).get("extension_jorf"),
        "bloc": bloc,
        "effective": (meta.get("effective_from") or None),
        "raw": {
            "cat": cat_key, "coeff": coeff, "mode": mode,
            "ccn_min_after_multipliers": ccn_min,
            "has_13th": bool(has_13th_month),
        },
    }
    return res, rule, []


def compute_worktime_bounds(
    idcc: Optional[int],
    work_time_mode: str,
    weekly_hours: Optional[float] = None,
    forfait_days_per_year: Optional[int] = None,
    as_of: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    TEMPS DE TRAVAIL — Renvoie des bornes selon le mode :
      standard | part_time | forfait_hours | forfait_hours_mod2 | forfait_days
    """
    _ = date.fromisoformat(as_of) if as_of else date.today()

    bounds: Dict[str, Any] = {}
    chosen: Optional[Dict[str, Any]] = None
    considered: List[Dict[str, Any]] = []

    # 1) Code du travail (standard / part_time / forfait_hours)
    code_items, _extras = _load_yaml(RULES_DIR / "code_travail" / "temps_travail.yml")
    for r in code_items:
        if r.get("scope", {}).get("work_time_mode") == work_time_mode:
            considered.append(r)
            c = r.get("constraint") or {}
            if work_time_mode in {"standard", "part_time", "forfait_hours"}:
                bounds = {
                    "weekly_hours_min": c.get("weekly_hours_min"),
                    "weekly_hours_max": c.get("weekly_hours_max"),
                }
                # Info supplémentaire pour l’explain (moyenne 12 semaines)
                if "average_12_weeks_max" in c:
                    bounds["average_12_weeks_max"] = c.get("average_12_weeks_max")
                chosen = {
                    "source": "code_travail",
                    "source_ref": r.get("source_ref") or "Temps de travail — Code du travail",
                    "bloc": "ordre_public",
                }
            # si on a trouvé une règle code, on s'arrête ici pour ce mode
            break

    # 2) CCN — Forfait‑jours (plafond)
    if work_time_mode == "forfait_days" and idcc:
        dccn = _find_ccn_dir(idcc)
        if dccn:
            ccn_items, _ = _load_yaml(dccn / "temps_travail.yml")
            fj = next((r for r in ccn_items if r.get("scope", {}).get("work_time_mode") == "forfait_days"), None)
            if fj:
                considered.append(fj)
                c = fj.get("constraint") or {}
                bounds = {"days_per_year_max": c.get("days_per_year_max")}
                chosen = {
                    "source": "ccn",
                    "source_ref": fj.get("source_ref") or "Forfait‑jours (CCN)",
                    "bloc": "bloc_1",
                }

    # 3) CCN — Modalité 2 (forfait hours mod2)
    if work_time_mode == "forfait_hours_mod2" and idcc:
        dccn = _find_ccn_dir(idcc)
        if dccn:
            ccn_items, _ = _load_yaml(dccn / "temps_travail.yml")
            m2 = next((r for r in ccn_items if r.get("scope", {}).get("work_time_mode") == "forfait_hours_mod2"), None)
            if m2:
                considered.append(m2)
                c = m2.get("constraint") or {}
                bounds = {
                    "weekly_hours_min": c.get("weekly_hours_min"),
                    "weekly_hours_max": c.get("weekly_hours_max"),
                }
                if "days_per_year_cap" in c:
                    bounds["days_per_year_max"] = c.get("days_per_year_cap")
                chosen = {
                    "source": "ccn",
                    "source_ref": m2.get("source_ref") or "Modalité 2 (CCN)",
                    "bloc": "bloc_1",
                }

    return bounds, chosen, considered


def compute_leave_minimum(
    idcc: Optional[int],
    anciennete_months: Optional[int],
    unit: str = "ouvrés",
    as_of: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    CONGÉS PAYÉS — Calcule le minimum légal et une suggestion (bonus CCN d’ancienneté si présent).
    Scalable : toute CCN peut fournir un barème 'anciennete_bonus_ouvres' dans ccn/<idcc>/conges_payes.yml.
    """
    # Base légale
    code_items, _ = _load_yaml(RULES_DIR / "code_travail" / "conges_payes.yml")
    base = next((r for r in code_items if r.get("key") == "cp_base"), None) or {}
    b = (base.get("base") or {})
    min_ouvres = int(b.get("jours_ouvres") or 25)
    min_ouvrables = int(b.get("jours_ouvrables") or 30)

    # Valeurs par défaut
    unit_l = (unit or "").lower()
    suggested: Optional[int] = None
    rule: Dict[str, Any] = {"source": "code_travail", "source_ref": "L3141-3", "bloc": "ordre_public"}
    considered: List[Dict[str, Any]] = [base] if base else []

    # --- Bonus d’ancienneté CCN (générique) ---
    if idcc:
        dccn = _find_ccn_dir(idcc)
        if dccn:
            bonus_items, extras = _load_yaml(dccn / "conges_payes.yml")
            sch = None
            for r in bonus_items:
                key = (r.get("key") or "").lower()
                if key in {"anciennete_bonus_ouvres", "anciennete_bonus"}:
                    sch = r
                    break
            if sch:
                considered.append(sch)
                schedule = sch.get("bonus_schedule") or {}
                years = (anciennete_months or 0) // 12
                eligible = [int(y) for y in schedule.keys() if years >= int(y)]
                bonus_ouvres = 0
                if eligible:
                    k = str(max(eligible))  # clé string
                    try:
                        bonus_ouvres = int(schedule.get(k, 0))
                    except Exception:
                        bonus_ouvres = 0

                src_meta = ((extras.get("meta") or {}).get("source") or {})
                src_label = src_meta.get("article") or sch.get("source_ref") or "CCN — Congés"

                if "ouvrés" in unit_l or "ouvres" in unit_l:
                    suggested = min_ouvres + bonus_ouvres
                    rule = {"source": "ccn", "source_ref": src_label, "bloc": "bloc_1"}
                else:
                    # conversion simple ouvrés -> ouvrables ≈ ×1,2
                    suggested = min_ouvrables + int(round(bonus_ouvres * 1.2))
                    rule = {"source": "ccn", "source_ref": f"{src_label} (conversion ~)", "bloc": "bloc_1"}

    # À défaut de bonus CCN, on suggère la base légale dans l’unité choisie
    if suggested is None:
        suggested = min_ouvres if ("ouvrés" in unit_l or "ouvres" in unit_l) else min_ouvrables

    res = {
        "min_days": min_ouvres if ("ouvrés" in unit_l or "ouvres" in unit_l) else min_ouvrables,
        "suggested_days": int(suggested),
    }
    return res, rule, considered


def load_classification_schema(idcc: Optional[int]) -> Dict[str, Any]:
    """
    Renvoie un schéma de classification pour l'IDCC donné, sinon un fallback générique.
    """
    schema: Dict[str, Any] = {}
    d = _find_ccn_dir(idcc) if idcc else None
    p = (d / "classification.yml") if d else None
    if p and p.exists():
        schema = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    if not schema:
        # Fallback générique minimal
        schema = {
            "meta": {
                "label": "Générique",
                "mapping": {
                    "categorie_to_backend": {"cadre": "cadre", "noncadre": "non-cadre"},
                    "classification_format": "{text}"
                }
            },
            "categories": []  # pas de positions => UI bascule en champ libre
        }
    return schema
