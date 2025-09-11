---
title: "Rémunération (France) — mémo opérationnel AE / CCN / Code"
source: "Légifrance, Code du travail numérique, Service-public, BOSS (vérif. 10/09/2025)"
version: "1.0 — 10/09/2025"
auteur: "Farid (workspace)"
licence: "CC BY-NC 4.0"
tags: ["rémunération", "SMIC", "minima de branche", "égalité F/H", "overtime", "bulletin de paie", "transport"]
---

> **But** : sécuriser les règles de **rémunération** dans tes formulaires (CDI/CDD) et éviter les hallucinations.  
> **Principe-clé** : l’**AE prime** sur la **CCN** **sauf** dans les **13 matières** du **Bloc 1** (ex. **minima hiérarchiques**, **classifications**, **garanties collectives complémentaires**) et les **4 matières** du **Bloc 2** (*verrouillables par la branche*, dont **primes pour travaux dangereux/insalubres**). Base : **L2253‑1/‑2/‑3**.  
> Réfs : L2253‑1 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036761771 — L2253‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036761762 — L2253‑3 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036262236

---

## 1) Garde‑fous **d’ordre public** (indépassables)

- **SMIC** (définition et finalités) : **L3231‑2** — *les montants évoluent par décret* (ne **pas** hardcoder).  
  L3231‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006902832 — Page officielle · https://www.service-public.fr/particuliers/vosdroits/F2300

- **Égalité de rémunération F/H** (*à travail égal, rémunération égale*) : **L3221‑2**.  
  L3221‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006902818

- **Définition de la rémunération** (inclut salaire **et** accessoires, en espèces ou en nature) : **L3221‑3**.  
  L3221‑3 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006902819

- **Non‑discrimination (dont rémunération)** : **L1132‑1**.  
  L1132‑1 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000045391841

- **Interdiction des amendes/sanctions pécuniaires** : **L1331‑2**.  
  L1331‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006901446

- **Prise en charge transports publics** (abonnements **50 %**) : **L3261‑2** (principe) + **R3261‑2** (taux 50 %).  
  L3261‑2 · https://www.legifrance.gouv.fr/codes/section_lc/LEGISCTA000006189675/ — R3261‑2 · https://www.legifrance.gouv.fr/codes/id/LEGISCTA000020080275 — Fiche · https://entreprendre.service-public.fr/vosdroits/F37900

- **Minimum garanti (MG)** : sert à évaluer certains **avantages en nature** (notamment repas). Le montant est fixé par décret (ex. **4,22 €** au **01/11/2024**). **Toujours vérifier le montant en vigueur**.  
  L3231‑12 · https://www.circulaires.gouv.fr/codes/section_lc/LEGISCTA000006189665/ — Décret 23/10/2024 · https://www.legifrance.gouv.fr/eli/decret/2024/10/23/TEMX2427845D/jo/texte

> 💡 **Blocage UI** : si `rémunération_base < max(SMIC, minima_branche)` ⇒ **erreur bloquante**. Si une “retenue disciplinaire” est saisie ⇒ **erreur** (L1331‑2).

---

## 2) **AE vs CCN vs Loi** — où l’AE peut primer en matière de rémunération ?

### 2.1 **Minima salariaux & classifications** → **Branche > Entreprise** (Bloc 1)
- Les **salaires minima hiérarchiques** et les **classifications** sont des matières **réservées** à la **branche** : l’AE **ne peut pas** prévoir moins.  
  Base : **L2253‑1 (1° et 2°)** · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036761771

### 2.2 **Primes “dangereux/insalubres”** → **Branche peut verrouiller** (Bloc 2)
- Si la CCN le **verrouille expressément**, l’AE **ne peut pas** y déroger en moins‑disant.  
  Base : **L2253‑2 (4°)** · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036761762

### 2.3 **Tout le reste** (politique primes/variable, modalités internes) → **AE prime** (Bloc 3)
- L’AE peut organiser les **primes**, le **variable**, les modalités d’attribution, **même** si moins favorables que la CCN, **à condition** de respecter **SMIC**, **minima de branche**, **égalité/non‑discrimination** et **ordre public**.  
  Base : **L2253‑3** · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036262236

---

## 3) Composantes de la **rémunération** (à modéliser dans le formulaire)

- **Salaire de base** (≥ **SMIC** **et** ≥ **minima de branche**).  
- **Primes** (ancienneté, objectif, panier, 13ᵉ mois, etc.) : d’origine **AE/CCN/usage**.  
- **Variable** (objectifs) : prévoir **critères objectivables** et **documentés** (**bonne pratique**), non discriminatoires (L1132‑1).  
- **Avantages en nature** (logement, véhicule, repas…) : **entrent** dans la rémunération (L3221‑3) et s’évaluent selon barèmes (dont **MG**).  
- **Frais professionnels** : **n’entrent pas** dans la rémunération (remboursement de dépenses engagées pour l’activité) — cf. **BOSS**.  
  BOSS · https://boss.gouv.fr/portail/accueil/autres-elements-de-remuneration/frais-professionnels.html

