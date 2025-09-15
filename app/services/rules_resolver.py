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


# -------------------- Questions génériques (Phase 1) --------------------
# Réutilisables par plusieurs thèmes pour le Q&A progressif.
GENERIC_QUESTIONS = {
    "work_time_mode": {
        "id": "work_time_mode",
        "label": "Régime du temps de travail",
        "type": "enum",
        "options": [
            {"value": "standard", "label": "35h/hebdo"},
            {"value": "part_time", "label": "Temps partiel"},
            {"value": "forfait_hours", "label": "Forfait heures"},
            {"value": "forfait_days", "label": "Forfait jours"}
        ],
        "writes": ["work_time_mode"],
        "required": True,
        "reason": "worktime.mode_required"
    },
    "anciennete_months": {
        "id": "anciennete_months",
        "label": "Ancienneté (mois)",
        "type": "number",
        "writes": ["anciennete_months"],
        "required": True,
        "reason": "salary.seniority_required"
    }
}

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

    # Chargement des questions CCN (classification.yml) — Phase 1
    # Indexe par identifiant pour un accès direct (ex: q_index["annexe"]).
    q_index: Dict[str, Dict[str, Any]] = {}
    try:
        if idcc:
            dccn_dir = _find_ccn_dir(idcc)  # depuis rules_engine
            if dccn_dir:
                classif_data = _load_yaml(dccn_dir / "classification.yml") or {}
                questions = classif_data.get("questions") or []
                if isinstance(questions, list):
                    for q in questions:
                        if isinstance(q, dict) and q.get("id"):
                            q_index[str(q["id"])]= q
    except Exception:
        # En cas d'erreur d'I/O YAML, on continue sans questions CCN
        q_index = {}

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
            },
            "defaults": {},
        }
        # Modalité 2: spécifique Syntec (IDCC 1486). Désactiver par défaut ailleurs.
        if idcc != SYNTEC_IDCC:
            capabilities["work_time_modes"]["forfait_hours_mod2"] = False
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
            "idcc": idcc, "categorie": categorie, "coeff": coeff,
            "work_time_mode": work_time_mode
        }))


        # (Conservé pour compat explicite HCR)
        if idcc == 1979:
            capabilities["work_time_modes"]["forfait_hours_mod2"] = False

        # -------------------- pending_inputs (Phase 1) --------------------
        pending_inputs: List[Dict[str, Any]] = []

        # 1) Work time mode manquant
        if ctx.get("work_time_mode") is None:
            try:
                q = dict(GENERIC_QUESTIONS.get("work_time_mode") or {})
                if q:
                    pending_inputs.append(q)
            except Exception:
                pass

        # 2) Statut manquant pour certains segments de la CCN 0016
        if idcc == 16:
            seg = ctx.get("segment")
            if seg in {"TRM_AAT", "TRV", "SANITAIRE"} and ctx.get("statut") is None:
                if "statut" in q_index:
                    try:
                        q = dict(q_index["statut"])  # copie défensive
                        q["required"] = True
                        q.setdefault("reason", "worktime.statut_required")
                        pending_inputs.append(q)
                    except Exception:
                        pass

        res = {
            "theme": "temps_travail",
            "bounds": bounds,
            "rule": _safe_rule(rule),
            "capabilities": capabilities,
            "explain": explain,
            "suggest": suggest,
            "trace": trace,
        }
        if pending_inputs:
            res["pending_inputs"] = pending_inputs
        return res

    # ---- PÉRIODE D’ESSAI ---------------------------------------------------
    if theme in {"periode_essai", "essai", "probation"}:
        bounds, rule, considered = compute_probation_bounds(
            idcc=idcc, categorie=categorie, contract_start=as_of, coeff=coeff
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
            idcc=idcc, categorie=categorie, anciennete_months=anciennete_months, coeff=coeff, as_of=as_of
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

        # -------------------- pending_inputs (Phase 1) --------------------
        pending_inputs: List[Dict[str, Any]] = []
        # Annexe manquante (si question disponible côté CCN)
        if ("annexe" in q_index) and (ctx.get("annexe") is None):
            try:
                q = dict(q_index["annexe"])  # copie défensive
                q["required"] = True
                q["reason"] = "notice.annexe_required"
                pending_inputs.append(q)
            except Exception:
                pass
        # Coefficient manquant (si question group_coeff disponible)
        if ctx.get("coeff") is None and ("group_coeff" in q_index):
            try:
                q = dict(q_index["group_coeff"])  # copie défensive
                q["required"] = True
                q["reason"] = "notice.coeff_missing"
                pending_inputs.append(q)
            except Exception:
                pass

        res = {
            "theme": "preavis",
            "notice": notice,
            "rule": _safe_rule(rule),
            "capabilities": {},
            "explain": explain,
            "suggest": suggest,
            "trace": trace,
        }
        if pending_inputs:
            res["pending_inputs"] = pending_inputs
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
            has_13th_month=bool(ctx.get("has_13th_month")),
            as_of=as_of,
            anciennete_months=ctx.get("anciennete_months"),
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

        # -------------------- pending_inputs (Phase 1) --------------------
        pending_inputs: List[Dict[str, Any]] = []

        # 1) Coefficient manquant
        if ctx.get("coeff") is None:
            if "group_coeff" in q_index:
                try:
                    q = dict(q_index["group_coeff"])  # copie défensive
                    q["required"] = True
                    q["reason"] = "salary.coeff_missing"
                    pending_inputs.append(q)
                except Exception:
                    pass
            else:
                pending_inputs.append({
                    "id": "coeff",
                    "label": "Coefficient",
                    "type": "number",
                    "writes": ["coeff"],
                    "required": True,
                    "reason": "salary.coeff_missing",
                })

        # 2) Segment manquant (si question disponible dans la CCN)
        if ("segment" in q_index) and (ctx.get("segment") is None):
            try:
                q = dict(q_index["segment"])  # copie défensive
                q["required"] = True
                q["reason"] = "salary.segment_required"
                pending_inputs.append(q)
            except Exception:
                pass

        # 3) Ancienneté manquante — forfait-jours (2216)
        if (
            idcc == 2216
            and (str(work_time_mode or "").lower() == "forfait_days")
            and (str(categorie or "").lower() in {"cadre", "ic"})
            and (ctx.get("anciennete_months") is None)
        ):
            try:
                q = dict(GENERIC_QUESTIONS.get("anciennete_months") or {})
                if q:
                    pending_inputs.append(q)
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
        if pending_inputs:
            res["pending_inputs"] = pending_inputs
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
