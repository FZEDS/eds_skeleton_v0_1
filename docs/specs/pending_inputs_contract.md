# Contrat `pending_inputs` — Résolveur ⇄ UI (Q&A progressif)

Objectif: permettre au résolveur d’indiquer au front quelles questions minimales il manque pour résoudre un thème (temps, salaire, essai, préavis, congés) dans un contexte CCN donné, sans multiplier les écrans ni collecter des données inutiles.

## Format de réponse (ajout non‑cassant)

Chaque endpoint logique (via `resolve(theme, ctx)`) peut inclure un champ optionnel `pending_inputs`:

```json
{
  "theme": "temps_travail",
  "bounds": { ... },
  "rule": { ... },
  "capabilities": { ... },
  "explain": [ ... ],
  "suggest": [ ... ],
  "pending_inputs": [
    {
      "id": "work_time_mode",
      "label": "Régime du temps de travail",
      "type": "enum",
      "options": [
        {"value":"standard","label":"35h/hebdo"},
        {"value":"part_time","label":"Temps partiel"},
        {"value":"forfait_hours","label":"Forfait heures"},
        {"value":"forfait_days","label":"Forfait jours"}
      ],
      "writes": ["work_time_mode"],
      "required": true,
      "reason": "worktime.mode_required"
    }
  ],
  "trace": { ... }
}
```

Notes:
- Absent ou liste vide ⇒ rien à demander.
- L’UI pose la/les questions en contexte (modale ou encart), met à jour `ctx`, relance le calcul.
- Types supportés: `text`, `number`, `enum`, `boolean`, `date`, `search`, `textarea`.

## Source des questions

Priorité aux questions déclarées par CCN dans `classification.yml` (`questions: [...]`). Le résolveur peut piocher dedans selon le thème et le contexte (idcc, segment, annexe…). À défaut, il peut émettre des questions génériques (ex: `work_time_mode`).

Clés d’une question (superset UI):
- `id`: identifiant stable (ex: `annexe`, `segment`, `statut`, `group_coeff`, `work_time_mode`).
- `label`, `help`, `placeholder` (facultatifs), `required` (bool).
- `type`: `text|number|enum|boolean|date|search|textarea`.
- `options`: pour `enum` — `{value,label}`.
- `writes`: liste des clés de contexte écrites par la réponse.
- `when` (facultatif): prédicat simple (equals/in/range/all/any) si on souhaite le remonter tel quel au front; sinon évalué côté résolveur.
- `reason`: courte clé machine pour l’UI/analytics (ex: `salary.coeff_missing`).

## Règles de décision (exemples 0016)

- Thème `temps_travail` (0016):
  - Si `work_time_mode` absent ⇒ demander `work_time_mode`.
  - Si `segment` ∈ {`TRM_AAT`,`TRV`,`SANITAIRE`} et contrainte spécifique roulants s’applique et `statut` absent ⇒ demander `statut` (roulant/sédentaire).

- Thème `remuneration` (0016):
  - Si `coeff` absent et `classification_level` ne permet pas d’en déduire un entier ⇒ demander `group_coeff` (texte) ou un `enum` de positions si la CCN en définit.
  - Si `work_time_mode` ∈ `forfait_days` et que la branche prévoit un plancher spécifique (ex. SMAG/216 j/an) nécessitant une info d’ancienneté pour la colonne ⇒ si `anciennete_months` absent, demander `anciennete_months` (number) — seulement quand pertinent.

- Thème `periode_essai`/`preavis` (0016):
  - Si la règle dépend de l’annexe/groupe et que `annexe`/`coeff` manquent ⇒ demander `annexe` (enum) et/ou `group_coeff` (text).

## Guidelines UI

- Afficher un composant léger (modale/contextuel) listant 1–2 questions maxi, justifiées par un texte court (`reason` + `ui_hints`).
- Renseigner immédiatement `ctx` à la réponse et relancer l’appel; pas d’étape additionnelle.
- Traçabilité: journaliser les `pending_inputs` posés dans l’annexe PDF (facultatif, slot dédié) ou le snapshot.

## Implémentation (phase 1)

1) Résolveur (`resolve`) — enrichir la réponse avec `pending_inputs` sans rompre l’existant.
   - Lire `classification.yml` si présent (clé `questions`), créer un index par `id`.
   - Politique par thème: détecter les clés manquantes; mapper vers les questions correspondantes; retourner un sous‑ensemble minimal.
2) UI — composant générique `AskOnDemand` repliant:
   - Si `pending_inputs` non vide: ouvrir modale; pour chaque item, rendre un contrôle selon `type`.
   - À submit: mettre à jour les champs cachés déjà présents (`categorie`, `classification_level`, etc.) + un store `EDS_CTX` (si nécessaire), puis relancer `resolve`.

## Sécurité juridique

- Ne demander qu’une info nécessaire à la règle ciblée (principe de minimisation).  
- Afficher la source de la règle qui motive la question (via `ui_hints` et `explain`, pas forcément dans l’item `pending_inputs`).

