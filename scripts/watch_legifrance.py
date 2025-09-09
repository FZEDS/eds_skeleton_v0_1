#!/usr/bin/env python3
"""
EDS Legifrance Watch — détecte les évolutions d'articles/textes référencés dans les YAML.

Usage:
  python -m scripts.watch_legifrance [--idcc 1486] [--strict] [--dry-run]

Comportement:
  - Parcourt rules/**.yml, extrait les URLs Legifrance (meta.source.url + rules[*].source/ref.url)
  - Convertit en identifiants KALI/LEGI (KALIARTI*, KALITEXT*, LEGIARTI*)
  - Ping l'API; si offline -> message et exit 0 (sauf --strict)
  - Pour chaque ID: consulte l'API, construit une empreinte (version/etat/dates/hash)
  - Compare à la baseline var/legifrance_watch.json
  - Écrit un rapport JSON dans reports/legifrance_watch/report-YYYYMMDD-HHMMSS.json
  - Met à jour la baseline (sauf --dry-run)
  - Sortie:
      - code 0 si aucun changement (ou offline sans --strict)
      - code 1 si changements détectés ET --strict
"""

from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "rules"
STATE_PATH = ROOT / "var" / "legifrance_watch.json"
REPORTS_DIR = ROOT / "reports" / "legifrance_watch"

# Imports du client
sys.path.insert(0, str(ROOT.resolve()))
from app.services.legifrance_client import LegifranceClient  # type: ignore

# ---------- Extraction des URLs/IDs depuis les YAML ----------

LF_HOST = "legifrance.gouv.fr"

def load_yaml(p: Path) -> Optional[Dict[str, Any]]:
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None

def iter_legifrance_urls(data: Dict[str, Any]) -> Iterable[str]:
    """Récupère meta.source.url et rules[*].source/ref.url s'ils contiennent legifrance.gouv.fr"""
    # meta.source.url
    meta = data.get("meta") or {}
    src = meta.get("source") or {}
    url = src.get("url")
    if isinstance(url, str) and LF_HOST in url:
        yield url.strip()
    # rules[*].source/ref.url
    rules = data.get("rules")
    if isinstance(rules, list):
        for r in rules:
            if not isinstance(r, dict):
                continue
            for key in ("source", "ref"):
                node = r.get(key) or {}
                if isinstance(node, dict):
                    u = node.get("url")
                    if isinstance(u, str) and LF_HOST in u:
                        yield u.strip()

def legifrance_id_from_url(url: str) -> Optional[str]:
    """Extrait l'identifiant KALI/LEGI depuis l'URL (KALIARTI*, KALITEXT*, KALICONT*, LEGIARTI*)."""
    if not isinstance(url, str) or LF_HOST not in url:
        return None
    # On cherche la première occurrence d'un ID connu dans le path
    m = re.search(r"(KALI(?:ARTI|TEXT|CONT)\w+|LEGIARTI\w+)", url)
    return m.group(1) if m else None

def index_repo_ids(idcc_filter: Optional[int]) -> Dict[str, Dict[str, Set[str]]]:
    """Retourne {lf_id: {'urls': set[url], 'files': set[relpath]}} pour tous les YAML du repo, optionnellement filtrés par IDCC."""
    out: Dict[str, Dict[str, Set[str]]] = {}
    for p in RULES_DIR.rglob("*.yml"):
        # filtre IDCC (si demandé)
        if idcc_filter is not None and "/ccn/" in str(p.as_posix()):
            try:
                dname = p.parent.name  # ex: "1486-syntec"
                if int(dname.split("-")[0]) != int(idcc_filter):
                    continue
            except Exception:
                continue
        data = load_yaml(p)
        if not data:
            continue
        for u in iter_legifrance_urls(data):
            lf_id = legifrance_id_from_url(u)
            if not lf_id:
                continue
            rec = out.setdefault(lf_id, {"urls": set(), "files": set()})
            rec["urls"].add(u)
            rec["files"].add(str(p.relative_to(ROOT)))
    return out

# ---------- Fingerprint ----------

