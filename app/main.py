# app/main.py

# Standard library
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any
import json
import re
import logging

# Third-party
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from io import BytesIO
import yaml

from app.schemas import (
    WorktimeResponse, SalaryResponse, EssaiResponse, PreavisResponse, CongesResponse
)


# Local modules
from app.services.pdf_renderer import render_pdf, render_pdf_bytes

# --- logger minimal (n'affecte pas la prod) ---
logger = logging.getLogger("eds")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# --- chemins sûrs (absolus) ---
APP_DIR = Path(__file__).resolve().parent                 # .../app
UI_TEMPLATES_DIR = APP_DIR / "templates" / "ui"           # .../app/templates/ui
STATIC_DIR = APP_DIR / "static"

# --- app FastAPI ---
app = FastAPI(title="EDS", version="0.1")

# --- statiques ---
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- moteur de templates ---
templates = Jinja2Templates(directory=str(UI_TEMPLATES_DIR))

# ========== Imports best‑effort ==========

# CCN registry (liste dynamique)
try:
    from app.services.ccn_registry import search_ccn as _ccn_search
except Exception as e:
    logger.warning("ccn_registry indisponible (%s) — fallback statique", e)
    def _ccn_search(q: Optional[str] = None):
        items = [
            {"idcc": 1486, "label": "Bureaux d’études techniques (Syntec)", "slug": "1486-syntec"},
            {"idcc": 1979, "label": "Hôtels, cafés, restaurants (HCR)", "slug": "1979-hcr"},
            {"idcc": 2216, "label": "Commerce de détail & de gros à prédominance alimentaire", "slug": "2216-predominance-alimentaire"},
        ]
        if not q:
            return items
        s = str(q).strip().lower()
        return [it for it in items if s in str(it["idcc"]) or s in it["label"].lower()]

# Bas niveau: schéma de classification (moteur de règles)
try:
    from app.services.rules_engine import load_classification_schema
except Exception as e:
    logger.warning("rules_engine.load_classification_schema indisponible (%s)", e)
    load_classification_schema = None

# Fallback de calcul salaire (si le resolver ne renvoie rien)
try:
    from app.services.rules_engine import compute_salary_minimum as _compute_salary_min_legacy
except Exception as e:
    logger.warning("rules_engine.compute_salary_minimum indisponible (%s)", e)
    _compute_salary_min_legacy = None

# Resolver (unique)
try:
    from app.services.rules_resolver import resolve as resolve_theme
except Exception as e:
    logger.warning("rules_resolver.resolve indisponible (%s)", e)
    resolve_theme = None

# --- Doc registry (catalogue) ---
try:
    from app.services.doc_registry import list_documents, get_document
except Exception as e:
    logger.warning("doc_registry indisponible (%s) — utilisation d'un fallback interne", e)

    def list_documents():
        # Fallback : 3 cartes dont 2 "bientôt"
        return [
            {"key": "cdi", "label": "CDI", "template": "cdi_form.html.j2", "status": "ready"},
            {"key": "cdd", "label": "CDD", "template": "coming_soon.html.j2", "status": "soon"},
            {"key": "convocation", "label": "Convocation à entretien préalable",
             "template": "coming_soon.html.j2", "status": "soon"},
        ]

    def get_document(k: str):
        for d in list_documents():
            if d["key"] == k:
                return d
        return None

# --- Clauses (catalogue) ---
try:
    from app.services.clauses_library import load_clauses_catalog, get_clause_texts
except Exception as e:
    logger.warning("clauses_library indisponible (%s)", e)
    def load_clauses_catalog(idcc: Optional[int] = None): return {"items": []}
    def get_clause_texts(idcc: Optional[int], keys): return []


# ========== Helpers ==========
def _today_iso() -> str:
    return date.today().isoformat()

def _smart_name_case(s: Optional[str]) -> Optional[str]:
    """Met en forme un nom/prénom proprement pour affichage (PDF).
    - Capitalise chaque mot,
    - Particules usuelles en minuscules (de, du, des, le, la, les, d', l'),
    - Gère les traits d'union et apostrophes ("'" et « ’ »).
    Ne modifie pas si la chaîne est vide/None.
    """
    if not s:
        return s
    text = str(s).strip()
    if not text:
        return text
    particles = {"de", "du", "des", "le", "la", "les", "da", "di", "del", "della", "van", "von"}
    apos = {"'", "’"}
    def capseg(seg: str) -> str:
        return seg[:1].upper() + seg[1:].lower() if seg else seg
    def capword(w: str) -> str:
        if not w:
            return w
        for ap in apos:
            if ap in w:
                p = w.split(ap)
                if len(p) == 2 and p[0].lower() in {"d", "l"}:
                    return p[0].lower() + ap + capseg(p[1])
        if '-' in w:
            return '-'.join(capseg(x) for x in w.split('-'))
        lw = w.lower()
        if lw in particles:
            return lw
        return capseg(w)
    return " ".join(capword(tok) for tok in text.split())