---

## 4) Heures **supplémentaires** / temps partiel (**impact rémunération**)

- **Heures supplémentaires** :  
  - **Par AE** (ou à défaut **branche**), fixer le **taux de majoration** (**≥ 10 %**) et le **contingent**. → **L3121‑33**.  
  - **À défaut d’accord** : **25 %** (8 premières HS) puis **50 %**. → **L3121‑36**.  
  L3121‑33 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000038610166 — L3121‑36 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033020341

- **Temps partiel – heures complémentaires** : matières visées au **Bloc 1** (branche).  
  - **Majorations** fixées par **branche** (≥ **10 %** dans la limite légale ; **≥ 25 %** au‑delà des limites d’avenant). → **L3123‑21** et **L3123‑22**.  
  L3123‑21 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033019988 — L3123‑22 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033019984

> 🔎 **Rappel d’ordre public temps/ repos** (indépassable) : max **10 h/j**, **48 h/sem**, moyenne **44 h/12 sem**, repos **11 h** + **24 h**. (Voir ta fiche “durée du travail”.)

---

## 5) Paiement & bulletin

- **Périodicité** : **mensuelle** (salariés mensualisés). Formula **52/12** × durée hebdo légale pour calcul mensuel de référence. → **L3242‑1**.  
  L3242‑1 · https://www.legifrance.gouv.fr/codes/id/LEGISCTA000006178027

- **Mode de paiement** : espèces **ou** chèque/virement (avec seuils et conditions). → **L3241‑1**.  
  L3241‑1 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000044605341

- **Bulletin de paie** : **obligatoire** à chaque versement. → **L3243‑2** ; mentions et présentation → **R3243‑1/‑2** (modèle par arrêté).  
  L3243‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033024092 — R3243‑2 · https://code.travail.gouv.fr/code-du-travail/r3243-2 — Dossier · https://travail-emploi.gouv.fr/le-bulletin-de-paie — Fiche · https://www.service-public.fr/particuliers/vosdroits/F559

- **Prescription des salaires** : **3 ans** (action en paiement/répétition). → **L3245‑1**.  
  L3245‑1 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000027566295

---

## 6) **Matrice AE / CCN / Code** — *rémunération* (résumé)

| Thème | AE > CCN ? | Peut écarter le Code ? | Garde‑fous / Réfs |
|---|---:|---:|---|
| **Minima hiérarchiques** | ❌ | ❌ | **Branche (Bloc 1)** — L2253‑1 (1°). |
| **Classifications** | ❌ | ❌ | **Branche (Bloc 1)** — L2253‑1 (2°). |
| **Primes dangereux/insalubres** | ⚠️ si **non** verrouillé | ❌ | **Branche peut verrouiller (Bloc 2)** — L2253‑2 (4°). |
| **Taux HS** | ✅ (Bloc 3) | ⚠️ (supplétif seulement) | **≥ 10 %** (L3121‑33) ; défaut **25/50 %** (L3121‑36). |
| **Primes internes / variable** | ✅ (Bloc 3) | ❌ | Respect **SMIC** (L3231‑2), **minima de branche** (L2253‑1), **égalité/N‑discrimination** (L3221‑2, L1132‑1). |
| **Avantages en nature** | ✅ (cadre interne) | ❌ | Doivent être valorisés (barèmes, **MG**) ; entrent dans rémunération (L3221‑3). |
| **Transport (50 %)** | ❌ | ❌ | **Obligation légale** (L3261‑2, R3261‑2). |


---

## 7) Liens utiles

- **SMIC** : L3231‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006902832 — Fiche · https://www.service-public.fr/particuliers/vosdroits/F2300 — Info ministérielle · https://travail-emploi.gouv.fr/le-smic-salaire-minimum-de-croissance  
- **Égalité F/H** : L3221‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006902818  
- **Définition rémunération** : L3221‑3 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006902819  
- **Mensualisation** : L3242‑1 · https://www.legifrance.gouv.fr/codes/id/LEGISCTA000006178027 — **Mode de paiement** : L3241‑1 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000044605341  
- **Bulletin de paie** : L3243‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033024092 — R3243‑2 · https://code.travail.gouv.fr/code-du-travail/r3243-2 — Dossier · https://travail-emploi.gouv.fr/le-bulletin-de-paie  
- **Prescription salaires** : L3245‑1 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000027566295  
- **Transports 50 %** : L3261‑2 · https://www.legifrance.gouv.fr/codes/section_lc/LEGISCTA000006189675/ — R3261‑2 · https://www.legifrance.gouv.fr/codes/id/LEGISCTA000020080275 — Fiche · https://entreprendre.service-public.fr/vosdroits/F37900  
- **Architecture AE/CCN** : L2253‑1 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036761771 — L2253‑2 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036761762 — L2253‑3 · https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036262236
