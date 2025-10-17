# EDS — Générateur RH/Juridique (squelette)

EDS — Générateur de documents RH/Juridique “cabinet”, conformité par design

EDS est une legaltech full code qui génère des documents (CDI, CDD, avenants, lettres…) via des formulaires multi-étapes et produit un PDF de qualité “cabinet”, avec annexe de conformité et snapshot d’audit.
La conformité est “par design” : les bornes (Code du travail / CCN / Accords d’entreprise via override utilisateur) sont expliquées, et tracées.


1) Vision & objectifs

Simplifier, sécuriser et moderniser la gestion du droit social & RH.

Rendre le droit accessible sans sacrifier la rigueur.

Offrir des contenus fiables, des outils performants et un conseil actionnable.

Fonctions clés :

Formulaires intelligents (validation live, “ramener à” ou override conscient).

Moteur de règles data-driven (YAML Code/CCN/AE via override utilisateur).

Résolveur unifié renvoyant un payload standardisé pour le front.

PDF avec annexe de conformité + snapshot JSON d’audit.

Veille Légifrance : alerte si un article/texte référencé dans nos YAML évolue.

## Démarrer

### 1) Environnement (macOS)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel
pip install -r requirements.txt
# Si WeasyPrint requiert des libs :
# brew install pango cairo gdk-pixbuf libffi libxml2 libxslt
```

### 2) Lancer
```bash
uvicorn app.main:app --reload
```
Ouvre http://127.0.0.1:8000

### 3) Générer un CDI
- Clique **Créer un CDI**
- Renseigne l'entreprise, le salarié, la catégorie, la CCN (ex. `1486`), et la durée d'essai proposée
- Télécharge le PDF. Le snapshot JSON est dans `var/generated/`

## Arborescence
```
Connaissances/          # notes et matrices métier
  Dossier_CDD.md
  Modèles_CDD_LAMY.md
  Code du travail/      # thèmes (durée du travail, rémunération, ...)
  ccn/
    ccn_0016_transports_routiers/
    ccn_syntec/

app/                    # FastAPI + logique métier
  main.py               # routes UI+API (CDI, CDD, thèmes, génération PDF)
  routers/              # routes modulaires
  schemas/              # schémas d'IO
  schemas.py            # schémas combinés (réponses helpers)
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
      cdi_form.html.j2
      cdd_form.html.j2
      convocation_ep_form.html.j2
      documents_list.html.j2
      index.html.j2
      layout.html.j2
      components/macros.html.j2
    pdf/
      cdi.html.j2
      cdd.html.j2
      base.css
  static/
    css/
    js/
      cdi.js
      cdd.js
      common/           # helpers (worktime, salaire, essai, etc.)

rules/                  # règles YAML (Code du travail / CCN)
  code_travail/
  ccn/
    1486-syntec/
    0016-transports-routiers/
    1979-hcr/
    2216-predominance-alimentaire/
    1501-restauration-rapide/
  clauses/

docs/                   # catalogues et notes
  catalog.yml           # documents exposés dans l’UI
  decisions/
    readme.md

scripts/                # outils (lint, validation Légifrance, ping)
tests/                  # tests Pytest (exemples)
var/generated/          # sorties (PDF + JSON snapshot)
```

## Légifrance / PISTE — Validation et veille des références

Objectif: s’assurer que les URLs Légifrance référencées dans les YAML existent et garder un minimum de veille.

### 1) Crédentials et variables d’environnement
```bash
export PISTE_CLIENT_ID=...
export PISTE_CLIENT_SECRET=...
# (optionnel selon votre compte)
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

+### 8) Dépannage express

| Symptôme | Cause probable | Solution |
|---|---|---|
| `invalid_client` à l’OAuth | mélange PROD/SANDBOX ou `scope` manquant | vérifier `PISTE_OAUTH_URL`/`PISTE_API_URL` & ajouter `scope=openid` |
| `400 ... Unable to find token` | `$TOKEN` vide | ré-extraire le token (ex. via Python `json.load(...)`) |
| `500` sur `/list/ping` | en‑têtes inadaptés (`Content-Type`, `X-API-Key`) | utiliser `python -m scripts.piste_ping` (GET minimal) |
| `405` sur `/list/ping` | POST au lieu de GET | utiliser GET |
| `offline` dans validate/watch | API KO ou creds absents | relancer plus tard ou passer `--strict` en CI si tu veux bloquer |

### 9) Sécurité & limites

- **Aucune interprétation automatique** des contenus juridiques : on détecte des **changements** et on **pointe les YAML** concernés.  
- **Zéro scraping HTML** : uniquement l’API officielle DILA/PISTE.  
- **Secrets** en variables d’environnement / GitHub **Secrets**, jamais en clair dans le repo.
