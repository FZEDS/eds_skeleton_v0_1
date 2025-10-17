# EDS — L'Expertise Droit Social — Générateur RH/Juridique

EDS génère des documents (CDI, CDD, lettres, avenants…) via des formulaires multi‑étapes, et produit un PDF de qualité "cabinet" avec annexe de conformité et snapshot JSON d’audit. La conformité est “par design” : les bornes (Code du travail / CCN / accords d’entreprise via override utilisateur) sont expliquées et tracées.

Objectifs rapides
- Simplifier, sécuriser et moderniser les actes RH/droit social.
- Rendre le droit accessible sans sacrifier la rigueur.
- Prendre en charge les CCN complexes que les autres Legaltech craignent, grâce à un système rigoureux et extensible.

Points clés
- Formulaires intelligents (validation live, suggestions, overrides conscients).
- Moteur de règles data‑driven (YAML Code/CCN/Accords d’entreprise).
- Résolveur unifié renvoyant un payload standardisé pour l’UI.
- PDF + annexe de conformité + snapshot JSON d’audit.
- Veille/validation Légifrance.

## Démarrer

### 1) Environnement (macOS)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel
pip install -r requirements.txt

```

### 2) Lancer
```bash
uvicorn app.main:app --reload
# ou
./start.sh
```
Ouvre http://127.0.0.1:8000

Tips
- Multi‑documents: `http://127.0.0.1:8000/documents` (catalogue piloté par `docs/catalog.yml`).
- Aperçu PDF inline (sans écrire sur disque): envoyer `preview=1` à `POST /cdi/generate` ou `POST /cdd/generate`.
- Debug HTML du PDF: `export EDS_KEEP_HTML_DEBUG=1` (conserve l’HTML à côté du PDF).

## Technique mise en place pour implémenter les CCN complexes
- Règles par thèmes en YAML: `rules/code_travail/*.yml` et `rules/ccn/<idcc>/*.yml` (consolidées par le résolveur).
- Hints/micro‑textes UI par CCN: `rules/ccn/<idcc>/ui_hints.(cdi|cdd).yml`.
- Schéma de classification CCN: `rules/ccn/<idcc>/classification.yml` (chargé par l’API `GET /api/classif/schema`).
- Résolution unique: `app/services/rules_resolver.py` retourne un payload standard (bounds/capabilities/rule/explain/suggest).
- Identification de la position exacte du salarié via questionnaire

## Tronc commun + clauses auto_include
- Clauses communes: `rules/clauses/common_<doc>.yml` (ex. `common_cdi.yml`).
- Spécificités CCN: `rules/ccn/<idcc>/clauses_<doc>.yml` (merge par clé). `defaults.auto_include` permet d’inclure des clauses obligatoires par contexte.

## Formulaire CDI
- UI Jinja: `app/templates/ui/cdi_form.html.j2` (plusieurs étapes). Le front appelle les endpoints bornes (`/api/essai/bounds`, `/api/temps/bounds`, etc.) pour guider et contrôler les saisies.
- Génération: `POST /cdi/generate` produit un PDF (`app/templates/pdf/cdi.html.j2`) + snapshot JSON dans `var/generated/`. Mode aperçu via `preview=1`.

## Formulaire CDD
- UI Jinja: `app/templates/ui/cdd_form.html.j2`.
- Génération: `POST /cdd/generate` avec logique équivalente au CDI (aperçu inclus).

## Arborescence
```
Connaissances/          # notes et matrices métier
  Code du travail/      # thèmes (durée du travail, rémunération, ...)
    base_cdd.md
    Modèles_CDD_LAMY.md
    ccd_matrice_primauté.md
    cdi_matrice_primauté.md
    durée_du_travail.md
    rémunération.md
  ccn/
    ccn_0016_transports_routiers/
    ccn_syntec/


app/                    # FastAPI + logique métier
  main.py               # routes UI+API (CDI, CDD, thèmes, génération PDF)
  schemas.py            # schémas (réponses helpers/API)
  services/             # moteurs et services
    rules_engine.py
    rules_resolver.py
    legifrance_client.py
    pdf_renderer.py
    clauses_library.py
    ccn_registry.py
    doc_registry.py
    ui_hints.py
  templates/
    ui/                 # formulaires Jinja
      steps
        cdd
        common
          ccn_ae.html.j2
          calendar.html.j2
          poste_lieu.html.j2
          classification.html.j2
          work_time.html.j2
          remuneration.html.j2
          essai.html.j2
          preavis_et_conges.html.j2
          sante_prev.html.j2
          clauses.html.j2
          formalites.html.j2
      cdi_form.html.j2
      cdd_form.html.j2
      convocation_ep_form.html.j2
      documents_list.html.j2
      index.html.j2
      layout.html.j2
    pdf/
      cdi.html.j2
      cdd.html.j2
      base.css
  static/
    css/
    js/
      cdi.js
      cdd.js
      common/
        eds_ccn_ae.js
        eds_classif.js
        eds_clauses.js
        eds_essai.js
        eds_explain.js
        eds_preavis.js
        eds_salary.js
        eds_step4.js
        eds_steps.js
        eds_submit.js
        eds_worktime.js          
rules/                  # règles YAML (Code du travail / CCN)
  code_travail/
  ccn/
    1486-syntec/
      classification.yml
      clauses_cdd.yml
      clauses_cdi.yml
      conges_payes.yml
      periode_essai.yml
      preavis.yml
      remuneration.yml
      temps_travail.yml
      ui_hints.cdd.yml
      ui_hints.cdi.yml
    0016-transports-routiers/
      classification.yml
      clauses_cdd.yml
      clauses_cdi.yml
      conges_payes.yml
      periode_essai.yml
      preavis.yml
      remuneration.yml
      temps_travail.yml
      ui_hints.cdd.yml
      ui_hints.cdi.yml
    1979-hcr/
      classification.yml
      clauses_cdd.yml
      clauses_cdi.yml
      conges_payes.yml
      periode_essai.yml
      preavis.yml
      remuneration.yml
      temps_travail.yml
      ui_hints.cdd.yml
      ui_hints.cdi.yml
    2216-predominance-alimentaire/
      classification.yml
      clauses_cdd.yml
      clauses_cdi.yml
      conges_payes.yml
      periode_essai.yml
      preavis.yml
      remuneration.yml
      temps_travail.yml
      ui_hints.cdd.yml
      ui_hints.cdi.yml
    1501-restauration-rapide/
      classification.yml
      clauses_cdd.yml
      clauses_cdi.yml
      conges_payes.yml
      periode_essai.yml
      preavis.yml
      remuneration.yml
      temps_travail.yml
      ui_hints.cdd.yml
      ui_hints.cdi.yml
  clauses/
    common_cdd.yml
    common_cdi.yml

docs/                   
  catalog.yml           # documents exposés dans l’UI

scripts/                # outils (lint, validation Légifrance, ping)
tests/                  # tests Pytest (exemples)
var/generated/          # sorties (PDF + JSON snapshot)
```

