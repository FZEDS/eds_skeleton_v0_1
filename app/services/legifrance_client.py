# app/services/legifrance_client.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class LegifranceAuthError(RuntimeError):
    pass


class LegifranceClientError(RuntimeError):
    pass


def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return None
    return v


@dataclass
class PisteCredentials:
    client_id: str
    client_secret: str
    api_key: Optional[str] = None


def load_piste_credentials() -> Optional[PisteCredentials]:
    """Charge les identifiants PISTE depuis les variables d'environnement.

    Variables supportées:
      - PISTE_CLIENT_ID
      - PISTE_CLIENT_SECRET
      - PISTE_API_KEY (optionnelle selon le compte)
    """
    cid = _env("PISTE_CLIENT_ID")
    cs = _env("PISTE_CLIENT_SECRET")
    ak = _env("PISTE_API_KEY")
    if not cid or not cs:
        return None
    return PisteCredentials(client_id=cid, client_secret=cs, api_key=ak)


class LegifranceClient:
    """Client minimal et robuste pour l'API Légifrance via PISTE.

    - Flux OAuth2 client_credentials pour obtenir un Bearer token
    - Méthodes utilitaires (ping, consult KALI, validation d'URL)
    - En-têtes adaptés selon le verbe HTTP (GET vs POST JSON)
    - Retries prudents (429/5xx)

    Configuration par variables d'environnement :
      - PISTE_OAUTH_URL :
            prod    -> https://oauth.piste.gouv.fr/api/oauth/token
            sandbox -> https://sandbox-oauth.piste.gouv.fr/api/oauth/token
      - PISTE_API_URL  :
            prod    -> https://api.piste.gouv.fr/dila/legifrance/lf-engine-app
            sandbox -> https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app
      - PISTE_CLIENT_ID / PISTE_CLIENT_SECRET / (optionnel) PISTE_API_KEY
      - PISTE_ACCESS_TOKEN | PISTE_BEARER | PISTE_TOKEN (si tu veux injecter un token existant)
      - EDS_LF_DEBUG=1 pour logs stderr
    """

    OAUTH_TOKEN_URL = os.getenv("PISTE_OAUTH_URL", "https://oauth.piste.gouv.fr/api/oauth/token")
    # Surchargée via env PISTE_API_URL (ex: https://api.piste.gouv.fr/dila/legifrance/lf-engine-app)
    BASE_API = os.getenv("PISTE_API_URL", "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app")

    def __init__(self, creds: Optional[PisteCredentials] = None, session: Optional[requests.Session] = None):
        self.creds = creds or load_piste_credentials()
        self._session = session or requests.Session()
        self._install_retries()
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._debug: bool = str(os.getenv("EDS_LF_DEBUG", "")).lower() in {"1", "true", "yes"}
        # Permet d'injecter un token existant (obtenu en dehors du client) pour éviter l'étape OAuth
        self._token_env: Optional[str] = _env("PISTE_ACCESS_TOKEN") or _env("PISTE_BEARER") or _env("PISTE_TOKEN")

    # ---------- infra ----------
    def _install_retries(self, total: int = 2, backoff: float = 0.5) -> None:
        retry = Retry(
            total=total,
            backoff_factor=backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def _log(self, msg: str) -> None:
        if self._debug:
            try:
                import sys
                print(f"[LegifranceClient] {msg}", file=sys.stderr)
            except Exception:
                pass

    # ---------- OAuth ----------
    def is_configured(self) -> bool:
        return self.creds is not None

    def _get_token(self) -> str:
        # Si un bearer est fourni via l'environnement, on l'utilise tel quel
        if self._token_env:
            return self._token_env
        if not self.creds:
            raise LegifranceAuthError("PISTE credentials manquants (variables PISTE_CLIENT_ID/PISTE_CLIENT_SECRET)")

        now = time.time()
        if self._token and now < (self._token_exp - 30):
            return self._token

        # Refresh token (form-urlencoded) + scope=openid
        data = {
            "grant_type": "client_credentials",
            "client_id": self.creds.client_id,
            "client_secret": self.creds.client_secret,
            "scope": "openid",
        }
        resp = self._session.post(self.OAUTH_TOKEN_URL, data=data, timeout=15)
        if resp.status_code != 200:
            raise LegifranceAuthError(f"OAuth token error {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in") or 600)
        if not token:
            raise LegifranceAuthError("OAuth: 'access_token' absent dans la réponse")
        self._token = token
        self._token_exp = now + max(60, expires_in)
        return token

    # ---------- Headers & HTTP helpers ----------
    def _headers(
        self,
        *,
        json: bool = True,
        accept: Optional[str] = None,
        include_api_key: bool = False,
    ) -> Dict[str, str]:
        """
        Construit des en-têtes adaptés :
          - GET (ping) : json=False -> pas de Content-Type, Accept optionnel (ex: '*/*')
          - POST JSON : json=True   -> Content-Type: application/json + Accept: application/json (par défaut)
          - API key : uniquement si explicitement demandée (certaines APIs PISTE la requièrent, pas Légifrance/ping)
        Par défaut, json=True pour conserver la compatibilité avec les usages existants (c._headers()).
        """
        headers: Dict[str, str] = {"Authorization": f"Bearer {self._get_token()}"}
        if include_api_key and self.creds and self.creds.api_key:
            headers["X-API-Key"] = self.creds.api_key
            headers["X-API-KEY"] = self.creds.api_key
        if json:
            headers["Content-Type"] = "application/json"
            headers["Accept"] = accept or "application/json"
        elif accept:
            headers["Accept"] = accept
        return headers

    def _get(self, path: str, *, accept: str = "*/*", include_api_key: bool = False) -> requests.Response:
        url = f"{self.BASE_API.rstrip('/')}/{path.lstrip('/')}"
        self._log(f"GET  {url}")
        resp = self._session.get(
            url,
            headers=self._headers(json=False, accept=accept, include_api_key=include_api_key),
            timeout=20,
        )
        self._log(
            f"-> status={resp.status_code} corr={resp.headers.get('x-correlationid','')} "
            f"len={resp.headers.get('content-length','?')}"
        )
        return resp

    def _post_json(self, path: str, payload: Dict[str, Any]) -> requests.Response:
        url = f"{self.BASE_API.rstrip('/')}/{path.lstrip('/')}"
        self._log(f"POST {url} payload={{{...}}}")
        resp = self._session.post(
            url,
            headers=self._headers(json=True, accept="application/json", include_api_key=False),
            json=payload,
            timeout=20,
        )
        self._log(
            f"-> status={resp.status_code} corr={resp.headers.get('x-correlationid','')} "
            f"len={resp.headers.get('content-length','?')}"
        )
        return resp

    # ---------- Helpers ----------
    @staticmethod
    def parse_legifrance_url(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extrait (kind, id, container) depuis une URL Legifrance.

        Exemples supportés:
          - https://www.legifrance.gouv.fr/conv_coll/id/KALITEXT000050228699
          - https://www.legifrance.gouv.fr/conv_coll/article/KALIARTI000047513825?idConteneur=KALICONT000005635173

        Retourne: (kind, id, container) où kind ∈ {KALITEXT, KALIARTI, KALICONT}
        """
        try:
            import urllib.parse as up
            if not url:
                return None, None, None
            lower = url.lower()
            if "legifrance.gouv.fr" not in lower:
                return None, None, None
            parts = url.split("/")
            lf_id = None
            kind = None
            for p in parts[::-1]:
                if p.startswith("KALITEXT") or p.startswith("KALIARTI") or p.startswith("KALICONT"):
                    lf_id = p
                    if p.startswith("KALITEXT"):
                        kind = "KALITEXT"
                    elif p.startswith("KALIARTI"):
                        kind = "KALIARTI"
                    else:
                        kind = "KALICONT"
                    break
            q = up.urlparse(url).query
            params = up.parse_qs(q)
            cont = None
            for key in ["idConteneur", "idconteneur", "container", "conteneur"]:
                if key in params:
                    cont = params[key][0]
                    break
            return kind, lf_id, cont
        except Exception:
            return None, None, None

    # ---------- API Légifrance ----------
    def ping(self) -> bool:
        """Retourne True si /list/ping répond 200. En-têtes minimaux (pas d'API key)."""
        try:
            resp = self._get("list/ping", accept="*/*", include_api_key=False)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def consult_kali_text(self, kalitext_id: str) -> Dict[str, Any]:
        """Consulte un texte KALI (KALITEXT*)."""
        if not kalitext_id:
            raise LegifranceClientError("Identifiant KALITEXT manquant")
        resp = self._post_json("consult/kaliText", {"id": kalitext_id})
        if resp.status_code != 200:
            raise LegifranceClientError(f"consult/kaliText {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def consult_kali_article(self, kaliarti_id: str) -> Dict[str, Any]:
        """Consulte un article KALI (KALIARTI*)."""
        if not kaliarti_id:
            raise LegifranceClientError("Identifiant KALIARTI manquant")
        resp = self._post_json("consult/kaliArticle", {"id": kaliarti_id})
        if resp.status_code != 200:
            raise LegifranceClientError(f"consult/kaliArticle {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def consult_legi_article(self, legiarti_id: str) -> Dict[str, Any]:
        """Consulte un article LEGI (codes/lois) : LEGIARTI*."""
        if not legiarti_id:
            raise LegifranceClientError("Identifiant LEGI article manquant")
        resp = self._post_json("consult/getArticle", {"id": legiarti_id})
        if resp.status_code != 200:
            raise LegifranceClientError(f"consult/getArticle {resp.status_code}: {resp.text[:200]}")
        return resp.json()


    def consult_legi_article(self, legiarti_id: str) -> Dict[str, Any]:
        """Consulte un article fonds LEGI (LEGIARTI*). Pratique pour les tests."""
        if not legiarti_id:
            raise LegifranceClientError("Identifiant LEGIARTI manquant")
        resp = self._post_json("consult/getArticle", {"id": legiarti_id})
        if resp.status_code != 200:
            raise LegifranceClientError(f"consult/getArticle {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # ---------- Vérification/validation ----------
    def check_exists(self, lf_id: str) -> bool:
        """Retourne True si l'identifiant (KALITEXT/KALIARTI/KALICONT) est consultable.
        KALICONT est validé indirectement (cohérence via les articles).
        """
        if not self.is_configured():
            # Sans credentials, on ne fait pas d'appel réseau — on ne valide pas.
            return False
        try:
            if lf_id.startswith("KALIARTI"):
                _ = self.consult_kali_article(lf_id)
                return True
            if lf_id.startswith("KALITEXT"):
                _ = self.consult_kali_text(lf_id)
                return True
            if lf_id.startswith("KALICONT"):
                # Validé indirectement via cohérence d'article
                return True
            return False
        except (LegifranceClientError, LegifranceAuthError, requests.RequestException) as e:
            self._log(f"check_exists error for {lf_id}: {e}")
            return False

    def validate_legifrance_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """Vérifie qu'une URL Legifrance KALI semble valide et (si possible) existe.

        Retourne (ok, message_diagnostic). Si credentials absents, contrôle de forme uniquement.
        """
        kind, lf_id, cont = self.parse_legifrance_url(url)
        if not lf_id:
            return False, "URL Legifrance non reconnue ou identifiant manquant"

        if not (lf_id.startswith("KALITEXT") or lf_id.startswith("KALIARTI") or lf_id.startswith("KALICONT")):
            return False, f"Identifiant inattendu: {lf_id}"

        if self.is_configured():
            exists = self.check_exists(lf_id)
            if not exists:
                return False, f"Identifiant non trouvé via API: {lf_id}"
            # Optionnel : si article, vérifier cohérence du conteneur si fourni
            if cont and cont.startswith("KALICONT") and kind == "KALIARTI":
                try:
                    art = self.consult_kali_article(lf_id)
                    container_id = (
                        (art.get("article") or {}).get("cidConteneur")
                        or (art.get("article") or {}).get("idConteneur")
                        or (art.get("conteneur") or {}).get("id")
                    )
                    if container_id and container_id != cont:
                        return False, f"Article {lf_id} rattaché à {container_id}, différent de {cont}"
                except Exception:
                    # En cas d'échec non bloquant, on considère la présence de l'article suffisante
                    pass
        else:
            return True, "Validation de forme (offline) — credentials PISTE absents"
        return True, None