def _safe_rule(rule: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Ne renvoie que les métadonnées utiles au front."""
    if not rule:
        return None
    return {
        "source": rule.get("source"),
        "source_ref": rule.get("source_ref"),
        "bloc": rule.get("bloc"),
        "url": rule.get("url"),
        "effective": rule.get("effective"),
    }

def _map_worktime_mode_ui_to_api(wt_ui: Optional[str]) -> str:
    """
    UI → API :
      'standard_35h' -> 'standard'
      'modalite_2'   -> 'forfait_hours_mod2'
      sinon: identique ('forfait_hours' | 'forfait_days' | 'part_time')
    """
    wt = (wt_ui or "").lower()
    if wt == "standard_35h":
        return "standard"
    if wt == "modalite_2":
        return "forfait_hours_mod2"
    # CCN 0016 — modes TRV/SAN/DEM mappés sur 'standard' côté API
    if wt in {"trv_70q", "trv_39rtt", "san_39rtt", "dem_39rtt"}:
        return "standard"
    return wt

def _call_resolver(theme: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Appelle resolve(theme, ctx) en robustesse et renvoie un payload standard.
    En cas d'indispo, renvoie un squelette neutre (les fallbacks UI restent).
    """
    if not resolve_theme:
        logger.warning("resolve_theme() indisponible — renvoi neutre pour %s", theme)
        return {
            "bounds": {}, "rule": {}, "capabilities": {},
            "explain": [], "suggest": [],
            "trace": {"theme": theme, "inputs": ctx, "error": "no_resolve"}
        }
    try:
        return resolve_theme(theme, ctx)
    except Exception as e:
        logger.warning("resolve_theme(%s) a échoué: %s", theme, e)
        return {
            "bounds": {}, "rule": {}, "capabilities": {},
            "explain": [], "suggest": [],
            "trace": {"theme": theme, "inputs": ctx, "error": str(e)}
        }

def _norm_minima(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise les différentes formes possibles en un bloc uniforme."""
    raw = raw or {}
    # forme attendue
    if "monthly_min_eur" in raw:
        out = {
            "monthly_min_eur": raw.get("monthly_min_eur"),
            "base_min_eur": raw.get("base_min_eur"),
            "applied": raw.get("applied") or [],
        }
        det = raw.get("details") or {}
        if out["base_min_eur"] is None and "ccn_min_prorata_or_fj" in det:
            out["base_min_eur"] = det.get("ccn_min_prorata_or_fj")
        if not out["applied"] and det.get("labels"):
            out["applied"] = det.get("labels")
        return out
    # forme "large" possible
    if "min_monthly_eur" in raw:
        det = raw.get("details") or {}
        return {
            "monthly_min_eur": raw.get("min_monthly_eur"),
            "base_min_eur": raw.get("base_min_eur") or det.get("ccn_min_prorata_or_fj"),
            "applied": raw.get("applied") or det.get("labels") or [],
        }
    return {"monthly_min_eur": None, "base_min_eur": None, "applied": []}


# ========== Routes UI ==========

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html.j2", {"request": request})

@app.get("/api/ccn/list")
async def api_ccn_list(q: Optional[str] = None):
    try:
        items = _ccn_search(q)
    except Exception as e:
        logger.warning("api_ccn_list failed: %s", e)
        items = []
    return JSONResponse({"items": items})

@app.get("/cdi", response_class=HTMLResponse)
async def cdi_form(request: Request):
    return templates.TemplateResponse("cdi_form.html.j2", {"request": request})

# ========== Catalogue multi-documents ==========
@app.get("/documents", response_class=HTMLResponse, name="documents_list")
async def documents_list(request: Request):
    docs = list_documents()
    return templates.TemplateResponse("documents_list.html.j2", {"request": request, "documents": docs})

@app.get("/documents/{dockey}", response_class=HTMLResponse, name="document_form")
async def document_form(request: Request, dockey: str):
    doc = get_document(dockey)
    if not doc:
        return HTMLResponse(f"Document inconnu : {dockey}", status_code=404)
    tpl = (doc.get("template") or "").strip()
    if not tpl:
        return HTMLResponse("Template non défini pour ce document.", status_code=500)
    # Fallback si le template référencé n'existe pas encore
    tpl_path = UI_TEMPLATES_DIR / tpl
    if not tpl_path.exists():
        html = f"""
        <div style="max-width:720px;margin:40px auto;font-family:system-ui,Segoe UI,Roboto,Arial">
          <h2>« {doc.get('label','Document')} » — bientôt disponible</h2>
          <p>Ce document n'est pas encore prêt dans l'interface. Revenez prochainement.</p>
          <p><a href="/documents">← Retour à la liste</a></p>
        </div>
        """
        return HTMLResponse(html, status_code=200)
    # IMPORTANT : le moteur Jinja pointe sur app/templates/ui
    return templates.TemplateResponse(tpl, {"request": request, "doc": doc})
    

# ========== API — Classification ==========

@app.get("/api/classif/schema")
async def api_classif_schema(idcc: Optional[int] = None, debug: Optional[bool] = False):
    def _generic_schema():
        return {
            "meta": {"label": "Générique", "mapping":{
                "categorie_to_backend": {"cadre": "cadre", "noncadre": "non-cadre"},
                "classification_format": "{text}"
            }},
            "categories": []
        }

    def _fallback_load_schema(idcc_val: Optional[int]):
        try:
            root = (APP_DIR.parent / "rules" / "ccn")
            d = None
            if root.exists():
                for sub in root.iterdir():
                    if not sub.is_dir():
                        continue
                    prefix = str(sub.name).split('-')[0]
                    try:
                        if int(prefix) == int(idcc_val):
                            d = sub; break
                    except Exception:
                        if prefix.lstrip('0') == str(idcc_val).lstrip('0'):
                            d = sub; break
            if not d:
                return _generic_schema(), {"used": "fallback", "dir": None, "file": None, "has_questions": False}
            p = d / 'classification.yml'
            if not p.exists():
                return _generic_schema(), {"used": "fallback", "dir": str(d), "file": None, "has_questions": False}
            y = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
            ok = isinstance(y, dict)
            meta = {"used": "fallback", "dir": str(d), "file": str(p), "has_questions": bool(ok and y.get('questions'))}
            if not ok:
                return _generic_schema(), meta
            return y, meta
        except Exception as e:
            logger.warning("fallback classif schema failed: %s", e)
            return _generic_schema(), {"used": "fallback", "error": str(e)}

    dbg = {"idcc": idcc}
    try:
        if load_classification_schema is None:
            raise RuntimeError('loader_unavailable')
        schema = load_classification_schema(idcc)
        if not isinstance(schema, dict):
            schema = _generic_schema()
        # Si le loader retourne un schéma trop vide pour une CCN précise,
        # tenter une lecture directe du YAML afin de récupérer `questions:`.
        if idcc and (
            (not isinstance(schema, dict)) or (
                not schema.get('questions') and not schema.get('categories')
            )
        ):
            fb, meta = _fallback_load_schema(idcc)
            dbg.update(meta)
            if isinstance(fb, dict) and (fb.get('questions') or fb.get('categories')):
                schema = fb
            else:
                dbg.setdefault('used', 'native')
                dbg['has_questions'] = bool(schema.get('questions'))
    except Exception as e:
        logger.warning("api_classif_schema loader failed (%s) — using fallback", e)
        schema, meta = _fallback_load_schema(idcc)
        dbg.update(meta)
    payload = {"schema": schema}
    if debug:
        # Infos utiles pour diagnostiquer la source et le fichier retenu
        if 'used' not in dbg:
            dbg['used'] = 'native'
            dbg['has_questions'] = bool(schema.get('questions'))
        payload['debug'] = dbg
    return JSONResponse(payload)


# ========== API — Temps de travail ==========

def _temps_bounds_payload(
    idcc: Optional[int],
    work_time_mode: str,
    weekly_hours: Optional[float],
    forfait_days_per_year: Optional[int],
    as_of: Optional[str],
    categorie: Optional[str] = None,
    statut: Optional[str] = None,
    segment: Optional[str] = None,
    contract_type: Optional[str] = None,
) -> Dict[str, Any]:
    # ⚙️ mapping UI→API systématique
    mapped_mode = _map_worktime_mode_ui_to_api(work_time_mode or "standard")
    ctx = {
        "idcc": idcc,
        "categorie": (categorie or None),
        "work_time_mode": mapped_mode,
        "weekly_hours": weekly_hours,
        "forfait_days_per_year": forfait_days_per_year,
        "as_of": as_of or _today_iso(),
        "statut": (statut or None),
        "segment": (segment or None),
    }
    # Hints CDI/CDD stricts (pas de fallback) — par défaut, on considère CDI si non précisé
    ctx["contract_type"] = (str(contract_type).strip().lower() if contract_type else "cdi")
    res = _call_resolver("temps_travail", ctx)

    bounds = dict(res.get("bounds") or {})
    rule   = _safe_rule(res.get("rule") or {})
    caps   = dict(res.get("capabilities") or {})
    explain = list(res.get("explain") or [])
    suggest = list(res.get("suggest") or [])

    # Defaults/guards minimes si YAML absent
    if (mapped_mode == "part_time") and ("weekly_hours_min" not in bounds) and ("weekly_hours_max" not in bounds):
        bounds["weekly_hours_min"] = 24.0
        bounds["weekly_hours_max"] = 34.9
        if not rule:
            rule = {"source": "code_travail", "source_ref": "Temps partiel — C. trav., L3123‑27 à L3123‑34", "bloc": "ordre_public"}

    # Si forfait_days et aucun plafond, proposer 218 par défaut
    if mapped_mode == "forfait_days" and "days_per_year_max" not in bounds:
        caps.setdefault("defaults", {})
        caps["defaults"].setdefault("forfait_days_per_year", 218)

    return {
        "bounds": bounds, "rule": rule,
        "capabilities": caps, "explain": explain, "suggest": suggest
    }

@app.get("/api/temps/bounds", response_model=WorktimeResponse)
async def api_temps_bounds(
    idcc: Optional[int] = None,
    work_time_mode: str = "standard",
    weekly_hours: Optional[float] = None,
    forfait_days_per_year: Optional[int] = None,
    as_of: Optional[str] = None,
    categorie: Optional[str] = None,
    statut: Optional[str] = None,
    segment: Optional[str] = None,
):
    payload = _temps_bounds_payload(idcc, work_time_mode, weekly_hours, forfait_days_per_year, as_of, categorie, statut, segment, contract_type=None)
    return payload

# Alias (pour compat éventuelle)
@app.get("/api/temps_travail/bounds")
async def api_temps_travail_bounds(
    idcc: Optional[int] = None,
    work_time_mode: str = "standard",
    weekly_hours: Optional[float] = None,
    forfait_days_per_year: Optional[int] = None,
    as_of: Optional[str] = None,
    categorie: Optional[str] = None,
    statut: Optional[str] = None,
    segment: Optional[str] = None,
):
    payload = _temps_bounds_payload(idcc, work_time_mode, weekly_hours, forfait_days_per_year, as_of, categorie, statut, segment, contract_type=None)
    return payload


# ========== API — Période d’essai ==========

@app.get("/api/essai/bounds", response_model=EssaiResponse)
async def api_essai_bounds(
    idcc: Optional[int] = None,
    categorie: str = "non-cadre",
    date: Optional[str] = None,
    coeff: Optional[int] = None,
    annexe: Optional[str] = None,
    statut: Optional[str] = None,
    contract_type: Optional[str] = None,
    duration_weeks: Optional[int] = None,
    contract_end: Optional[str] = None,
):
    # Calculer la durée (semaines) si contract_end fourni
    dur_weeks = duration_weeks
    try:
        if not dur_weeks and contract_end and (date or _today_iso()):
            from datetime import date as _date
            d0 = _date.fromisoformat(date or _today_iso())
            d1 = _date.fromisoformat(contract_end)
            delta_days = (d1 - d0).days
            if delta_days > 0:
                dur_weeks = int(round(delta_days / 7.0))
    except Exception:
        dur_weeks = duration_weeks

    ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "as_of": date or _today_iso(),
        "annexe": annexe,
        "statut": statut,
        # Par défaut CDI si non fourni (UI CDI ne transmet pas contract_type)
        "contract_type": (contract_type or 'cdi'),
        "contract_duration_weeks": dur_weeks,
    }
    res = _call_resolver("periode_essai", ctx)
    bounds = res.get("bounds") or {}

    # Petit fallback si rien
    if not bounds or bounds.get("max_months") is None:
        maxm = 4 if (categorie or "").lower() == "cadre" else 2
        bounds = {"max_months": maxm, "max_total_months": None}
        if not res.get("rule"):
            res["rule"] = {"source": "code_travail", "source_ref": "C. trav., L1221‑19 à L1221‑25", "bloc": "ordre_public"}

    return ({
        "bounds": bounds,
        "rule": _safe_rule(res.get("rule")),
        "capabilities": res.get("capabilities") or {},
        "explain": res.get("explain") or [],
        "suggest": res.get("suggest") or [],

    })


# ========== API — Préavis ==========

@app.get("/api/preavis/bounds", response_model=PreavisResponse)
async def api_preavis_bounds(
    idcc: Optional[int] = None,
    categorie: str = "non-cadre",
    anciennete_months: Optional[int] = None,
    coeff: Optional[int] = None,
    as_of: Optional[str] = None,
    annexe: Optional[str] = None,
    segment: Optional[str] = None,
    statut: Optional[str] = None,
    coeff_key: Optional[str] = None,
):
    ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "anciennete_months": anciennete_months,
        "coeff": coeff,
        "as_of": as_of or _today_iso(),
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
        "coeff_key": coeff_key,
        "contract_type": 'cdi',
    }
    res = _call_resolver("preavis", ctx)
    # ✅ le resolver renvoie "notice"
    notice = res.get("notice") or {}

    # Fallback léger si absolument rien
    if not notice or (notice.get("demission") is None and notice.get("licenciement") is None):
        if idcc == 1486:
            cat = (categorie or "").lower()
            months = int(anciennete_months or 0)
            if cat == "cadre":
                notice = {"demission": 3.0, "licenciement": 3.0}
            else:
                notice = {"demission": 1.0, "licenciement": 2.0 if months >= 24 else 1.0}
            if not res.get("rule"):
                res["rule"] = {"source": "ccn", "source_ref": "Syntec, art. 4.2 (repère)", "bloc": "bloc_1"}
        else:
            notice = {"demission": None, "licenciement": None}
            if not res.get("rule"):
                res["rule"] = {"source": "code_travail", "source_ref": "À défaut, renvoi CCN/contrat", "bloc": "suppletif"}

    return ({
        "notice": notice,
        "rule": _safe_rule(res.get("rule")),
        "capabilities": res.get("capabilities") or {},
        "explain": res.get("explain") or [],
        "suggest": res.get("suggest") or [],
    })


# ========== API — Rémunération ==========

@app.get("/api/salaire/bounds", response_model=SalaryResponse)
async def api_salaire_bounds(
    idcc: Optional[int] = None,
    categorie: str = "non-cadre",
    coeff: Optional[int] = None,
    coeff_key: Optional[str] = None,
    work_time_mode: Optional[str] = None,
    weekly_hours: Optional[float] = None,
    forfait_days_per_year: Optional[int] = None,
    classification_level: Optional[str] = None,
    has_13th_month: bool = False,
    as_of: Optional[str] = None,
    anciennete_months: Optional[int] = None,
    annexe: Optional[str] = None,
    segment: Optional[str] = None,
    statut: Optional[str] = None,
):
    ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "coeff_key": coeff_key,
        # ✅ mapping UI→API
        "work_time_mode": _map_worktime_mode_ui_to_api(work_time_mode or "standard"),
        "weekly_hours": weekly_hours,
        "forfait_days_per_year": forfait_days_per_year,
        "classification_level": classification_level,
        "has_13th_month": has_13th_month,
        "as_of": as_of or _today_iso(),
        "anciennete_months": anciennete_months,
        # Dimensions de classification CCN (0016, etc.)
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
        "contract_type": 'cdi',
    }
    # 1) Resolver principal
    res = _call_resolver("remuneration", ctx)
    # ✅ le resolver renvoie "minima"
    minima = _norm_minima(res.get("minima") or {})

    # 2) Filet: si rien de concret, legacy
    if minima.get("monthly_min_eur") is None and _compute_salary_min_legacy:
        try:
            try:
                m2, r2, _ = _compute_salary_min_legacy(
                    idcc=idcc,
                    categorie=categorie,
                    coeff=coeff,
                    work_time_mode=ctx["work_time_mode"],
                    weekly_hours=weekly_hours,
                    forfait_days_per_year=forfait_days_per_year,
                    classification_level=classification_level,
                    as_of=ctx["as_of"],
                    annexe=ctx.get("annexe"),
                    segment=ctx.get("segment"),
                    statut=ctx.get("statut"),
                )
            except TypeError:
                m2, r2, _ = _compute_salary_min_legacy(
                    idcc=idcc,
                    categorie=categorie,
                    coeff=coeff,
                    work_time_mode=ctx["work_time_mode"],
                    as_of=ctx["as_of"],
                    annexe=ctx.get("annexe"),
                    segment=ctx.get("segment"),
                    statut=ctx.get("statut"),
                )
            if m2:
                minima = _norm_minima(m2)
                if not res.get("rule") and r2:
                    res["rule"] = r2
        except Exception as e:
            logger.warning("fallback compute_salary_minimum failed: %s", e)

    # 3) Suggest par défaut si absente
    suggest = list(res.get("suggest") or [])
    if minima.get("monthly_min_eur") is not None and not any(s.get("field") == "salary_gross_monthly" for s in suggest):
        suggest.append({"field": "salary_gross_monthly", "value": float(minima["monthly_min_eur"])})

    # 4) Bandeau explicatif (footer) — on affiche le mensuel
    explain = list(res.get("explain") or [])
    if minima.get("monthly_min_eur") is not None:
        try:
            m = float(minima["monthly_min_eur"])
            txt = f"Plancher mensuel applicable : {m:,.2f} € bruts (hors accessoires)."
            explain.append({
                "kind": "info",
                "slot": "step6.footer",
                "text": txt,
                "ref": (res.get("rule") or {}).get("source_ref"),
                "url": (res.get("rule") or {}).get("url"),
            })
        except Exception:
            pass

    # ✅ Toujours répondre, même si aucun minimum n'est disponible
    return ({
        "minima": minima,
        "rule": _safe_rule(res.get("rule")),
        "capabilities": res.get("capabilities") or {},
        "explain": explain,
        "suggest": suggest,
    })


# ========== API — Congés ==========

@app.get("/api/conges/bounds", response_model=CongesResponse)
async def api_conges_bounds(
    idcc: Optional[int] = None,
    anciennete_months: Optional[int] = None,
    unit: str = "ouvrés",
    as_of: Optional[str] = None,
):
    ctx = {
        "idcc": idcc,
        "anciennete_months": anciennete_months,
        "unit": unit,
        "as_of": as_of or _today_iso(),
        "contract_type": 'cdi',
    }
    res = _call_resolver("conges", ctx)
    # ✅ le resolver renvoie "conges" (avec min_days / suggested_days)
    conges_payload = res.get("conges") or res.get("bounds") or {}

    return ({
        "conges": conges_payload,
        "rule": _safe_rule(res.get("rule")),
        "capabilities": res.get("capabilities") or {},
        "explain": res.get("explain") or [],
        "suggest": res.get("suggest") or [],
    })

# ========== API — CDD (règles de recours / durée / carence / précarité) ==========

@app.get("/api/cdd/rules")
async def api_cdd_rules(
    idcc: Optional[int] = None,
    reason: Optional[str] = None,
    as_of: Optional[str] = None,
):
    ctx = {
        "idcc": idcc,
        "reason": (reason or "").strip().lower(),
        "as_of": as_of or _today_iso(),
    }
    res = _call_resolver("cdd", ctx)
    return ({
        "cdd": res.get("cdd") or {},
        "rule": _safe_rule(res.get("rule")),
        "capabilities": res.get("capabilities") or {},
        "explain": res.get("explain") or [],
        "suggest": res.get("suggest") or [],
    })

# ========== API — Clauses ==========

@app.get("/api/clauses/catalog")
async def api_clauses_catalog(
    idcc: Optional[int] = None,
    categorie: Optional[str] = None,
    work_time_mode: Optional[str] = None,
    coeff: Optional[int] = None,
    annexe: Optional[str] = None,
    segment: Optional[str] = None,
    statut: Optional[str] = None,
    doc: Optional[str] = None,
):
    ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "work_time_mode": work_time_mode,
        "coeff": coeff,
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
    }
    # Doc type (cdi/cdd) pour charger le YAML idoine
    if doc:
        ctx["doc"] = str(doc).strip().lower()
    cat = load_clauses_catalog(idcc, ctx)
    return JSONResponse(cat)


# ========== API — Resolve (debug/diag) ==========

@app.get("/api/resolve")
async def api_resolve(
    theme: str,
    idcc: Optional[int] = None,
    categorie: Optional[str] = "non-cadre",
    coeff: Optional[int] = None,
    work_time_mode: Optional[str] = None,
    weekly_hours: Optional[float] = None,
    forfait_days_per_year: Optional[int] = None,
    classification_level: Optional[str] = None,
    anciennete_months: Optional[int] = None,
    unit: str = "ouvrés",
    as_of: Optional[str] = None,
):
    if resolve_theme is None:
        return JSONResponse({"error": "resolver_unavailable"})
    ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "as_of": as_of or date.today().isoformat(),
        # ✅ mapping UI→API ici aussi
        "work_time_mode": _map_worktime_mode_ui_to_api(work_time_mode or "standard"),
        "weekly_hours": weekly_hours,
        "forfait_days_per_year": forfait_days_per_year,
        "classification_level": classification_level,
        "anciennete_months": anciennete_months,
        "unit": unit,
    }
    try:
        res = resolve_theme(theme, ctx)
    except Exception as e:
        logger.exception("resolve failed: %s", e)
        return JSONResponse({"error": "resolver_failed", "detail": str(e)}, status_code=500)
    return JSONResponse(res)


# ========== Génération CDI ==========

@app.post("/cdi/generate")
async def cdi_generate(
    # --- Employeur
    employer_name: str = Form(...),
    employer_address: str = Form(...),
    urssaf_number: str = Form(...),
    rep_name: str = Form(...),
    rep_title: str = Form(...),
    rep_civility: Optional[str] = Form(None),
    # Signataire personne morale (optionnel)
    rep_signatory_kind: Optional[str] = Form(None),
    rep_entity_name: Optional[str] = Form(None),
    rep_entity_legal_form: Optional[str] = Form(None),
    rep_entity_siren: Optional[str] = Form(None),
    rep_entity_rep_civility: Optional[str] = Form(None),
    rep_entity_rep_last_name: Optional[str] = Form(None),
    rep_entity_rep_first_name: Optional[str] = Form(None),
    rep_entity_rep_title: Optional[str] = Form(None),

    # --- Salarié
    employee_civility: str = Form(...),
    employee_name: str = Form(...),
    birth_date: str = Form(...),
    birth_place: str = Form(...),
    nationality: str = Form(...),
    employee_address: Optional[str] = Form(None),
    employee_postal_code: Optional[str] = Form(None),
    employee_city: Optional[str] = Form(None),
    ssn: Optional[str] = Form(None),   # ← facultatif

    # --- Contexte conventionnel
    idcc: Optional[int] = Form(None),
    categorie: str = Form(...),
    classification_level: Optional[str] = Form(None),
    # Dimensions de classification CCN (ex. 0016 Transports routiers)
    annexe: Optional[str] = Form(None),
    segment: Optional[str] = Form(None),
    statut: Optional[str] = Form(None),
    coeff_key: Optional[str] = Form(None),
    adhesion_syndicat: Optional[str] = Form(None),
    # --- Accords d'entreprise (optionnel)
    ae_exists: Optional[str] = Form(None),
    ae_count: Optional[int] = Form(None),
    ae_json: Optional[str] = Form(None),

    # --- Emploi
    job_title: str = Form(...),
    main_mission: Optional[str] = Form(None),
    annex_activities: Optional[str] = Form(None),
    mission_in_contract: Optional[str] = Form(None),
    mission_in_annex: Optional[str] = Form(None),

    # --- Temps de travail
    work_time_regime: str = Form(...),
    work_time_mode: Optional[str] = Form(None),   
    part_time_payload: Optional[str] = Form(None),
    # TRV — organisation temps complet
    trv_fulltime_mode: Optional[str] = Form(None),
    trv_rtt_days_per_year: Optional[int] = Form(None),
    trv_ref_desc: Optional[str] = Form(None),
    # TRM — roulants (temps de service de référence)
    trm_service_kind: Optional[str] = Form(None),
    # Modulation (cadre annuel)
    mod_annual_hours_max: Optional[int] = Form(None),
    mod_weekly_hours_cap: Optional[float] = Form(None),
    mod_ref_desc: Optional[str] = Form(None),

    weekly_hours: Optional[float] = Form(None),
    schedule_info: Optional[str] = Form(None),
    forfait_hours_per_year: Optional[int] = Form(None),
    forfait_hours_ref: Optional[str] = Form(None),
    forfait_days_per_year: Optional[int] = Form(None),
    forfait_days_ref: Optional[str] = Form(None),
    m2_days_cap: Optional[int] = Form(None),
    ref_period_desc: Optional[str] = Form(None),

    # --- Dates & essai
    contract_start: str = Form(...),
    probation_months: Optional[float] = Form(None),
    probation_renewal_requested: str = Form("non"),

    # --- Rémunération
    salary_gross_monthly: float = Form(...),
    has_13th_month: Optional[str] = Form(None),   # checkbox string
    remuneration_accessories: Optional[str] = Form(None),
    expense_policy: Optional[str] = Form(None),
    bonus13_when: Optional[str] = Form(None),
    bonus13_when_free: Optional[str] = Form(None),
    bonus13_base: Optional[str] = Form(None),
    bonus13_base_free: Optional[str] = Form(None),

    # --- Lieu / mobilité
    workplace_base: str = Form(...),
    work_area: Optional[str] = Form(None),
    mobility_clause: str = Form("non"),
    # Rappels employeur (compléments)
    employer_postal_code: Optional[str] = Form(None),
    employer_city: Optional[str] = Form(None),
    legal_form: Optional[str] = Form(None),
    siren_number: Optional[str] = Form(None),

    # --- Congés / organismes
    cp_days_number: Optional[int] = Form(None),
    cp_unit: str = Form("ouvrables"),
    retirement_org: Optional[str] = Form(None),
    retirement_org_address: Optional[str] = Form(None),
    health_org: Optional[str] = Form(None),
    health_org_address: Optional[str] = Form(None),
    welfare_org: Optional[str] = Form(None),
    welfare_org_address: Optional[str] = Form(None),
    # --- Santé & sécurité
    poste_risques_particuliers: Optional[str] = Form(None),

    # --- Préavis saisis
    notice_dismissal_months: Optional[float] = Form(None),
    notice_resignation_months: Optional[float] = Form(None),

    # --- Entretien professionnel (périodicité)
    entretien_periodicity: Optional[str] = Form(None),

    # --- Clauses (Step 9)
    clauses_selected_json: Optional[str] = Form(None),
    clauses_custom_json: Optional[str] = Form(None),
    clauses_params_json:   Optional[str] = Form(None),
    
    # --- DPAE / signatures
    dpae_urssaf_city: Optional[str] = Form(None),
    dpae_date: Optional[str] = Form(None),
    place_of_signature: str = Form(...),
    date_of_signature: str = Form(...),
    copies_count: int = Form(...),

    # --- Données fail-soft/hard venant du front
    non_compliance_json: Optional[str] = Form(None),
    overrides_steps: Optional[str] = Form(None),

    # --- (Optionnel) ancienneté totale en mois (envoyée par le front)
    anciennete_months: Optional[int] = Form(None),
    preview: Optional[str] = Form(None),
):
    # 0) fail-soft/hard côté front
    try:
        conformity_issues = json.loads(non_compliance_json) if non_compliance_json else []
        if not isinstance(conformity_issues, list):
            conformity_issues = []
    except Exception:
        conformity_issues = []
    try:
        override_steps_set = set(json.loads(overrides_steps)) if overrides_steps else set()
    except Exception:
        override_steps_set = set()

    # 1) coefficient éventuel dans classification_level
    coeff: Optional[int] = None
    if classification_level:
        m = re.search(r"(\d{2,3})", classification_level)
        if m:
            try:
                coeff = int(m.group(1))
            except Exception:
                coeff = None

    # 1-bis) Accords d'entreprise (parse JSON caché)
    ae_exists_flag = False
    ae_count_val: Optional[int] = None
    ae_items: list[dict[str, Any]] = []

    # la checkbox brute peut valoir "on", "true", "oui", "1"
    if ae_exists and str(ae_exists).strip().lower() in {"on", "true", "oui", "1"}:
        ae_exists_flag = True

    try:
        if ae_json:
            data = json.loads(ae_json)
            if isinstance(data, dict):
                ae_exists_flag = bool(data.get("exists", ae_exists_flag))
                ae_count_val = int(data.get("count") or 0) or ae_count
                items = data.get("items") or []
                if isinstance(items, list):
                    for it in items[:5]:
                        title = (it.get("title") or "").strip()
                        dt    = (it.get("date") or "").strip()
                        if title or dt:
                            ae_items.append({"title": title, "date": dt})
    except Exception:
        # si JSON invalide, on retombe sur la case + select bruts
        ae_count_val = ae_count


    # ---------- Server‑side rechecks via resolve() ----------

    # Essai
    # Calcul durée estimée (semaines) pour CDD
    _dur_weeks = None
    try:
        if contract_end:
            _d0 = date.fromisoformat(contract_start)
            _d1 = contract_end if isinstance(contract_end, date) else date.fromisoformat(str(contract_end))
            _dd = (_d1 - _d0).days
            if _dd > 0:
                _dur_weeks = int(round(_dd/7.0))
        elif cdd_min_duration_value is not None:
            _v = int(cdd_min_duration_value)
            _unit = (cdd_min_duration_unit or 'jours').strip().lower()
            _days = _v * (30 if _unit == 'mois' else 1)
            _dur_weeks = int(round(_days/7.0))
    except Exception:
        _dur_weeks = None

    ess_ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "as_of": contract_start,
        "annexe": annexe,
        "statut": statut,
        "contract_type": "cdi",
        "contract_duration_weeks": _dur_weeks,
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }
    ess_res = _call_resolver("periode_essai", ess_ctx)
    ess_bounds = ess_res.get("bounds") or {}
    max_essai = ess_bounds.get("max_months")
    if max_essai is None:
        max_essai = 4 if (categorie or "").lower() == "cadre" else 2  # ceinture & bretelles
    if probation_months is not None and float(probation_months) > float(max_essai):
        conformity_issues.append({
            "key": "essai_srv",
            "step": 9,
            "field": "probation_months",
            "severity": "hard",
            "message": f"Période d’essai saisie ({probation_months} mois) > plafond ({max_essai}).",
            "ref": (ess_res.get("rule") or {}).get("source_ref"),
            "url": (ess_res.get("rule") or {}).get("url"),
            "suggested": max_essai,
        })

    # Préavis
    prv_ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "anciennete_months": anciennete_months,
        "as_of": contract_start,
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
        "coeff_key": coeff_key,
        "contract_type": "cdi",
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }
    prv_res = _call_resolver("preavis", prv_ctx)
    # ✅ lire "notice"
    prv_bounds = prv_res.get("notice") or {}
    dem_min = prv_bounds.get("demission")
    lic_min = prv_bounds.get("licenciement")

    if dem_min is None and lic_min is None and idcc == 1486:
        # petit filet Syntec si YAML code manquant
        cat = (categorie or "").lower()
        months = int(anciennete_months or 0)
        if cat == "cadre":
            dem_min = lic_min = 3.0
        else:
            dem_min = 1.0
            lic_min = 2.0 if months >= 24 else 1.0

    if notice_resignation_months is not None and dem_min is not None and float(notice_resignation_months) < float(dem_min):
        conformity_issues.append({
            "key": "preavis_dem_srv",
            "step": 10,
            "field": "notice_resignation_months",
            "severity": "hard",
            "message": f"Préavis démission saisi ({notice_resignation_months} mois) < minimum ({dem_min}).",
            "ref": (prv_res.get("rule") or {}).get("source_ref"),
            "url": (prv_res.get("rule") or {}).get("url"),
            "suggested": dem_min,
        })
    if notice_dismissal_months is not None and lic_min is not None and float(notice_dismissal_months) < float(lic_min):
        conformity_issues.append({
            "key": "preavis_lic_srv",
            "step": 10,
            "field": "notice_dismissal_months",
            "severity": "hard",
            "message": f"Préavis licenciement saisi ({notice_dismissal_months} mois) < minimum ({lic_min}).",
            "ref": (prv_res.get("rule") or {}).get("source_ref"),
            "url": (prv_res.get("rule") or {}).get("url"),
            "suggested": lic_min,
        })

    # Rémunération minimale
    has_13th_flag = False
    try:
        if has_13th_month and str(has_13th_month).strip().lower() in {"on","true","oui","1"}:
            has_13th_flag = True
    except Exception:
        has_13th_flag = False

    ui_work_time_mode = (work_time_mode or "standard_35h")  
    wt_api = _map_worktime_mode_ui_to_api(ui_work_time_mode)
    if (work_time_regime or "").lower() == "temps_partiel" and wt_api == "standard":
        wt_api = "part_time"

    # Rémunération: pour TRV/SAN/DEM temps complet en standard, les minimas restent sur 35h (151,67 h/mois)
    _sal_weekly = weekly_hours
    try:
        seg_up = str(segment or '').strip().upper()
        if idcc == 16 and seg_up in {'TRV','SANITAIRE','DEMENAGEMENT'} and (work_time_regime or '').lower() == 'temps_complet' and wt_api == 'standard':
            _sal_weekly = 35.0
    except Exception:
        _sal_weekly = weekly_hours

    sal_ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "work_time_mode": wt_api,
        "weekly_hours": _sal_weekly,
        "forfait_days_per_year": forfait_days_per_year,
        "classification_level": classification_level,
        "coeff_key": coeff_key,
        "has_13th_month": has_13th_flag,
        "as_of": contract_start,
        "anciennete_months": anciennete_months,
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
        "contract_type": "cdi",
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }

    sal_res = _call_resolver("remuneration", sal_ctx)
    # ✅ lire "minima"
    sal_bounds = _norm_minima(sal_res.get("minima") or {})
    floor = sal_bounds.get("monthly_min_eur")
    if floor is not None and salary_gross_monthly is not None:
        try:
            if float(salary_gross_monthly) < float(floor):
                conformity_issues.append({
                    "key": "salaire_min_srv",
                    "step": 6,
                    "field": "salary_gross_monthly",
                    "severity": "hard",
                    "message": f"Salaire saisi ({float(salary_gross_monthly):.2f} €) < minimum applicable ({float(floor):.2f} €).",
                    "ref": (sal_res.get("rule") or {}).get("source_ref"),
                    "url": (sal_res.get("rule") or {}).get("url"),
                    "suggested": float(floor),
                })
        except Exception:
            pass

    # Temps de travail — hebdo / forfait-jours
    tt_ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "work_time_mode": wt_api,
        "weekly_hours": weekly_hours,
        "forfait_days_per_year": forfait_days_per_year,
        "as_of": contract_start,
        "segment": segment,
        "statut": statut,
        "contract_type": "cdi",
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }

    # ---------- Temps partiel (payload UI) ----------
    part_time_data = {}
    try:
        if part_time_payload:
            js = json.loads(part_time_payload)
            if isinstance(js, dict):
                part_time_data = js
    except Exception:
        part_time_data = {}

    # (On ne rend présent dans le contexte que si le régime est partiel)
    is_part_time = (work_time_regime or "").lower() == "temps_partiel"

    tt_res = _call_resolver("temps_travail", tt_ctx)
    tt_bounds = tt_res.get("bounds") or {}
    if wt_api in {"standard", "part_time"} and weekly_hours is not None:
        wmin = tt_bounds.get("weekly_hours_min")
        wmax = tt_bounds.get("weekly_hours_max")
        if wmin is not None and float(weekly_hours) < float(wmin):
            conformity_issues.append({
                "key": "tt_min_srv", "step": 7, "field": "weekly_hours", "severity": "hard",
                "message": f"Heures/semaine saisies ({weekly_hours}) < minimum ({wmin}).",
                "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": wmin,
            })
        if wmax is not None and float(weekly_hours) > float(wmax):
            conformity_issues.append({
                "key": "tt_max_srv", "step": 7, "field": "weekly_hours", "severity": "hard",
                "message": f"Heures/semaine saisies ({weekly_hours}) > plafond ({wmax}).",
                "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": wmax,
            })
    if wt_api == "forfait_days" and forfait_days_per_year is not None:
        dmax = tt_bounds.get("days_per_year_max")
        if dmax is not None and int(forfait_days_per_year) > int(dmax):
            conformity_issues.append({
                "key": "fj_max_srv", "step": 7, "field": "forfait_days_per_year", "severity": "hard",
                "message": f"Forfait-jours saisi ({forfait_days_per_year}) > plafond ({dmax}).",
                "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": dmax,
            })
    # Modalité 2 — plafond annuel en jours (facultatif) : contrôler contre la borne CCN si disponible
    if wt_api == "forfait_hours_mod2" and m2_days_cap is not None:
        dmax = tt_bounds.get("days_per_year_max")
        try:
            if dmax is not None and int(m2_days_cap) > int(dmax):
                conformity_issues.append({
                    "key": "m2_jours_max_srv", "step": 7, "field": "m2_days_cap", "severity": "hard",
                    "message": f"Plafond annuel saisi ({m2_days_cap}) > plafond ({dmax}).",
                    "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": dmax,
                })
        except Exception:
            pass

    # Congés payés — minimum
    cp_ctx = {
        "idcc": idcc,
        "anciennete_months": anciennete_months,
        "unit": cp_unit,
        "as_of": contract_start,
        "contract_type": "cdi",
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }
    cp_res = _call_resolver("conges", cp_ctx)
    # ✅ lire "conges" (et pas "bounds")
    cp_bounds = cp_res.get("conges") or cp_res.get("bounds") or {}
    cp_min = cp_bounds.get("min_days")
    cp_sugg = cp_bounds.get("suggested_days")
    if cp_days_number is not None and cp_min is not None and int(cp_days_number) < int(cp_min):
        conformity_issues.append({
            "key": "cp_min_srv", "step": 10, "field": "cp_days_number", "severity": "hard",
            "message": f"CP saisis ({cp_days_number} {cp_unit}) < minimum ({cp_min}).",
            "ref": (cp_res.get("rule") or {}).get("source_ref"), "suggested": cp_min,
        })
    
    # ---------- Clauses (Step 9) ----------
    selected_keys: list[str] = []
    custom_clauses: list[dict[str, Any]] = []
    clauses_params: dict[str, Any] = {}  # mapping { "<key>": { "<param>": value, "<param>__label": "..." } }

    # Sélection (cases cochées)
    try:
        if clauses_selected_json:
            data = json.loads(clauses_selected_json)
            if isinstance(data, list):
                seen = set()
                for k in data:
                    if isinstance(k, str):
                        kk = k.strip()
                        if kk and kk not in seen:
                            selected_keys.append(kk)
                            seen.add(kk)
    except Exception:
        selected_keys = []

    # Auto‑inclusions (branche) basées sur YAML — CDI
    try:
        from app.services.clauses_library import get_auto_include_keys as _auto_inc
        for kk in _auto_inc(idcc, 'cdi'):
            if kk not in selected_keys:
                selected_keys.append(kk)
    except Exception:
        pass

    # Clauses custom
    try:
        if clauses_custom_json:
            data = json.loads(clauses_custom_json)
            if isinstance(data, list):
                for it in data:
                    title = (it.get("title") or "").strip()
                    text  = (it.get("text")  or "").strip()
                    if title or text:
                        custom_clauses.append({"title": title, "text": text})
    except Exception:
        custom_clauses = []

    # Paramètres saisis pour les clauses
    try:
        if clauses_params_json:
            data = json.loads(clauses_params_json)
            if isinstance(data, dict):
                clauses_params = data
    except Exception:
        clauses_params = {}


    # ---------- Clauses automatiques si temps partiel ----------
    auto_clauses = []
    if is_part_time:
        emp_name = employee_name
        comp = employer_name

        # 1) Égalité de traitement
        auto_clauses.append({
            "title": "Égalité de traitement",
            "body": (
                f"{emp_name} bénéficiera de tous les droits et avantages reconnus aux salariés à temps plein "
                f"travaillant dans la société, résultant du Code du travail, des accords collectifs applicables "
                f"ou des usages, au prorata de son temps de travail. {comp} garantit un traitement équivalent "
                f"aux autres salariés de même qualification et ancienneté en matière de promotion, déroulement "
                f"de carrière et accès à la formation. À sa demande, {emp_name} pourra être reçu·e par la direction "
                f"pour examiner toute difficulté d’application de cette égalité."
            )
        })

        # 2) Cumul d’emplois
        auto_clauses.append({
            "title": "Cumul d’emplois",
            "body": (
                f"{emp_name} peut exercer une autre activité professionnelle, sous réserve d’en informer préalablement "
                f"{comp}. Cette activité ne devra pas porter atteinte aux intérêts légitimes de l’entreprise, "
                f"ni contrevenir aux obligations de loyauté et de confidentialité."
            )
        })

        # 3) Priorité d’affectation
        pr_days = None
        try:
            pr_days = int((part_time_data.get("priority") or {}).get("reply_days") or 0) or None
        except Exception:
            pr_days = None
        delay_txt = f"dans un délai maximal de {pr_days} jours" if pr_days else "dans un délai raisonnable"

        auto_clauses.append({
            "title": "Priorité d’affectation",
            "body": (
                f"{emp_name} bénéficie d’une priorité d’affectation aux emplois à temps complet ou à temps partiel "
                f"ressortissant de sa catégorie professionnelle ou équivalents qui seraient créés ou deviendraient vacants. "
                f"La liste de ces emplois est communiquée avant toute attribution. En cas de candidature, la demande "
                f"est examinée et une réponse motivée est donnée {delay_txt}."
            )
        })

    # Résolution des textes “catalogue” → HTML prêt PDF   
    selected_clause_texts = get_clause_texts(idcc, selected_keys, clauses_params, doc_type='cdi')


    # 4) Contexte PDF
    # Mise en forme des noms pour un rendu PDF propre
    rep_name_fmt = _smart_name_case(rep_name)
    employee_name_fmt = _smart_name_case(employee_name)

    context = {
        # Employeur
        "employer_name": employer_name,
        "employer_address": employer_address,
        "urssaf_number": urssaf_number,
        "rep_name": rep_name_fmt or rep_name,
        "rep_title": rep_title,
        "rep_civility": rep_civility,
        # Signataire personne morale (chaînage)
        "rep_signatory_kind": rep_signatory_kind,
        "rep_entity_name": rep_entity_name,
        "rep_entity_legal_form": rep_entity_legal_form,
        "rep_entity_siren": rep_entity_siren,
        "rep_entity_rep_civility": rep_entity_rep_civility,
        "rep_entity_rep_title": rep_entity_rep_title,
        # Salarié
        "employee_civility": employee_civility,
        "employee_name": employee_name_fmt or employee_name,
        "employee_address": employee_address,
        "employee_postal_code": employee_postal_code,
        "employee_city": employee_city,
        "birth_date": birth_date,
        "birth_place": birth_place,
        "nationality": nationality,
        "ssn": ssn,
        # Contexte
        "idcc": idcc,
        "categorie": categorie,
        "classification_level": classification_level,
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
        "coeff_key": coeff_key,
        "adhesion_syndicat": adhesion_syndicat,
        "ae_exists": ae_exists_flag,
        "ae_count": ae_count_val,
        "ae_items": ae_items,
        # Emploi
        "job_title": job_title,
        "main_mission": main_mission,
        "annex_activities": annex_activities,
        "mission_in_contract": mission_in_contract,
        "mission_in_annex": mission_in_annex,
        # Temps de travail
        "work_time_mode": ui_work_time_mode, 
        "work_time_regime": work_time_regime,     # "temps_complet" | "temps_partiel"
        "part_time": part_time_data if is_part_time else None,
        "weekly_hours": weekly_hours,
        "schedule_info": schedule_info,
        "forfait_hours_per_year": forfait_hours_per_year,
        "forfait_hours_ref": forfait_hours_ref,
        "forfait_days_per_year": forfait_days_per_year,
        "forfait_days_ref": forfait_days_ref,
        "m2_days_cap": m2_days_cap,
        "ref_period_desc": ref_period_desc,
        # TRV (organisation temps complet)
        "trv_fulltime_mode": trv_fulltime_mode,
        "trv_rtt_days_per_year": trv_rtt_days_per_year,
        "trv_ref_desc": trv_ref_desc,
        # TRM (roulants) — service de référence
        "trm_service_kind": trm_service_kind,
        # Modulation (cadre annuel)
        "mod_annual_hours_max": mod_annual_hours_max,
        "mod_weekly_hours_cap": mod_weekly_hours_cap,
        "mod_ref_desc": mod_ref_desc,
        # Essai
        "contract_start": contract_start,
        "probation_months": probation_months,
        "probation_renewal_requested": probation_renewal_requested,
        # Rémunération
        "salary_gross_monthly": salary_gross_monthly,
        "has_13th_month": has_13th_flag,
        "remuneration_accessories": remuneration_accessories,
        "expense_policy": expense_policy,
        "bonus13_when": bonus13_when,
        "bonus13_when_free": bonus13_when_free,
        "bonus13_base": bonus13_base,
        "bonus13_base_free": bonus13_base_free,
        # Rémunération (bornes appliquées pour l'annexe)
        "salary_min_base": sal_bounds.get("base_min_eur"),
        "salary_min_applied": sal_bounds.get("monthly_min_eur"),
        "salary_min_labels": sal_bounds.get("applied", []),
        # Lieu / mobilité
        "workplace_base": workplace_base,
        "work_area": work_area,
        "mobility_clause": mobility_clause,
        # Employeur — compléments
        "employer_postal_code": employer_postal_code,
        "employer_city": employer_city,
        "legal_form": legal_form,
        "siren_number": siren_number,
        # Congés / organismes
        "cp_days_number": cp_days_number,
        "cp_unit": cp_unit,
        "retirement_org": retirement_org,
        "retirement_org_address": retirement_org_address,
        "health_org": health_org,
        "health_org_address": health_org_address,
        "welfare_org": welfare_org,
        "welfare_org_address": welfare_org_address,
        # Santé & sécurité
        "poste_risques_particuliers": poste_risques_particuliers,
        # Entretien professionnel
        "entretien_periodicity": entretien_periodicity,
        # Préavis (saisis)
        "notice_dismissal_months": notice_dismissal_months,
        "notice_resignation_months": notice_resignation_months,
        # Clauses (Step 9)
        "clauses_selected": selected_clause_texts,   # [{key,title,text_html,source_ref,url,flags}]
        "clauses_custom": custom_clauses,           # [{title,text}]
        "auto_clauses": auto_clauses,
        # DPAE / signatures
        "dpae_urssaf_city": dpae_urssaf_city,
        "dpae_date": dpae_date,
        "place_of_signature": place_of_signature,
        "date_of_signature": date_of_signature,
        "copies_count": copies_count,
        # Meta & conformité
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "conformity_issues": conformity_issues,
        "overrides_steps": list(override_steps_set),
        # Rappels bornes/valeurs pour annexe
        "probation_max": max_essai,
        "probation_max_total": ess_bounds.get("max_total_months"),
        "notice_min_resignation": dem_min,
        "notice_min_dismissal": lic_min,
        "worktime_bounds": tt_bounds,
        "leave_min_days": cp_min,
        "leave_suggested_days": cp_sugg,
    }

        # --- Mode aperçu PDF : rendu en mémoire, pas d’écriture disque ---
    is_preview = False
    try:
        if preview and str(preview).strip().lower() in {"1","true","on","yes","oui"}:
            is_preview = True
    except Exception:
        is_preview = False

    if is_preview:
        try:
            pdf_bytes = render_pdf_bytes("pdf/cdi.html.j2", context)
            headers = {"Content-Disposition": 'inline; filename="cdi_preview.pdf"'}
            return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)
        except Exception as e:
            logger.exception("preview render failed: %s", e)
            return JSONResponse({"error": "preview_failed", "detail": str(e)}, status_code=500)


    # 5) PDF (toujours)
    pdf_path = await run_in_threadpool(render_pdf, "pdf/cdi.html.j2", context)

    # 6) Snapshot (best effort)
    try:
        snapshot = {
            "document": "CDI",
            "context": {k: v for k, v in context.items()
                        if k not in ("remuneration_accessories", "expense_policy")},
            "ae": {
                "exists": ae_exists_flag,
                "count": ae_count_val,
                "items": ae_items,
            },

            "clauses": {
                "selected_keys": selected_keys,
                "custom_count": len(custom_clauses),
            },

            "rules_applied": [
                {
                    "theme": "periode_essai",
                    "source": (ess_res.get("rule") or {}).get("source"),
                    "source_ref": (ess_res.get("rule") or {}).get("source_ref"),
                    "bloc": (ess_res.get("rule") or {}).get("bloc"),
                },
                {
                    "theme": "preavis",
                    "source": (prv_res.get("rule") or {}).get("source"),
                    "source_ref": (prv_res.get("rule") or {}).get("source_ref"),
                    "bloc": (prv_res.get("rule") or {}).get("bloc"),
                },
                {
                    "theme": "salaire",
                    "source": (sal_res.get("rule") or {}).get("source"),
                    "source_ref": (sal_res.get("rule") or {}).get("source_ref"),
                    "bloc": (sal_res.get("rule") or {}).get("bloc"),
                },
                {
                    "theme": "temps_travail",
                    "source": (tt_res.get("rule") or {}).get("source"),
                    "source_ref": (tt_res.get("rule") or {}).get("source_ref"),
                    "bloc": (tt_res.get("rule") or {}).get("bloc"),
                },
                {
                    "theme": "conges_payes",
                    "source": (cp_res.get("rule") or {}).get("source"),
                    "source_ref": (cp_res.get("rule") or {}).get("source_ref"),
                    "bloc": (cp_res.get("rule") or {}).get("bloc"),
                },

            ],
            "generated_at": context["generated_at"],
        }
        snap_path = pdf_path.replace(".pdf", "_snapshot.json")
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("snapshot write failed: %s", e)

    return FileResponse(pdf_path, media_type="application/pdf", filename="cdi.pdf")


# ========== Génération CDD ==========

@app.post("/cdd/generate")
async def cdd_generate(
    # --- Employeur
    employer_name: str = Form(...),
    employer_address: str = Form(...),
    urssaf_number: str = Form(...),
    rep_name: str = Form(...),
    rep_title: str = Form(...),
    rep_civility: Optional[str] = Form(None),
    # Signataire personne morale (optionnel)
    rep_signatory_kind: Optional[str] = Form(None),
    rep_entity_name: Optional[str] = Form(None),
    rep_entity_legal_form: Optional[str] = Form(None),
    rep_entity_siren: Optional[str] = Form(None),
    rep_entity_rep_civility: Optional[str] = Form(None),
    rep_entity_rep_last_name: Optional[str] = Form(None),
    rep_entity_rep_first_name: Optional[str] = Form(None),
    rep_entity_rep_title: Optional[str] = Form(None),

    # --- Salarié
    employee_civility: str = Form(...),
    employee_name: str = Form(...),
    birth_date: str = Form(...),
    birth_place: str = Form(...),
    nationality: str = Form(...),
    employee_address: Optional[str] = Form(None),
    employee_postal_code: Optional[str] = Form(None),
    employee_city: Optional[str] = Form(None),
    ssn: Optional[str] = Form(None),

    # --- Contexte conventionnel
    idcc: Optional[int] = Form(None),
    categorie: str = Form(...),
    classification_level: Optional[str] = Form(None),
    # Dimensions de classification CCN
    annexe: Optional[str] = Form(None),
    segment: Optional[str] = Form(None),
    statut: Optional[str] = Form(None),
    coeff_key: Optional[str] = Form(None),
    adhesion_syndicat: Optional[str] = Form(None),
    # Accords d'entreprise (optionnel)
    ae_exists: Optional[str] = Form(None),
    ae_count: Optional[int] = Form(None),
    ae_json: Optional[str] = Form(None),

    # --- Étape CDD : motif & durée
    # Noms "natifs" du formulaire CDD
    cdd_reason: Optional[str] = Form(None),
    cdd_reason_other_text: Optional[str] = Form(None),
    cdd_replace_last_name: Optional[str] = Form(None),
    cdd_replace_first_name: Optional[str] = Form(None),
    cdd_replace_job: Optional[str] = Form(None),
    cdd_replace_reason: Optional[str] = Form(None),
    cdd_term_kind: Optional[str] = Form(None),  # "fixed" | "imprecise"
    contract_end: Optional[date] = Form(None),  # si terme fixe
    cdd_min_duration_value: Optional[int] = Form(None),  # si terme imprécis
    cdd_min_duration_unit: Optional[str] = Form(None),   # "jours" | "mois"
    cdd_term_event: Optional[str] = Form(None),          # événement déclencheur (sans terme précis)
    # Contrôle licenciement économique (< 6 mois) — accroissement
    cdd_eco_layoff_6m: Optional[str] = Form(None),
    cdd_eco_layoff_notes: Optional[str] = Form(None),
    cdd_renewable: Optional[str] = Form(None),
    cdd_renewals_max: Optional[int] = Form(0),
    # Alias éventuels (interop)
    cdd_type: Optional[str] = Form(None),
    replaced_employee_name: Optional[str] = Form(None),
    replaced_employee_position: Optional[str] = Form(None),
    replacement_reason: Optional[str] = Form(None),
    no_term: Optional[str] = Form(None),
    minimum_duration: Optional[int] = Form(None),
    renewal_count: Optional[int] = Form(None),

    # --- Emploi
    job_title: str = Form(...),
    main_mission: Optional[str] = Form(None),
    annex_activities: Optional[str] = Form(None),
    mission_in_contract: Optional[str] = Form(None),
    mission_in_annex: Optional[str] = Form(None),

    # --- Temps de travail
    work_time_regime: str = Form(...),
    work_time_mode: Optional[str] = Form(None),
    part_time_payload: Optional[str] = Form(None),
    trv_fulltime_mode: Optional[str] = Form(None),
    trv_rtt_days_per_year: Optional[int] = Form(None),
    trv_ref_desc: Optional[str] = Form(None),
    trm_service_kind: Optional[str] = Form(None),
    mod_annual_hours_max: Optional[int] = Form(None),
    mod_weekly_hours_cap: Optional[float] = Form(None),
    mod_ref_desc: Optional[str] = Form(None),
    weekly_hours: Optional[float] = Form(None),
    schedule_info: Optional[str] = Form(None),
    forfait_hours_per_year: Optional[int] = Form(None),
    forfait_hours_ref: Optional[str] = Form(None),
    forfait_days_per_year: Optional[int] = Form(None),
    forfait_days_ref: Optional[str] = Form(None),
    m2_days_cap: Optional[int] = Form(None),
    ref_period_desc: Optional[str] = Form(None),

    # --- Dates & essai
    contract_start: str = Form(...),
    probation_months: Optional[float] = Form(None),
    probation_renewal_requested: str = Form("non"),

    # --- Rémunération
    salary_gross_monthly: float = Form(...),
    has_13th_month: Optional[str] = Form(None),
    remuneration_accessories: Optional[str] = Form(None),
    expense_policy: Optional[str] = Form(None),
    bonus13_when: Optional[str] = Form(None),
    bonus13_when_free: Optional[str] = Form(None),
    bonus13_base: Optional[str] = Form(None),
    bonus13_base_free: Optional[str] = Form(None),

    # --- Prime de précarité (CDD)
    precarity_rate_percent: Optional[float] = Form(None),
    precarity_rate_source: Optional[str] = Form(None),
    precarity_notes: Optional[str] = Form(None),

    # --- Lieu / mobilité
    workplace_base: str = Form(...),
    work_area: Optional[str] = Form(None),
    mobility_clause: str = Form("non"),
    employer_postal_code: Optional[str] = Form(None),
    employer_city: Optional[str] = Form(None),
    legal_form: Optional[str] = Form(None),
    siren_number: Optional[str] = Form(None),

    # --- Congés / organismes
    cp_days_number: Optional[int] = Form(None),
    cp_unit: str = Form("ouvrables"),
    retirement_org: Optional[str] = Form(None),
    retirement_org_address: Optional[str] = Form(None),
    health_org: Optional[str] = Form(None),
    health_org_address: Optional[str] = Form(None),
    welfare_org: Optional[str] = Form(None),
    welfare_org_address: Optional[str] = Form(None),

    # --- Entretien pro
    entretien_periodicity: Optional[str] = Form(None),

    # --- Clauses (Step 10)
    clauses_selected_json: Optional[str] = Form(None),
    clauses_custom_json: Optional[str] = Form(None),
    clauses_params_json:   Optional[str] = Form(None),

    # --- DPAE / signatures
    dpae_urssaf_city: Optional[str] = Form(None),
    dpae_date: Optional[str] = Form(None),
    place_of_signature: str = Form(...),
    date_of_signature: str = Form(...),
    copies_count: int = Form(...),

    # --- Données front (issues/overrides) + diverses
    non_compliance_json: Optional[str] = Form(None),
    overrides_steps: Optional[str] = Form(None),
    anciennete_months: Optional[int] = Form(None),
    preview: Optional[str] = Form(None),
):
    # 0) Issues / overrides
    try:
        conformity_issues = json.loads(non_compliance_json) if non_compliance_json else []
        if not isinstance(conformity_issues, list):
            conformity_issues = []
    except Exception:
        conformity_issues = []
    try:
        override_steps_set = set(json.loads(overrides_steps)) if overrides_steps else set()
    except Exception:
        override_steps_set = set()

    # 1) coefficient éventuel dans classification_level
    coeff: Optional[int] = None
    if classification_level:
        m = re.search(r"(\d{2,3})", classification_level)
        if m:
            try:
                coeff = int(m.group(1))
            except Exception:
                coeff = None

    # 1-bis) Accords d'entreprise (parse JSON caché)
    ae_exists_flag = False
    ae_count_val: Optional[int] = None
    ae_items: list[dict[str, Any]] = []
    if ae_exists and str(ae_exists).strip().lower() in {"on", "true", "oui", "1"}:
        ae_exists_flag = True
    try:
        if ae_json:
            data = json.loads(ae_json)
            if isinstance(data, dict):
                ae_exists_flag = bool(data.get("exists", ae_exists_flag))
                ae_count_val = int(data.get("count") or 0) or ae_count
                items = data.get("items") or []
                if isinstance(items, list):
                    for it in items[:5]:
                        title = (it.get("title") or "").strip()
                        dt    = (it.get("date") or "").strip()
                        if title or dt:
                            ae_items.append({"title": title, "date": dt})
    except Exception:
        ae_count_val = ae_count

    # ---------- Server‑side rechecks via resolve() ----------

    # Essai (step 9 en CDD)
    ess_ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "as_of": contract_start,
        "annexe": annexe,
        "statut": statut,
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }
    ess_res = _call_resolver("periode_essai", ess_ctx)
    ess_bounds = ess_res.get("bounds") or {}
    max_essai = ess_bounds.get("max_months")
    if max_essai is None:
        max_essai = 4 if (categorie or "").lower() == "cadre" else 2
    if probation_months is not None and float(probation_months) > float(max_essai):
        conformity_issues.append({
            "key": "essai_srv",
            "step": 10,
            "field": "probation_months",
            "severity": "hard",
            "message": f"Période d’essai saisie ({probation_months} mois) > plafond ({max_essai}).",
            "ref": (ess_res.get("rule") or {}).get("source_ref"),
            "url": (ess_res.get("rule") or {}).get("url"),
            "suggested": max_essai,
        })

    # Rémunération minimale (step 8 en CDD)
    has_13th_flag = False
    try:
        if has_13th_month and str(has_13th_month).strip().lower() in {"on","true","oui","1"}:
            has_13th_flag = True
    except Exception:
        has_13th_flag = False
    ui_work_time_mode = (work_time_mode or "standard_35h")
    wt_api = _map_worktime_mode_ui_to_api(ui_work_time_mode)
    if (work_time_regime or "").lower() == "temps_partiel" and wt_api == "standard":
        wt_api = "part_time"
    _sal_weekly = weekly_hours
    try:
        if idcc == 16 and str(segment or '').strip().upper() == 'TRV' and (work_time_regime or '').lower() == 'temps_complet' and wt_api == 'standard':
            _sal_weekly = 35.0
    except Exception:
        _sal_weekly = weekly_hours
    sal_ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "coeff": coeff,
        "work_time_mode": wt_api,
        "weekly_hours": _sal_weekly,
        "forfait_days_per_year": forfait_days_per_year,
        "classification_level": classification_level,
        "coeff_key": coeff_key,
        "has_13th_month": has_13th_flag,
        "as_of": contract_start,
        "anciennete_months": anciennete_months,
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }
    sal_res = _call_resolver("remuneration", sal_ctx)
    sal_bounds = _norm_minima(sal_res.get("minima") or {})
    floor = sal_bounds.get("monthly_min_eur")
    if floor is not None and salary_gross_monthly is not None:
        try:
            if float(salary_gross_monthly) < float(floor):
                conformity_issues.append({
                    "key": "salaire_min_srv",
                    "step": 8,
                    "field": "salary_gross_monthly",
                    "severity": "hard",
                    "message": f"Salaire saisi ({float(salary_gross_monthly):.2f} €) < minimum applicable ({float(floor):.2f} €).",
                    "ref": (sal_res.get("rule") or {}).get("source_ref"),
                    "url": (sal_res.get("rule") or {}).get("url"),
                    "suggested": float(floor),
                })
        except Exception:
            pass

    # Temps de travail — bornes (step 7 en CDD)
    tt_ctx = {
        "idcc": idcc,
        "categorie": categorie,
        "work_time_mode": wt_api,
        "weekly_hours": weekly_hours,
        "forfait_days_per_year": forfait_days_per_year,
        "as_of": contract_start,
        "segment": segment,
        "statut": statut,
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }
    part_time_data = {}
    try:
        if part_time_payload:
            js = json.loads(part_time_payload)
            if isinstance(js, dict):
                part_time_data = js
    except Exception:
        part_time_data = {}
    is_part_time = (work_time_regime or "").lower() == "temps_partiel"
    tt_res = _call_resolver("temps_travail", tt_ctx)
    tt_bounds = tt_res.get("bounds") or {}
    if wt_api in {"standard", "part_time"} and weekly_hours is not None:
        wmin = tt_bounds.get("weekly_hours_min")
        wmax = tt_bounds.get("weekly_hours_max")
        if wmin is not None and float(weekly_hours) < float(wmin):
            conformity_issues.append({
                "key": "tt_min_srv", "step": 8, "field": "weekly_hours", "severity": "hard",
                "message": f"Heures/semaine saisies ({weekly_hours}) < minimum ({wmin}).",
                "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": wmin,
            })
        if wmax is not None and float(weekly_hours) > float(wmax):
            conformity_issues.append({
                "key": "tt_max_srv", "step": 8, "field": "weekly_hours", "severity": "hard",
                "message": f"Heures/semaine saisies ({weekly_hours}) > plafond ({wmax}).",
                "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": wmax,
            })
    if wt_api == "forfait_days" and forfait_days_per_year is not None:
        dmax = tt_bounds.get("days_per_year_max")
        if dmax is not None and int(forfait_days_per_year) > int(dmax):
            conformity_issues.append({
                "key": "fj_max_srv", "step": 8, "field": "forfait_days_per_year", "severity": "hard",
                "message": f"Forfait-jours saisi ({forfait_days_per_year}) > plafond ({dmax}).",
                "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": dmax,
            })
    if wt_api == "forfait_hours_mod2" and m2_days_cap is not None:
        dmax = tt_bounds.get("days_per_year_max")
        try:
            if dmax is not None and int(m2_days_cap) > int(dmax):
                conformity_issues.append({
                    "key": "m2_jours_max_srv", "step": 8, "field": "m2_days_cap", "severity": "hard",
                    "message": f"Plafond annuel saisi ({m2_days_cap}) > plafond ({dmax}).",
                    "ref": (tt_res.get("rule") or {}).get("source_ref"), "suggested": dmax,
                })
        except Exception:
            pass

    # Congés payés (step 11 en CDD) — minimum
    cp_ctx = {
        "idcc": idcc,
        "anciennete_months": anciennete_months,
        "unit": cp_unit,
        "as_of": contract_start,
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
    }
    cp_res = _call_resolver("conges", cp_ctx)
    cp_bounds = cp_res.get("conges") or cp_res.get("bounds") or {}
    cp_min = cp_bounds.get("min_days")
    cp_sugg = cp_bounds.get("suggested_days")
    if cp_days_number is not None and cp_min is not None and int(cp_days_number) < int(cp_min):
        conformity_issues.append({
            "key": "cp_min_srv", "step": 11, "field": "cp_days_number", "severity": "hard",
            "message": f"CP saisis ({cp_days_number} {cp_unit}) < minimum ({cp_min}).",
            "ref": (cp_res.get("rule") or {}).get("source_ref"), "suggested": cp_min,
        })

    # ---------- Clauses ----------
    selected_keys: list[str] = []
    custom_clauses: list[dict[str, Any]] = []
    clauses_params: dict[str, Any] = {}
    try:
        if clauses_selected_json:
            data = json.loads(clauses_selected_json)
            if isinstance(data, list):
                seen = set()
                for k in data:
                    if isinstance(k, str):
                        kk = k.strip()
                        if kk and kk not in seen:
                            selected_keys.append(kk); seen.add(kk)
    except Exception:
        selected_keys = []
    try:
        if clauses_custom_json:
            data = json.loads(clauses_custom_json)
            if isinstance(data, list):
                for it in data[:10]:
                    title = (it.get("title") or "").strip()
                    text  = (it.get("text") or "").strip()
                    if title or text:
                        custom_clauses.append({"title": title, "text": text})
    except Exception:
        custom_clauses = []
    try:
        if clauses_params_json:
            data = json.loads(clauses_params_json)
            if isinstance(data, dict):
                for k, params in list(data.items())[:30]:
                    if not isinstance(params, dict):
                        continue
                    out = {}
                    for pk, pv in list(params.items())[:30]:
                        key = str(pk)
                        if key.endswith("__label"):
                            out[key] = str(pv)
                        else:
                            try:
                                out[key] = pv if isinstance(pv, (str, int, float)) else json.dumps(pv)
                            except Exception:
                                out[key] = str(pv)
                    clauses_params[str(k)] = out
    except Exception:
        clauses_params = {}

    # Auto‑inclusions (branche) basées sur YAML — CDD
    try:
        from app.services.clauses_library import get_auto_include_keys as _auto_inc
        for kk in _auto_inc(idcc, 'cdd'):
            if kk not in selected_keys:
                selected_keys.append(kk)
    except Exception:
        pass

    # Charger les textes de clauses depuis la bibliothèque
    selected_clause_texts = get_clause_texts(idcc, selected_keys, clauses_params, doc_type='cdd')
    # Clauses automatiques si temps partiel (mêmes règles que CDI)
    auto_clauses = []
    if is_part_time:
        try:
            emp_name = employee_name
            comp = employer_name
            # 1) Égalité de traitement
            auto_clauses.append({
                "title": "Égalité de traitement",
                "body": (
                    f"{emp_name} bénéficiera de tous les droits et avantages reconnus aux salariés à temps plein "
                    f"travaillant dans la société, résultant du Code du travail, des accords collectifs applicables "
                    f"ou des usages, au prorata de son temps de travail. {comp} garantit un traitement équivalent "
                    f"aux autres salariés de même qualification et ancienneté en matière de promotion, déroulement "
                    f"de carrière et accès à la formation. À sa demande, {emp_name} pourra être reçu·e par la direction "
                    f"pour examiner toute difficulté d’application de cette égalité."
                )
            })
            # 2) Cumul d’emplois
            auto_clauses.append({
                "title": "Cumul d’emplois",
                "body": (
                    f"{emp_name} peut exercer une autre activité professionnelle, sous réserve d’en informer préalablement "
                    f"{comp}. Cette activité ne devra pas porter atteinte aux intérêts légitimes de l’entreprise, "
                    f"ni contrevenir aux obligations de loyauté et de confidentialité."
                )
            })
            # 3) Priorité d’affectation
            pr_days = None
            try:
                pr_days = int((part_time_data.get("priority") or {}).get("reply_days") or 0) or None
            except Exception:
                pr_days = None
            delay_txt = f"dans un délai maximal de {pr_days} jours" if pr_days else "dans un délai raisonnable"
            auto_clauses.append({
                "title": "Priorité d’affectation",
                "body": (
                    f"{emp_name} bénéficie d’une priorité d’affectation aux emplois à temps complet ou à temps partiel "
                    f"ressortissant de sa catégorie professionnelle ou équivalents qui seraient créés ou deviendraient vacants. "
                    f"La liste de ces emplois est communiquée avant toute attribution. En cas de candidature, la demande "
                    f"est examinée et une réponse motivée est donnée {delay_txt}."
                )
            })
        except Exception:
            auto_clauses = auto_clauses

    # ---------- Normalisation CDD (contexte + checks basiques) ----------
    reason = (cdd_reason or cdd_type or "").strip() or None
    repl_name = None
    if replaced_employee_name:
        repl_name = replaced_employee_name
    elif (cdd_replace_first_name or cdd_replace_last_name):
        repl_name = " ".join([x for x in [(cdd_replace_first_name or '').strip(), (cdd_replace_last_name or '').strip()] if x]).strip() or None
    repl_job = replaced_employee_position or cdd_replace_job
    repl_reason = replacement_reason or cdd_replace_reason

    term_kind = (cdd_term_kind or ("imprecise" if (no_term and str(no_term).lower() in {"on","true","oui","1"}) else None) or ("fixed" if contract_end else None))
    min_dur_val = cdd_min_duration_value or minimum_duration
    min_dur_unit = cdd_min_duration_unit or "jours"
    renewable_flag = False
    try:
        if cdd_renewable and str(cdd_renewable).strip().lower() in {"on","true","oui","1"}:
            renewable_flag = True
    except Exception:
        renewable_flag = False
    renewals_max = cdd_renewals_max if cdd_renewals_max is not None else (renewal_count or 0)

    # Checks basiques liés au CDD
    if not reason:
        conformity_issues.append({
            "key": "cdd_reason_missing", "step": 4, "field": "cdd_reason",
            "severity": "hard", "message": "Le motif du recours au CDD doit être renseigné (L1242‑2).",
        })
    if (reason == "remplacement") and not (repl_name or repl_job):
        conformity_issues.append({
            "key": "cdd_replacement_details_missing", "step": 4, "field": "cdd_replace_last_name",
            "severity": "hard", "message": "En cas de remplacement, précisez la personne et/ou la fonction remplacée.",
        })
    if (term_kind == "fixed") and (contract_end is None):
        conformity_issues.append({
            "key": "cdd_end_date_missing", "step": 5, "field": "contract_end",
            "severity": "hard", "message": "Date de fin requise pour un CDD à terme fixe.",
        })
    if (term_kind == "imprecise") and (min_dur_val is None):
        conformity_issues.append({
            "key": "cdd_min_duration_missing", "step": 5, "field": "cdd_min_duration_value",
            "severity": "soft", "message": "Sans terme précis, indiquez une durée minimale (L1242‑7).",
        })
    if (term_kind == "imprecise") and not (cdd_term_event and str(cdd_term_event).strip()):
        conformity_issues.append({
            "key": "cdd_term_event_missing", "step": 5, "field": "cdd_term_event",
            "severity": "soft", "message": "Sans terme précis, précisez l’événement déclencheur de fin (ex. retour du remplacé, fin de saison…).",
        })
    # Sans terme précis: motifs admis (remplacement, saisonnier, usage)
    if (term_kind == "imprecise") and reason not in {"remplacement","saisonnier","usage"}:
        conformity_issues.append({
            "key": "cdd_imprecise_reason_forbidden", "step": 5, "field": "cdd_term_kind",
            "severity": "hard", "message": "Sans terme précis uniquement pour remplacement, saisonnier ou usage (L1242‑7, D1242‑1).",
        })
    # Accroissement : interdiction présumée si licenciement éco ≤ 6 mois sur le même poste
    try:
        if (reason == 'accroissement') and cdd_eco_layoff_6m and str(cdd_eco_layoff_6m).strip().lower() in {'oui','on','true','1'}:
            msg = "Accroissement : licenciement économique ≤ 6 mois sur le poste — CDD en principe interdit (sauf exception via accord/PSE)."
            # S'il y a une note de justification, on conserve la sévérité hard (information forte) mais on facilite l'override côté UI
            conformity_issues.append({
                "key": "cdd_eco_layoff_recent",
                "step": 4,
                "field": "cdd_eco_layoff_6m",
                "severity": "hard",
                "message": msg,
                "suggested": None,
            })
    except Exception:
        pass

    # ---------- Prime de précarité (détermination basique) ----------
    # Par défaut 10% Code du travail. Possibilité de 6% si accord étendu (à brancher via table CCN ultérieurement).
    try:
        precarity_rate_val = float(precarity_rate_percent) if precarity_rate_percent is not None else None
    except Exception:
        precarity_rate_val = None
    precarity_source_val = (precarity_rate_source or '').strip() or None
    if precarity_rate_val is None:
        # Fallback: 10% (code). Évolution: si idcc connu et table CCN fournie → 6% + source accord_etendu
        precarity_rate_val = 10.0
        if not precarity_source_val:
            precarity_source_val = 'code'

    # ---------- Contexte pour rendu ----------
    context: Dict[str, Any] = {
        # Type de document
        "document": "CDD",
        "contract_type": "CDD",
        # Employeur
        "employer_name": employer_name,
        "employer_address": employer_address,
        "urssaf_number": urssaf_number,
        "rep_name": _smart_name_case(rep_name),
        "rep_title": rep_title,
        "rep_civility": rep_civility,
        "rep_signatory_kind": rep_signatory_kind,
        "rep_entity_name": rep_entity_name,
        "rep_entity_legal_form": rep_entity_legal_form,
        "rep_entity_siren": rep_entity_siren,
        "rep_entity_rep_civility": rep_entity_rep_civility,
        "rep_entity_rep_last_name": rep_entity_rep_last_name,
        "rep_entity_rep_first_name": rep_entity_rep_first_name,
        "rep_entity_rep_title": rep_entity_rep_title,
        # Salarié
        "employee_civility": employee_civility,
        "employee_name": _smart_name_case(employee_name),
        "birth_date": birth_date,
        "birth_place": birth_place,
        "nationality": nationality,
        "employee_address": employee_address,
        "employee_postal_code": employee_postal_code,
        "employee_city": employee_city,
        "ssn": ssn,
        # CCN & classification
        "idcc": idcc,
        "categorie": categorie,
        "classification_level": classification_level,
        "annexe": annexe,
        "segment": segment,
        "statut": statut,
        "coeff_key": coeff_key,
        "adhesion_syndicat": adhesion_syndicat,
        "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
        # Étape CDD (motif & durée)
        "cdd": {
            "reason": reason,
            "reason_other": (cdd_reason_other_text or None),
            "replacement": {
                "name": _smart_name_case(repl_name),
                "job": repl_job,
                "reason": repl_reason,
            },
            "term": {
                "kind": term_kind,
                "end_date": (contract_end.isoformat() if isinstance(contract_end, date) else None),
                "min_duration_value": min_dur_val,
                "min_duration_unit": min_dur_unit,
                "event_desc": (cdd_term_event or None),
            },
            "renewable": renewable_flag,
            "renewals_max": int(renewals_max or 0),
        },
        # Exposition directe pour le template (accès simple)
        "contract_end": (contract_end.isoformat() if isinstance(contract_end, date) else None),
        "no_term": (term_kind == "imprecise"),
        "cdd_reason": reason,
        "replaced_employee_name": _smart_name_case(repl_name),
        "replaced_employee_position": repl_job,
        "replacement_reason": repl_reason,
        "renewal_count": int(renewals_max or 0),
        "min_duration": min_dur_val,
        "min_duration_unit": min_dur_unit,
        # Emploi
        "job_title": job_title,
        "main_mission": main_mission,
        "annex_activities": annex_activities,
        "mission_in_contract": mission_in_contract,
        "mission_in_annex": mission_in_annex,
        # Temps de travail
        "work_time_regime": work_time_regime,
        "work_time_mode": work_time_mode,
        "part_time": part_time_data if is_part_time else None,
        "weekly_hours": weekly_hours,
        "schedule_info": schedule_info,
        "forfait_hours_per_year": forfait_hours_per_year,
        "forfait_hours_ref": forfait_hours_ref,
        "forfait_days_per_year": forfait_days_per_year,
        "forfait_days_ref": forfait_days_ref,
        "m2_days_cap": m2_days_cap,
        "ref_period_desc": ref_period_desc,
        "trv_fulltime_mode": trv_fulltime_mode,
        "trv_rtt_days_per_year": trv_rtt_days_per_year,
        "trv_ref_desc": trv_ref_desc,
        "trm_service_kind": trm_service_kind,
        "mod_annual_hours_max": mod_annual_hours_max,
        "mod_weekly_hours_cap": mod_weekly_hours_cap,
        "mod_ref_desc": mod_ref_desc,
        # Dates & essai
        "contract_start": contract_start,
        "probation_months": probation_months,
        "probation_renewal_requested": probation_renewal_requested,
        # Rémunération
        "salary_gross_monthly": salary_gross_monthly,
        "has_13th_month": bool(has_13th_flag),
        "remuneration_accessories": remuneration_accessories,
        "expense_policy": expense_policy,
        "bonus13_when": bonus13_when,
        "bonus13_when_free": bonus13_when_free,
        "bonus13_base": bonus13_base,
        "bonus13_base_free": bonus13_base_free,
        # Prime de précarité (CDD)
        "precarity_rate_percent": precarity_rate_val,
        "precarity_rate_source": precarity_source_val,
        "precarity_notes": precarity_notes,
        # Lieu / mobilité
        "workplace_base": workplace_base,
        "work_area": work_area,
        "mobility_clause": mobility_clause,
        # CDD accroissement — contexte carence/éco
        "cdd_eco_layoff_6m": (str(cdd_eco_layoff_6m).strip().lower() if cdd_eco_layoff_6m is not None else None),
        "cdd_eco_layoff_notes": cdd_eco_layoff_notes,
        "employer_postal_code": employer_postal_code,
        "employer_city": employer_city,
        "legal_form": legal_form,
        "siren_number": siren_number,
        # Congés / organismes
        "cp_days_number": cp_days_number,
        "cp_unit": cp_unit,
        "retirement_org": retirement_org,
        "retirement_org_address": retirement_org_address,
        "health_org": health_org,
        "health_org_address": health_org_address,
        "welfare_org": welfare_org,
        "welfare_org_address": welfare_org_address,
        # Santé & sécurité
        "poste_risques_particuliers": poste_risques_particuliers,
        # Entretien pro
        "entretien_periodicity": entretien_periodicity,
        # Clauses
        "clauses_selected": selected_clause_texts,
        "clauses_custom": custom_clauses,
        "auto_clauses": auto_clauses,
        # DPAE / signatures
        "dpae_urssaf_city": dpae_urssaf_city,
        "dpae_date": dpae_date,
        "place_of_signature": place_of_signature,
        "date_of_signature": date_of_signature,
        "copies_count": copies_count,
        # Meta & conformité
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "conformity_issues": conformity_issues,
        "overrides_steps": list(override_steps_set),
        # Rappels bornes/valeurs (annexe)
        "probation_max": max_essai,
        "probation_max_total": ess_bounds.get("max_total_months"),
        "worktime_bounds": tt_bounds,
        "leave_min_days": cp_min,
        "leave_suggested_days": cp_sugg,
        # Préavis (CDD → neutre)
        "notice_dismissal_months": None,
        "notice_resignation_months": None,
    }

    # Aperçu PDF inline (si demandé)
    is_preview = False
    try:
        if preview and str(preview).strip().lower() in {"1","true","on","yes","oui"}:
            is_preview = True
    except Exception:
        is_preview = False
    if is_preview:
        try:
            # utiliser le template CDD si disponible, sinon fallback CDI
            tpl_rel = "pdf/cdd.html.j2"
            tpl_path = UI_TEMPLATES_DIR.parent / "pdf" / "cdd.html.j2"
            if not tpl_path.exists():
                tpl_rel = "pdf/cdi.html.j2"
            pdf_bytes = render_pdf_bytes(tpl_rel, context)
            headers = {"Content-Disposition": 'inline; filename="cdd_preview.pdf"'}
            return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)
        except Exception as e:
            logger.exception("cdd preview render failed: %s", e)
            return JSONResponse({"error": "preview_failed", "detail": str(e)}, status_code=500)

    # 5) PDF (fichier)
    tpl_rel = "pdf/cdd.html.j2"
    tpl_path = UI_TEMPLATES_DIR.parent / "pdf" / "cdd.html.j2"
    if not tpl_path.exists():
        # fallback best-effort tant que le template CDD n'est pas prêt
        tpl_rel = "pdf/cdi.html.j2"
    pdf_path = await run_in_threadpool(render_pdf, tpl_rel, context, out_name=None)
    # Renommer intelligemment en cdd_*.pdf si défaut
    try:
        if pdf_path.endswith(".pdf") and ("/cdi_" in pdf_path or pdf_path.split('/')[-1].startswith("cdi_")):
            from pathlib import Path as _P
            p = _P(pdf_path)
            newp = str(p.with_name(p.name.replace("cdi_", "cdd_")))
            import os as _os
            _os.rename(pdf_path, newp)
            pdf_path = newp
    except Exception:
        pass

    # 6) Snapshot (best effort)
    try:
        snapshot = {
            "document": "CDD",
            "context": {k: v for k, v in context.items()
                        if k not in ("remuneration_accessories", "expense_policy")},
            "ae": {"exists": ae_exists_flag, "count": ae_count_val, "items": ae_items},
            "clauses": {"selected_keys": selected_keys, "custom_count": len(custom_clauses)},
            "rules_applied": [
                {
                    "theme": "periode_essai",
                    "source": (ess_res.get("rule") or {}).get("source"),
                    "source_ref": (ess_res.get("rule") or {}).get("source_ref"),
                    "bloc": (ess_res.get("rule") or {}).get("bloc"),
                },
                {
                    "theme": "salaire",
                    "source": (sal_res.get("rule") or {}).get("source"),
                    "source_ref": (sal_res.get("rule") or {}).get("source_ref"),
                    "bloc": (sal_res.get("rule") or {}).get("bloc"),
                },
                {
                    "theme": "temps_travail",
                    "source": (tt_res.get("rule") or {}).get("source"),
                    "source_ref": (tt_res.get("rule") or {}).get("source_ref"),
                    "bloc": (tt_res.get("rule") or {}).get("bloc"),
                },
                {
                    "theme": "conges_payes",
                    "source": (cp_res.get("rule") or {}).get("source"),
                    "source_ref": (cp_res.get("rule") or {}).get("source_ref"),
                    "bloc": (cp_res.get("rule") or {}).get("bloc"),
                },
            ],
            "generated_at": context["generated_at"],
        }
        snap_path = pdf_path.replace(".pdf", "_snapshot.json")
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("cdd snapshot write failed: %s", e)

    return FileResponse(pdf_path, media_type="application/pdf", filename="cdd.pdf")
