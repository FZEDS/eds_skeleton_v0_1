# CCN 0016 — Modèle de dimensions et intégration (squelette)

Objectif: intégrer la CCN 0016 (Transports routiers) sans lister tous les métiers, en s’appuyant sur des dimensions stables pour le calcul et un questionnaire progressif.

## Dimensions clés (contexte)
- annexe: I | II | III | IV
- segment: TRM_AAT | TRV | EPL | SANITAIRE | DEMENAGEMENT
- statut: roulant | sédentaire
- classification_level: texte libre (groupe/coeff)
- coeff: nombre (dérivé de classification_level si présent)
- work_time_mode: standard | part_time | forfait_hours | forfait_days | forfait_hours_mod2
- equivalence_profile: optionnel
- anciennete_months: entier
- (non bloquant minima) zone_service, decoucher, dimanche_ferie, region_code, zone_deplacement, job_family

## Questionnaire (classification.yml v2)
Voir `rules/ccn/0016-transports-routiers/classification.yml` — questions `annexe`, `segment`, `statut`, `group_coeff`, `job_suggest`.

## Thèmes et sources
- rémunération: grilles GAR/SMPG/taux horaires par segment/coeff; combiner avec SMIC; multiplicateurs (forfait‑jours, 13e mois).  
- temps_travail: Code + règles CCN par segment/statut (équivalences, part‑time guards).  
- période d’essai/préavis: règles par annexe/groupe; fallback Code si absent.  
- congés: base Code; bonus ancienneté si CCN prévoit.

## Étapes suivantes
1. Renseigner progressivement les grilles et bornes par segment/annexe avec références KALI.  
2. Ajouter des `ui_hints` et des `clauses` métiers (non bloquant calcul).  
3. Étendre les tests par thème (cas nominaux et fallback Code).

