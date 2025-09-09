#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from datetime import date
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


def _is_number(x):
    return isinstance(x, (int, float))


def _is_iso_date(s: str) -> bool:
    try:
        date.fromisoformat(str(s))
        return True
    except Exception:
        return False


def check_temps_travail(p: Path, data) -> bool:
    ok = True
    if not isinstance(data, dict):
        return ok
    rules = data.get("rules") or []
    if not isinstance(rules, list):
        print(f"[ERR] {p}: 'rules' doit être une liste")
        return False
    NUM_KEYS = {
        "weekly_hours_min",
        "weekly_hours_max",
        "average_12_weeks_max",
        "days_per_year_max",
        "days_per_year_cap",
        # part-time guards
        "break_threshold_hours",
        "daily_amplitude_max_if_break",
        "daily_amplitude_max_inventory",
        "min_halfday_hours",
        "breaks_per_day_max",
        "breaks_per_week_max",
        "max_break_duration_hours",
        "min_sequence_hours",
        "daily_amplitude_max",
        "break_premium_mg_ratio",
        "break_premium_min_eur",
        "forbid_breaks_if_weekly_hours_lt",
        "forbid_breaks_if_monthly_hours_lt",
        # work program
        "program_prevenance_days",
        "program_modify_deadline_days",
    }
    for i, r in enumerate(rules):
        eff = r.get("effective") or {}
        if isinstance(eff, dict):
            f = eff.get("from"); t = eff.get("to")
            if f is not None and not _is_iso_date(f):
                print(f"[ERR] {p}: rule#{i} effective.from non‑ISO: {f}")
                ok = False
            if t is not None and not _is_iso_date(t):
                print(f"[ERR] {p}: rule#{i} effective.to non‑ISO: {t}")
                ok = False
        c = r.get("constraint") or {}
        if isinstance(c, dict):
            for k, v in c.items():
                if k in NUM_KEYS and v is not None and not _is_number(v):
                    print(f"[ERR] {p}: rule#{i} constraint.{k} doit être numérique, trouvé {type(v).__name__}")
                    ok = False
            # cohérence min/max
            wmin = c.get("weekly_hours_min"); wmax = c.get("weekly_hours_max")
            try:
                if _is_number(wmin) and _is_number(wmax) and float(wmin) >= float(wmax):
                    print(f"[ERR] {p}: rule#{i} weekly_hours_min >= weekly_hours_max")
                    ok = False
            except Exception:
                pass
    return ok


def check_remuneration(p: Path, data) -> bool:
    ok = True
    if not isinstance(data, dict):
        return ok
    meta = data.get("meta") or {}
    eff = meta.get("effective_from")
    if eff is not None and not _is_iso_date(eff):
        print(f"[ERR] {p}: meta.effective_from non‑ISO: {eff}")
        ok = False

    grid = data.get("grid")
    if grid is not None and not isinstance(grid, dict):
        print(f"[ERR] {p}: grid doit être un objet (dict)")
        ok = False
    # Vérifie que toutes les feuilles de 'grid' sont numériques
    def _check_grid_node(node, path="grid"):
        nonlocal ok
        if isinstance(node, dict):
            for k, v in node.items():
                _check_grid_node(v, f"{path}.{k}")
        else:
            if not _is_number(node):
                print(f"[ERR] {p}: {path} doit contenir des nombres (trouvé {type(node).__name__})")
                ok = False
    if isinstance(grid, dict):
        _check_grid_node(grid)

    # policy.monthly_floor_ratio: nombres
    ratios = ((data.get("policy") or {}).get("monthly_floor_ratio") or {})
    for k, v in ratios.items():
        if not _is_number(v):
            print(f"[ERR] {p}: policy.monthly_floor_ratio.{k} doit être numérique")
            ok = False

    # multipliers: nombres au dernier niveau
    def _check_mults(node, path="multipliers"):
        nonlocal ok
        if isinstance(node, dict):
            for k, v in node.items():
                _check_mults(v, f"{path}.{k}")
        else:
            if not _is_number(node):
                print(f"[ERR] {p}: {path} doit contenir des nombres (trouvé {type(node).__name__})")
                ok = False
    mults = data.get("multipliers") or {}
    if isinstance(mults, dict) and mults:
        _check_mults(mults)
    return ok


def check_conges(p: Path, data) -> bool:
    ok = True
    if not isinstance(data, dict):
        return ok
    rules = data.get("rules") or []
    if not isinstance(rules, list):
        return ok
    for i, r in enumerate(rules):
        key = (r.get("key") or "").lower()
        if key == "cp_base":
            b = (r.get("base") or {})
            if not isinstance(b.get("jours_ouvres"), int) or not isinstance(b.get("jours_ouvrables"), int):
                print(f"[ERR] {p}: cp_base doit définir base.jours_ouvres et base.jours_ouvrables (entiers)")
                ok = False
        if key in {"anciennete_bonus_ouvres", "anciennete_bonus"}:
            sch = r.get("bonus_schedule") or {}
            if not isinstance(sch, dict) or not sch:
                print(f"[ERR] {p}: bonus_schedule manquant/invalide pour {key}")
                ok = False
            else:
                for k, v in sch.items():
                    try:
                        int(k)
                    except Exception:
                        print(f"[ERR] {p}: bonus_schedule clé '{k}' non convertible en entier (années)")
                        ok = False
                    if not isinstance(v, int):
                        print(f"[ERR] {p}: bonus_schedule valeur '{v}' doit être un entier (jours)")
                        ok = False
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legifrance", action="store_true", help="Valider aussi les références Legifrance (via PISTE)")
    ap.add_argument("--idcc", type=int, help="Limiter la validation Legifrance à une IDCC")
    ap.add_argument("--strict", action="store_true", help="--strict pour Legifrance: échouer si offline")
    args = ap.parse_args()

    ok = True
    for p in RULES.rglob("*.yml"):
        data = load_yaml(p)
        if data is None:
            ok = False
            continue
        if p.name == "ui_hints.yml":
            ok = check_ui_hints(p, data) and ok
        if p.name.endswith("temps_travail.yml"):
            ok = check_temps_travail(p, data) and ok
        if p.name.endswith("remuneration.yml"):
            ok = check_remuneration(p, data) and ok
        if p.name.endswith("conges_payes.yml"):
            ok = check_conges(p, data) and ok
    # Optionnel: validation Legifrance
    if args.legifrance:
        try:
            sys.path.insert(0, str((ROOT / "scripts").resolve()))
            import validate_legifrance as vl  # type: ignore
            lf_ok = vl.run(strict=args.strict, idcc=args.idcc)
            ok = ok and lf_ok
        except Exception as e:
            print(f"[ERR] Échec validation Legifrance: {e}")
            ok = False

    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
