# EDS — Générateur RH/Juridique (squelette)

> **Avertissement** : les règles et références sont **fictives** pour démonstration. Remplace-les par des données réelles (Code du travail, CCN).

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
app/                # code FastAPI + services
rules/              # règles YAML (Code/CCN)
tests/              # tests Pytest (exemples)
docs/               # notes & arbitrages
var/generated/      # sorties (PDF + JSON)
```
