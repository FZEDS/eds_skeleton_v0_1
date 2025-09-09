#!/usr/bin/env python3
"""
Validation des références Legifrance dans les YAML CCN.

Usage:
  python scripts/validate_legifrance.py [--idcc 1486] [--strict]

Comportement:
  - Parcourt rules/ccn/<IDCC-...>/*.yml
  - Vérifie la cohérence meta.idcc ~ dossier
  - Récupère TOUTES les URLs Legifrance pertinentes:
      * meta.source.url
      * rules[*].source.url
      * rules[*].ref.url
      * rules[*].refs[] (liste de dicts ou de chaînes)
  - En ligne: appelle l'API via PISTE pour valider l'existence (KALI* supporté)
  - Hors ligne: contrôle de forme non bloquant (sauf --strict)

Notes:
  - Online/offline est déterminé via /list/ping avec en-têtes minimaux
  - On ne "casse" pas sur ui_hints.yml si du texte contient 'legifrance' hors URL
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

import yaml
import requests

# --- Locaux & chemins
ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "ccn"

# --- Imports robustes du client (package > fallback)
try:
    from app.services.legifrance_client import (
        LegifranceClient,
        load_piste_credentials,
    )
except Exception:  # fallback si 'app' n'est pas un package
    sys.path.insert(0, str((ROOT / "app").resolve()))
    from services.legifrance_client import (  # type: ignore
        LegifranceClient,
        load_piste_credentials,
    )


# -------------------- Helpers YAML --------------------
def load_yaml(p: Path) -> Optional[Dict[str, Any]]:
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"[ERR] YAML invalide: {p}: {e}")
        return None


def idcc_from_dirname(d: Path) -> Optional[int]:
    try:
        return int(str(d.name).split("-")[0])
    except Exception:
        return None


def validate_meta_idcc(p: Path, data: Dict[str, Any], expected_idcc: Optional[int]) -> bool:
    meta = data.get("meta") or {}
    found = meta.get("idcc")
    if expected_idcc and found and int(found) != int(expected_idcc):
        print(f"[ERR] {p}: meta.idcc={found} ≠ dossier {expected_idcc}")
        return False
    return True


# -------------------- Extraction d'URLs --------------------
def _add_url(urls: List[str], u: Any) -> None:
    if isinstance(u, str):
        s = u.strip()
        if s and "legifrance.gouv.fr" in s:
            urls.append(s)


def iter_legifrance_urls(data: Dict[str, Any]) -> List[str]:
    """
    Retourne les URLs Legifrance présentes dans:
      - meta.source.url
      - rules[*].source.url
      - rules[*].ref.url
      - rules[*].refs[] (chaînes ou dicts avec 'url')
    """
    urls: List[str] = []

    # meta.source.url
    meta = data.get("meta") or {}
    src = meta.get("source") or {}
    _add_url(urls, src.get("url"))

    # rules[*]
    rules = data.get("rules")
    if isinstance(rules, list):
        for r in rules:
            if not isinstance(r, dict):
                continue
            # source.url
            _add_url(urls, (r.get("source") or {}).get("url"))
            # ref.url
            _add_url(urls, (r.get("ref") or {}).get("url") if isinstance(r.get("ref"), dict) else None)
            # refs[] : peut être une liste de dicts {'url': "..."} ou de chaînes
            refs = r.get("refs")
            if isinstance(refs, list):
                for it in refs:
                    if isinstance(it, dict):
                        _add_url(urls, it.get("url"))
                    else:
                        _add_url(urls, it)

    # Déduplication en conservant l'ordre
    seen: set[str] = set()
    uniq: List[str] = []
    for u in urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    return uniq


# -------------------- Réseau / PING --------------------
def lf_ping(client: LegifranceClient) -> bool:
    """
    Ping minimal (GET /list/ping) avec en-têtes acceptés:
      - Authorization: Bearer <token>
      - Accept: */*
    Pas de X-API-Key, pas de Content-Type.
    """
    try:
        base = client.BASE_API.rstrip("/")
        headers = {"Authorization": f"Bearer {client._get_token()}", "Accept": "*/*"}
        resp = client._session.get(f"{base}/list/ping", headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


# -------------------- Validation --------------------
def offline_shape_check(url: str) -> Tuple[bool, str]:
    """
    Contrôle de forme "soft" en mode offline:
      - URL Legifrance reconnue ?
      - Identifiant KALI* détecté ?
    Ne consulte pas l'API. Ne doit pas échouer le build (sauf --strict géré plus haut).
    """
    kind, lf_id, _ = LegifranceClient.parse_legifrance_url(url)  # type: ignore[attr-defined]
    if not lf_id:
        return False, "URL Legifrance non reconnue ou identifiant manquant"
    if not (lf_id.startswith("KALITEXT") or lf_id.startswith("KALIARTI") or lf_id.startswith("KALICONT")):
        return False, f"Identifiant inattendu (non KALI*): {lf_id}"
    return True, ""


def validate_file(client: LegifranceClient, p: Path, *, online: bool, strict_offline: bool) -> bool:
    data = load_yaml(p)
    if data is None:
        return False

    ok = True

    # idcc cohérent
    expected_idcc = idcc_from_dirname(p.parent)
    ok = validate_meta_idcc(p, data, expected_idcc) and ok

    # URLs à valider
    urls = iter_legifrance_urls(data)
    if not urls:
        return ok

    for url in urls:
        if online:
            exists, diag = client.validate_legifrance_url(url)
            if not exists:
                print(f"[ERR] {p}: URL non valide: {url} ({diag or 'échec inconnu'})")
                ok = False
        else:
            ok_shape, diag = offline_shape_check(url)
            if not ok_shape:
                # offline: avertissement par défaut, échec si --strict
                if strict_offline:
                    print(f"[ERR] {p}: offline: {diag} — {url}")
                    ok = False
                else:
                    print(f"[WARN] {p}: offline: {diag} — {url}")

    return ok


def run(strict: bool = False, idcc: Optional[int] = None) -> bool:
    base = RULES
    if not base.exists():
        print(f"[ERR] Dossier introuvable: {base}")
        return False

    target_dirs: List[Path] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        if idcc is not None:
            try:
                if int(str(d.name).split("-")[0]) != int(idcc):
                    continue
            except Exception:
                continue
        target_dirs.append(d)

    client = LegifranceClient()
    creds = load_piste_credentials()

    # Détermination du mode online/offline
    if not creds:
        print("[INFO] PISTE credentials absents — validation de forme uniquement (offline).")
        if strict:
            print("[ERR] --strict demandé mais credentials absents.")
            return False
        online = False
    else:
        online = lf_ping(client)
        if not online:
            print("[WARN] API Légifrance injoignable (/list/ping KO) — validation de forme uniquement (offline).")
            if strict:
                print("[ERR] --strict demandé et API injoignable.")
                return False

    ok = True
    for d in target_dirs:
        for p in sorted(d.glob("*.yml")):
            ok = validate_file(client, p, online=online, strict_offline=strict) and ok

    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--idcc", type=int, help="Limiter la validation à une IDCC (ex. 1486)")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Échec si credentials absents OU si l'API est injoignable (pas de mode offline).",
    )
    args = ap.parse_args()
    ok = run(strict=args.strict, idcc=args.idcc)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