def sha256_utf8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def build_fingerprint(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit une empreinte robuste à partir de la réponse API.
    'kind' ∈ {'KALIARTI','KALITEXT','LEGIARTI',...}
    """
    # Cherche le bloc "article" ou "texte" courant selon corpus
    node = (payload.get("article") or
            payload.get("texte") or
            payload.get("text") or
            {})
    # Métadonnées usuelles
    version = node.get("versionArticle") or node.get("versionTexte")
    etat = node.get("etat")
    date_debut = node.get("dateDebut")
    date_fin = node.get("dateFin")
    # Corps
    texte_html = node.get("texteHtml")
    texte_plain = node.get("texte")
    if isinstance(texte_html, str) and texte_html.strip():
        content_hash = sha256_utf8(texte_html)
        content_len = len(texte_html)
    elif isinstance(texte_plain, str) and texte_plain.strip():
        content_hash = sha256_utf8(texte_plain)
        content_len = len(texte_plain)
    else:
        # fallback: hash du sous-objet node (stable trié)
        try:
            content_hash = sha256_utf8(json.dumps(node, sort_keys=True, ensure_ascii=False))
            content_len = None
        except Exception:
            content_hash = sha256_utf8(json.dumps(payload, sort_keys=True, ensure_ascii=False))
            content_len = None
    return {
        "kind": kind,
        "version": version,
        "etat": etat,
        "dateDebut": date_debut,
        "dateFin": date_fin,
        "hash": content_hash,
        "len": content_len,
    }

def detect_kind(lf_id: str) -> str:
    if lf_id.startswith("KALIARTI"): return "KALIARTI"
    if lf_id.startswith("KALITEXT"): return "KALITEXT"
    if lf_id.startswith("KALICONT"): return "KALICONT"
    if lf_id.startswith("LEGIARTI"): return "LEGIARTI"
    return "UNKNOWN"

# ---------- Watcher principal ----------

@dataclass
class WatchResult:
    new: List[Dict[str, Any]]
    changed: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    offline: bool

def run_watch(idcc: Optional[int], strict: bool, dry_run: bool) -> Tuple[int, WatchResult]:
    client = LegifranceClient()
    online = client.ping()
    if not online:
        msg = "[WARN] API Légifrance injoignable — mode offline, aucun contrôle effectué."
        print(msg)
        if strict:
            print("[ERR] --strict demandé mais offline; échec.")
            return 1, WatchResult([], [], [], offline=True)
        return 0, WatchResult([], [], [], offline=True)

    ids_map = index_repo_ids(idcc_filter=idcc)
    if not ids_map:
        print("[INFO] Aucun identifiant Legifrance trouvé dans rules/.")
        return 0, WatchResult([], [], [], offline=False)

    # Charge la baseline
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    new, changed, errors = [], [], []

    for lf_id, refs in sorted(ids_map.items()):
        kind = detect_kind(lf_id)
        try:
            if kind == "KALIARTI":
                payload = client.consult_kali_article(lf_id)
            elif kind == "KALITEXT":
                payload = client.consult_kali_text(lf_id)
            elif kind == "LEGIARTI":
                # dispo si tu as ajouté consult_legi_article
                payload = client.consult_legi_article(lf_id)
            else:
                # KALICONT ou inconnu: on ignore (pas de endpoint direct stable)
                continue
            fp = build_fingerprint(kind, payload)
        except Exception as e:
            errors.append({"id": lf_id, "error": str(e), "files": sorted(refs["files"])})
            continue

        prev = state.get(lf_id)
        if prev is None:
            new.append({"id": lf_id, "fingerprint": fp, "files": sorted(refs["files"]), "urls": sorted(refs["urls"])})
            state[lf_id] = {"fingerprint": fp, "first_seen": ts, "last_seen": ts}
        else:
            if prev.get("fingerprint") != fp:
                changed.append({
                    "id": lf_id,
                    "prev": prev.get("fingerprint"),
                    "curr": fp,
                    "files": sorted(refs["files"]),
                    "urls": sorted(refs["urls"]),
                })
                prev["fingerprint"] = fp
                prev["last_changed"] = ts
            prev["last_seen"] = ts
        time.sleep(0.15)  # petit throttle pour être gentil avec l'API

    # Écrit le rapport
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"report-{time.strftime('%Y%m%d-%H%M%S')}.json"
    report = {
        "timestamp": ts,
        "changed": changed,
        "new": new,
        "errors": errors,
        "count": {"changed": len(changed), "new": len(new), "errors": len(errors)},
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Rapport: {report_path.relative_to(ROOT)}  (changed={len(changed)} new={len(new)} errors={len(errors)})")

    # Met à jour la baseline
    if not dry_run:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    # Sortie
    exit_code = 1 if strict and (changed or new or errors) else 0
    # Résumé clair en console
    for item in changed:
        print(f"[CHANGED] {item['id']}  -> {len(item['files'])} fichier(s)")
        for f in item["files"]:
            print(f"          - {f}")
    for item in new:
        print(f"[NEW]     {item['id']}  -> {len(item['files'])} fichier(s)")
        for f in item["files"]:
            print(f"          - {f}")
    for item in errors:
        print(f"[ERROR]   {item['id']}: {item['error']}  -> {len(item['files'])} fichier(s)")
        for f in item["files"]:
            print(f"          - {f}")

    return exit_code, WatchResult(new=new, changed=changed, errors=errors, offline=False)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--idcc", type=int, help="Limiter la surveillance aux YAML d'une IDCC")
    ap.add_argument("--strict", action="store_true", help="Exit 1 si changements/erreurs détectés")
    ap.add_argument("--dry-run", action="store_true", help="N'écrit pas la baseline")
    args = ap.parse_args()
    code, _ = run_watch(idcc=args.idcc, strict=args.strict, dry_run=args.dry_run)
    return code

if __name__ == "__main__":
    raise SystemExit(main())
