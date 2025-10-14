# app/services/rules_resolver.py
from __future__ import annotations

from pathlib import Path
from datetime import date
from typing import Optional, Dict, Any, List
import yaml

# Moteur bas-niveau (on réutilise les compute_* existants)
from app.services.rules_engine import (
    compute_probation_bounds,
    compute_notice_bounds,
    compute_salary_minimum,
    compute_worktime_bounds,
    compute_leave_minimum,
    _find_ccn_dir,
)
from app.services.ui_hints import load_ui_hints, build_rule_explain

# Dossiers (alignés sur rules_engine.py)
APP_DIR = Path(__file__).resolve().parents[1]   # .../app
RULES_DIR = APP_DIR.parent / "rules"            # .../rules

SYNTEC_IDCC = 1486

# -------------------- utils locaux --------------------

def _load_yaml(p: Path):
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def _match_list_or_scalar(value, cond) -> bool:
    if cond is None:
        return True
    if isinstance(cond, list):
        return value in cond
    return value == cond



# -------------------- RESOLVE (v1) --------------------

def _safe_rule(rule: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rule:
        return None
    return {
        "source": rule.get("source"),
        "source_ref": rule.get("source_ref"),
        "bloc": rule.get("bloc"),
        "url": rule.get("url"),
        "effective": rule.get("effective"),
    }

def resolve(theme: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Résolveur générique v1 — unifie le format de retour.

    Entrée (ctx attendu) :
      idcc, categorie, coeff, as_of, work_time_mode, weekly_hours, forfait_days_per_year,
      classification_level, has_13th_month, anciennete_months, unit

    Sortie :
      {
        "theme": "<nom>",
        "bounds"/"notice"/"minima"/"conges": ...,
        "rule": {...},
        "capabilities": {...},
        "explain": [...],
        "suggest": [...],
        "trace": {...}
      }
    """
    theme = (theme or "").strip().lower()
    idcc = ctx.get("idcc")
    categorie = ctx.get("categorie") or "non-cadre"
    coeff = ctx.get("coeff")
    as_of = ctx.get("as_of") or date.today().isoformat()
    work_time_mode = (ctx.get("work_time_mode") or "standard").lower()
    weekly_hours = ctx.get("weekly_hours")
    forfait_days_per_year = ctx.get("forfait_days_per_year")
    anciennete_months = ctx.get("anciennete_months")

    explain: List[Dict[str, Any]] = []
    suggest: List[Dict[str, Any]] = []
    capabilities: Dict[str, Any] = {}
    trace: Dict[str, Any] = {"inputs": ctx}

    # (Depuis l'adoption de la classification étape 4, on ne pilote plus de Q&A
    #  à la volée côté backend. Les informations nécessaires sont collectées
    #  dans l'UI avant les calculs.)

    # ---- CLASSIFICATION ----------------------------------------------------
    if theme in {"classification", "classif"}:
        explain = load_ui_hints(idcc, "classification", {
            "idcc": idcc, "categorie": categorie, "coeff": coeff
        })
        return {
            "theme": "classification",
            "rule": None,
            "capabilities": {},
            "explain": explain,
            "suggest": [],
            "trace": {"inputs": ctx},
        }

    # ---- TEMPS DE TRAVAIL --------------------------------------------------
    if theme in {"temps_travail", "temps", "worktime"}:
        bounds, rule, considered = compute_worktime_bounds(
            idcc=idcc,
            work_time_mode=work_time_mode,
            weekly_hours=weekly_hours,
            forfait_days_per_year=forfait_days_per_year,
            as_of=as_of,
            segment=ctx.get("segment"),
            statut=ctx.get("statut"),
        )
        trace["considered"] = considered

        # Capabilities par défaut (v1)
        capabilities = {
            "work_time_modes": {
                "standard": True,
                "part_time": True,
                "forfait_hours": True,
                "forfait_hours_mod2": True,
                "forfait_days": True,
                "modulation": False,
            },
            "defaults": {},
        }
        # Modalité 2: spécifique Syntec (IDCC 1486). Désactiver par défaut ailleurs.
        if idcc != SYNTEC_IDCC:
            capabilities["work_time_modes"]["forfait_hours_mod2"] = False
        # Modulation: exposée pour CCN 0016 (TRV / SANITAIRE / DEMENAGEMENT)
        try:
            seg = str(ctx.get("segment") or "").strip().upper()
            if idcc == 16 and seg in {"TRV", "SANITAIRE", "DEMENAGEMENT"}:
                capabilities["work_time_modes"]["modulation"] = True
        except Exception:
            pass
        if bounds.get("days_per_year_max") is not None:
            capabilities["defaults"]["forfait_days_per_year"] = int(bounds["days_per_year_max"])

        # Propager les règles TP (coupures/amplitude) si le moteur les a exposées dans bounds._capabilities
        try:
            bcap = (bounds.get("_capabilities") or {})
            if isinstance(bcap.get("part_time_rules"), dict):
                # Pré-remplir la durée max de coupure si connue
                thr = bcap["part_time_rules"].get("break_threshold_hours")
                if thr is not None:
                    capabilities["defaults"]["pt_break_max_hours"] = thr
                capabilities["part_time_rules"] = bcap["part_time_rules"]
        except Exception:
            pass

        # Encarts factorisés + Hints CCN
        explain.extend(build_rule_explain("temps_travail", bounds, rule, ctx))
        explain.extend(load_ui_hints(idcc, "temps_travail", {
            "idcc": idcc,
            "categorie": categorie,
            "coeff": coeff,
            "work_time_mode": work_time_mode,
            "segment": ctx.get("segment"),
            "statut": ctx.get("statut"),
            "annexe": ctx.get("annexe"),
        }))

        # Ventilation & majorations — forfait-heures (hint générique légal)
        try:
            if work_time_mode == "forfait_hours" and isinstance(weekly_hours, (int, float)):
                wh = float(weekly_hours)
                hs = max(0.0, wh - 35.0)
                if wh > 35.0:
                    txt = (
                        f"Ventilation indicative : base 35 h + {hs:.2f} h supplémentaires incluses. "
                        "Majoration légale de référence : +25 % (36–43 h), +50 % (≥ 44 h), sauf dispositions conventionnelles plus favorables."
                    )
                    explain.append({
                        "kind": "info",
                        "slot": "step5.block.fh",
                        "text": txt,
                        "ref": "C. trav., L3121‑33 s. (heures supplémentaires)",
                        "url": "https://www.legifrance.gouv.fr/codes/id/LEGIARTI000037389785/"
                    })
        except Exception:
            pass


        # (Conservé pour compat explicite HCR)
        if idcc == 1979:
            capabilities["work_time_modes"]["forfait_hours_mod2"] = False

        res = {
            "theme": "temps_travail",
            "bounds": bounds,
            "rule": _safe_rule(rule),
            "capabilities": capabilities,
            "explain": explain,
            "suggest": suggest,
            "trace": trace,
        }
        return res

    # ---- PÉRIODE D’ESSAI ---------------------------------------------------
    if theme in {"periode_essai", "essai", "probation"}:
        bounds, rule, considered = compute_probation_bounds(
            idcc=idcc,
            categorie=categorie,
            contract_start=as_of,
            coeff=coeff,
            annexe=ctx.get("annexe"),
            statut=ctx.get("statut"),
        )
        trace["considered"] = considered

        # Encarts + suggestion
        explain.extend(build_rule_explain("periode_essai", bounds, rule, ctx))
        if bounds.get("max_months") is not None:
            suggest.append({"field": "probation_months", "value": float(bounds["max_months"])})
        # Hints CCN
        explain.extend(load_ui_hints(idcc, "periode_essai", {"idcc": idcc, "categorie": categorie, "coeff": coeff}))

        # --- Hints "droit commun" affichés partout (slots dédiés) ---
        explain.append({
            "slot": "step7.prior",
            "kind": "info",
            "text": "CDI après CDD : la période d’essai du CDI est réduite de la durée du CDD (suppression si la durée déjà accomplie excède le plafond).",
            "ref": "Code du travail — poursuite CDD en CDI",
            "url": "https://code.travail.gouv.fr/contribution/quelle-est-la-duree-maximale-de-la-periode-dessai-sans-et-avec-renouvellement"
        })

        explain.append({
            "slot": "step7.prior",
            "kind": "info",
            "text": "CDI après stage : (i) stage de fin d’études avec embauche dans les 3 mois → déduction dans la limite de la moitié de l’essai ; (ii) si l’emploi correspond aux activités du stage → déduction intégrale.",
            "ref": "C. trav., L1221‑24",
            "url": "https://www.legifrance.gouv.fr/codes/id/LEGIARTI000037389885"
        })

        explain.append({
            "slot": "step7.renewal",
            "kind": "info",
            "text": "Renouvellement : possible une seule fois uniquement si un accord de branche étendu l’autorise et en fixe les conditions ; la possibilité doit être prévue au contrat et le salarié doit donner son accord durant l’essai initial.",
            "ref": "C. trav., L1221‑21 à L1221‑23",
            "url": "https://www.legifrance.gouv.fr/codes/id/LEGIARTI000043565932"
        })

        return {
            "theme": "periode_essai",
            "bounds": bounds,
            "rule": _safe_rule(rule),
            "capabilities": {},
            "explain": explain,
            "suggest": suggest,
            "trace": trace,
        }

    # ---- PRÉAVIS -----------------------------------------------------------
    if theme in {"preavis", "notice"}:
        notice, rule, considered = compute_notice_bounds(
            idcc=idcc,
            categorie=categorie,
            anciennete_months=anciennete_months,
            coeff=coeff,
            as_of=as_of,
            annexe=ctx.get("annexe"),
            segment=ctx.get("segment"),
            statut=ctx.get("statut"),
            coeff_key=ctx.get("coeff_key"),
        )
        trace["considered"] = considered

        # Suggestions
        dmin = notice.get("demission")
        lmin = notice.get("licenciement")
        if dmin is not None:
            suggest.append({"field": "notice_resignation_months", "value": float(dmin)})
        if lmin is not None:
            suggest.append({"field": "notice_dismissal_months", "value": float(lmin)})

        # Encarts factorisés + hints
        explain.extend(build_rule_explain("preavis", notice, rule, ctx))
        explain.extend(load_ui_hints(idcc, "preavis", {"idcc": idcc, "categorie": categorie, "coeff": coeff}))

        res = {
            "theme": "preavis",
            "notice": notice,
            "rule": _safe_rule(rule),
            "capabilities": {},
            "explain": explain,
            "suggest": suggest,
            "trace": trace,
        }
        return res

   # ---- RÉMUNÉRATION ------------------------------------------------------
    if theme in {"remuneration", "salaire"}:
        minima, rule, _ = compute_salary_minimum(
            idcc=idcc,
            categorie=categorie,
            coeff=coeff,
            work_time_mode=work_time_mode,
            weekly_hours=weekly_hours,
            forfait_days_per_year=forfait_days_per_year,
            classification_level=ctx.get("classification_level"),
            coeff_key=ctx.get("coeff_key"),
            has_13th_month=bool(ctx.get("has_13th_month")),
            as_of=as_of,
            anciennete_months=ctx.get("anciennete_months"),
            annexe=ctx.get("annexe"),
            segment=ctx.get("segment"),
            statut=ctx.get("statut"),
        )

        # Suggestion salaire mensuel si connu
        if minima.get("monthly_min_eur") is not None:
            suggest.append({"field": "salary_gross_monthly", "value": float(minima["monthly_min_eur"])})

        # Encarts + hints
        explain.extend(build_rule_explain("remuneration", minima, rule, ctx))
        explain.extend(load_ui_hints(idcc, "remuneration", {
            "idcc": idcc, "categorie": categorie, "coeff": coeff,
            "work_time_mode": work_time_mode
        }))

        # --- HCR : simulateur mensuel avec HS (10/20/50) ---
        try:
            if (idcc == 1979
                and (work_time_mode in {"standard", "forfait_hours"})
                and isinstance(weekly_hours, (int, float)) and weekly_hours > 35
                and isinstance(minima.get("base_min_eur"), (int, float))):
                base35 = float(minima["base_min_eur"])  # mensuel 35h CCN
                h_rate = base35 / 151.67

                w = float(weekly_hours)
                h1 = max(0.0, min(w, 39.0) - 35.0)  # 36-39 → +10%
                h2 = max(0.0, min(w, 43.0) - 39.0)  # 40-43 → +20%
                h3 = max(0.0, w - 43.0)             # ≥44 → +50%
                weeks_per_month = 52.0 / 12.0

                extra = weeks_per_month * h_rate * (1.10*h1 + 1.20*h2 + 1.50*h3)
                sim_monthly = round(base35 + extra, 2)

                explain.append({
                    "kind": "info",
                    "slot": "step6.more.minima",
                    "text": (f"Simulation HCR pour {w:.2f} h/sem : "
                            f"≈ {sim_monthly:,.2f} € bruts/mois "
                            f"(35h CCN + HS : 10% (36–39h), 20% (40–43h), 50% (≥44h))."),
                    "ref": "Majoration HS HCR",
                    "url": "https://www.legifrance.gouv.fr/conv_coll/id/KALISCTA000005713679"
                })
        except Exception:
            pass

        res = {
            "theme": "remuneration",
            "minima": minima,
            "rule": _safe_rule(rule),
            "capabilities": {},
            "explain": explain,
            "suggest": suggest,
            "trace": {"inputs": ctx},
        }
        return res

    # ---- CONGÉS PAYÉS ------------------------------------------------------
    if theme in {"conges_payes", "conges"}:
        conges, rule, _ = compute_leave_minimum(
            idcc=idcc, anciennete_months=anciennete_months, unit=ctx.get("unit") or "ouvrés", as_of=as_of
        )
        # Suggestion nombre de jours
        if conges.get("suggested_days") is not None:
            suggest.append({"field": "cp_days_number", "value": int(conges["suggested_days"])})

        # Encarts + hints
        explain.extend(build_rule_explain("conges", conges, rule, ctx))
        explain.extend(load_ui_hints(idcc, "conges_payes", {"idcc": idcc, "categorie": categorie, "coeff": coeff}))

        return {
            "theme": "conges_payes",
            "conges": conges,
            "rule": _safe_rule(rule),
            "capabilities": {},
            "explain": explain,
            "suggest": suggest,
            "trace": {"inputs": ctx},
        }

    # Thème inconnu
    return {
        "theme": theme,
        "error": "unknown_theme",
        "trace": {"inputs": ctx},
    }


# -------- Compat API (anciens handlers appellent resolve_theme) ---------------

def resolve_theme(theme: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Alias rétro‑compat pour les handlers plus anciens."""
    return resolve(theme, ctx)