Endpoints utiles (rapide)
- `GET /` page d’accueil (lien direct vers CDI)
- `GET /documents` catalogue multi‑documents (basé sur `docs/catalog.yml`)
- `GET /api/ccn/list?q=1486` recherche CCN (fallback si registre indisponible)
- `GET /api/classif/schema?idcc=1486&debug=1` schéma de classification (fallback lecture YAML si besoin)
- `GET /api/temps/bounds …` bornes temps de travail (UI→API mappé automatiquement)
- `GET /api/essai/bounds …` bornes période d’essai (CDI/CDD)
- `GET /api/preavis/bounds …` préavis min. (démission/licenciement)
- `GET /api/resolve?theme=…` sortie brute du résolveur (debug)

## Légifrance / PISTE — Validation et veille des références

Objectif: s’assurer que les URLs Légifrance référencées dans les YAML existent et garder un minimum de veille.

### 1) Crédentials et variables d’environnement
```bash
export PISTE_CLIENT_ID=...
export PISTE_CLIENT_SECRET=...
export PISTE_API_KEY=...

# (optionnel) surcharger les URLs si besoin
# export PISTE_OAUTH_URL="https://oauth.piste.gouv.fr/api/oauth/token"
# export PISTE_API_URL="https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
```

### 2) Ping rapide
```bash
python scripts/piste_ping.py
```

### 3) Validation des références dans les YAML
```bash
# Tous les dossiers CCN (auto: online si credentials présents et ping OK; offline sinon)
python scripts/validate_legifrance.py
python scripts/validate_legifrance.py --idcc 1486
python scripts/validate_legifrance.py --strict   # échoue si offline / API KO
```

### 4) Via le linter
```bash
python scripts/lint_rules.py --legifrance
python scripts/lint_rules.py --legifrance --idcc 1486
```

Notes:
- En mode offline (sans credentials), contrôle de forme uniquement (pattern des URLs, cohérence des IDs). Avec credentials, les identifiants KALI (KALITEXT/KALIARTI/KALICONT) sont vérifiés via l’API.
- Les URLs JORF sont vérifiées de façon basique (forme), pas via l’API.

> En **mode strict**, fais échouer la CI pour bloquer un merge tant que les YAML ne sont pas revus : `python -m scripts.watch_legifrance --strict`.

### 7) Bonnes pratiques de saisie YAML

- **Dates** ISO (`YYYY-MM-DD`) pour `effective.from/to` et `meta.effective_from`.  
- **Types** numériques pour bornes/ratios/grilles.  
- `meta.idcc` **=** dossier (ex. `rules/ccn/1486-syntec/…`).  
- **Références** au niveau **règle** (URL `KALIARTI*` préférée).  
- Le résolveur renvoie `rule.url` + `rule.source_ref` (ID KALI/LEGI) pour la **traçabilité** (UI & PDF & snapshot).

### 8) Dépannage express

| Symptôme                   | Cause probable            | Solution                                         |
|----------------------------|---------------------------|--------------------------------------------------|
| `invalid_client` à l’OAuth | mélange PROD/SANDBOX      | vérif `PISTE_OAUTH_URL`/`PISTE_API_URL` & add `scope=openid`|
| `400 ... Unable to find token` | `$TOKEN` vide         | ré-extraire le token (ex. via Python `json.load(...)`) |
| `500` sur `/list/ping`     | en‑têtes inadaptés (`Content-Type`, `X-API-Key`) | utiliser `python -m scripts.piste_ping` (GET minimal) |
| `405` sur `/list/ping`     | POST au lieu de GET        | utiliser GET                                        |
| `offline` dans validate/watch | API KO ou creds absents | passer `--strict` en CI pour bloquer                |

### 9) Sécurité & limites

- **Aucune interprétation automatique** des contenus juridiques : on détecte des **changements** et on **pointe les YAML** concernés.  
- **Zéro scraping HTML** : uniquement l’API officielle DILA/PISTE.  
- **Secrets** en variables d’environnement / GitHub **Secrets**, jamais en clair dans le repo.

## Qualité & CI

- Tests: `pytest -q` (exemples dans `tests/`).
- Lint YAML + validations: `python scripts/lint_rules.py` (intégré à `pre-commit`).
- Pré‑commit: `pip install pre-commit && pre-commit install`.
- Watch Légifrance en CI: `.github/workflows/legifrance-watch.yml` (sandbox PISTE, artefact rapport, issue automatique sur changements).