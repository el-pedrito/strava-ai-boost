# Spec technique — Intégrité des chiffres du coach

**Date :** 2026-08-04
**Statut :** WP0, WP1, WP2, WP2b, WP4, WP5, WP5a, WP6 livrés et déployés. WP3 restant.
**Dernière mise à jour :** 2026-08-05
**Portée :** pipeline coach (`coach_generator`, `content_generator`, `embedded_prompts`),
coach conversationnel (`coach_chat`), préférences athlète
**Lots :** WP0 → WP7

---

## 1. Problème et principe directeur

Le coach énonçait des chiffres faux : décomptes hebdomadaires, répétitions d'intervalles,
séances restantes, volumes. Symptômes d'origine rapportés par l'athlète : « le coach se perd
dans les semaines du programme Campus », et une EF 40min déjà faite présentée comme à faire.

> **Principe directeur, validé empiriquement : tout chiffre laissé au modèle a été faux,
> tout chiffre déplacé dans le code a été juste.**

| Cas de production | Chiffre du modèle | Réalité | Cause racine |
|---|---|---|---|
| Répétitions | « 7x1min » | 9 laps réels | plan W30 cité pour une séance W31 ; le prompt ne recevait **aucun** `repeat` (`coach_context` lisait `repeats` au pluriel, le producteur écrit `repeat`) |
| Volume hebdo | « 35km cette semaine, +32% ramp » | 6,4km | fenêtre glissante 7j présentée comme semaine ISO |
| Séances restantes | « 2 restantes » | 4 | champ `status` legacy lu au lieu du statut effectif |
| Muscu | « 2 séances muscu » | 1 | 1re ligne de `weekly_breakdown` (= semaine passée) lue comme semaine courante, sur instruction explicite d'un prompt périmé |
| Muscu (résiduel) | « Upper B le 03/08 » | le 03/08 était une course | **fabrication** : la donnée n'existe dans aucun champ du payload |
| Répétitions muscu | « 320 reps au total » + « fun fact » inventé | 238 (calcul depuis la description) | **fabrication non sollicitée** : aucun champ ne fournit ce total, aucune instruction ne le demande |
| Tonnage | 10 370 kg | 15 370 kg | schéma d'extraction **lossy** : `{sets, reps, weight_kg}` ne peut pas porter `10x80 8x90 8x90` |
| Séries | 26 séries / 248 reps | 25 / 238 | `xN` en suffixe lu comme « une série plus N » au lieu de « N au total » |

Les quatre premiers cas sont des défauts de données ou d'instructions : corrigés, ils ne
reviennent pas. Le cinquième est d'une autre nature et définit le cœur du travail restant.

---

## 2. Invariants (ne pas régresser)

Documentés dans AGENTS.md, protégés par tests.

1. **Statut d'exécution** : uniquement via `shared/campus_status.effective_status()`.
   Le champ legacy `status` **n'existe plus** — retiré du code (précédence : `local_status`
   → `matched_activity_id`/`completed_at` → `provider_status` → `todo`) et purgé de la table
   (`scripts/migrate_campus_legacy_status.py`, 33 lignes, appliqué le 04/08, idempotent).
   Le miroir dans `coach_chat_agent.py` est verrouillé par `test_matches_shared_effective_status`.
2. **Identité de semaine** : toujours le label ISO `'YYYY-Www'` via
   `shared/iso_week.iso_week_label()`. Jamais un entier nu. **Violé à 4 endroits → WP0.**
3. **Intervalles** : trois formes tolérées, normalisées par
   `modules_processing._normalize_intervals()`. Jamais sommer un `repeat` par entrée.
   Durée planifiée : préférer `expected_duration_min` du provider.
4. **Lectures scopées semaine** : `Query` sur la PK `session_date = week-YYYY-Www`, fallback
   `is_current_week` avec warning. Le scoring discrimine mal les semaines (0,82 contre la
   semaine homonyme voisine, au-dessus du seuil 0,5) : le scoping est la vraie protection.
5. **Champs hebdo à couverture disjointe** :
   - `week_overview` = LA semaine de l'activité, activité courante incluse, avec `label` lisible
   - `weekly_breakdown` = semaines strictement passées, 1re ligne « Semaine derniere »
   - `recent_activities_by_week` = détail indexé par semaine ISO, jamais une liste plate
6. **Chiffres pré-calculés** : `volume_ramp`, `avg_pace`, `prs_set_this_activity`,
   `avg_weekly_km_last_4_weeks`, `campus_matched_session`.
7. **Contrat prompt↔données** : toute règle de prompt qui nomme un champ doit être relue quand
   la *couverture* de ce champ change. La contradiction « Cette semaine = 1re ligne de
   `weekly_breakdown` » a produit le cas 4 alors que toutes les données étaient justes.
8. **Tout garde-fou de prompt existe dans les DEUX prompts** (pipeline et chat), vérifié par
   `tests/regression/test_coach_prompt_guardrails.py`.

---

## 3. État des lieux

### Acquis (déployé, validé sur activités réelles)

- Retrait complet du champ `status` legacy (code + migration + tests).
- Rendu des intervalles corrigé : `repeat` et `duration` présents dans le texte du plan.
- Sync Campus 9x/jour au lieu de 1x (jusqu'à 13h de retard auparavant).
- Matcher partagé `match_campus_session()` appelé par les deux branches parallèles.
- Scoring pondéré gym-vs-PPG : fin du `0.8` codé en dur qui fermait la PPG à chaque séance
  de salle. La déclaration de l'athlète dans le texte **original** est le facteur décisif.
- Restructuration hebdo (`week_overview` / `weekly_breakdown` disjoints, prompt routé).
- Portabilité des scripts de déploiement (`--profile` conditionnel).
- 374 tests verts.

### Restant

| Lot | Sujet | Statut |
|---|---|---|
| WP0 | Entiers nus de semaine | **livré** (4 sites ; `dashboard_api` corrigé au-delà du remplacement : l'arithmétique `année × 52` était fausse au passage d'année ISO) |
| WP1 | `iso_week` sur les activités du chat | **livré** (miroir + test anti-dérive) |
| WP2 | Outil `get_weekly_totals` | **livré** (test d'égalité contre `build_week_overview`) |
| WP2b | Outil muscu du chat + promesse retirée | **livré** (`get_strength_sessions` lit les totaux stockés) |
| WP3 | Vérificateur post-génération | **RESTANT** — la fabrication est toujours possible en production |
| WP4 | `body_weight_kg` / `height_cm` | **livré** (amorcé depuis Strava, saisie jamais écrasée) |
| WP5 | Tonnage | **livré** (`shared/strength_volume.py`, calculé à l'écriture, lu partout) |
| WP5a | Persistance `strength_history` | **livré** + 64 séances récupérées |
| WP6 | Outillage de test | **livré** (`.venv-test` 3.11, suite complète sans exclusion) |
| WP7 | Commits | en cours |

---

## 4. WP0 — Entiers nus de semaine (prioritaire)

L'invariant 2 est violé à 4 endroits ; la spec initiale le déclarait acquis, c'était faux.

| Fichier:ligne | Code | Gravité |
|---|---|---|
| `content_generator.py:329` | `activity_iso_week = activity_dt.isocalendar()[1]` | **haute** — la variable s'appelle `iso_week` mais contient un entier nu, et cette branche écrit le marqueur de complétion en base |
| `content_generator.py:335` | idem, fallback `datetime.now()` | haute |
| `dashboard_api.py:1308-1309` | `now.isocalendar()[1]`, `dt.isocalendar()[1]` | moyenne (affichage) |

C'est exactement le bug corrigé dans `coach_generator` (un `32` nu ne peut pas être comparé
aux `week_date_iso` écrits par la sync), laissé vivant dans la branche contenu.

**Livrables** : remplacer par `iso_week_label()` ; test de non-régression interdisant
`isocalendar()[1]` hors de `shared/iso_week.py`.

**Acceptation** : aucun `isocalendar()[1]` hors du helper ; le marqueur de complétion écrit
par la branche contenu porte un label ISO.

---

## 5. WP1 + WP2 — Chiffres hebdomadaires côté chat

### Constat

`query_activities` rend une **liste plate triée par date**, sans `iso_week`
(`_compact_activity`, `coach_chat_agent.py:238`) : exactement la forme qui a produit le cas 2.
Le prompt du chat interdit la fenêtre glissante mais n'offre **aucune alternative** — le
modèle n'a que le calcul à la main pour répondre « combien cette semaine ? ».

Contrainte : le runtime `coach_chat` ne peut pas importer `lambda_functions/shared/`
(`--entrypoint "src/coach_chat/coach_chat_agent.py"`, bundle limité à `src/coach_chat/`).
Vérifié : aucun import de `shared` dans ce répertoire.

### WP1 — `iso_week` sur chaque activité

- `_compact_activity` : ajouter `"iso_week": iso_week_label(date)`.
- Miroir local de `iso_week_label` + test anti-dérive `test_matches_shared_iso_week_label`,
  sur le modèle éprouvé de `_effective_status` (`coach_chat_agent.py:192`,
  test `coach_week_disambiguation.py:256`).
- Prompt chat : « chaque activité porte `iso_week`, regrouper par ce champ, jamais par
  calcul de date ».

### WP2 — Outil `get_weekly_totals`

Ce qui a réglé le pipeline n'est pas l'étiquetage, c'est le **total calculé en code**. Le chat
étant agentique, la forme correcte est un 6e outil, pas un champ injecté.

- `get_weekly_totals(user_id, weeks_back: int = 4) -> list[dict]`, retour par semaine ISO :
  `{iso_week, label, runs, run_km, strength, other, total, is_current}`.
- Query sur `UserActivitiesIndex`. **Aucun changement IAM** : le rôle a déjà
  `dynamodb:Query` sur la table activities + index (`deploy_agentcore_agents.sh:495-498`).
- Miroir du bucketing + test anti-dérive contre `build_week_overview` sur fixtures communes.
- Prompt chat : « tout total hebdomadaire vient de `get_weekly_totals` ; INTERDIT de compter
  en parcourant `query_activities` ». Nouveau garde-fou `weekly_totals_from_tool` ajouté au
  test anti-dérive, donc **dans les deux prompts** (invariant 8).
- À faire dans le même lot : ajouter `dynamodb:Query` sur la table sessions à
  `CoachChatToolsDataAccess` (`deploy_agentcore_agents.sh:488`, actuellement `Scan` seul
  ligne 510-511) et convertir `get_campus_plan` en Query.

**Acceptation** : « combien de séances cette semaine ? » au chat rend les mêmes chiffres que
`week_overview` du pipeline pour la même semaine ; test d'égalité sur fixtures partagées ;
test anti-dérive étendu, toujours sans `parametrize` (contrainte `test_docs_sync`).

---

## 6. WP3 — Vérificateur post-génération

### Constat

Après correction de la contradiction de prompt, le pipeline a encore produit « 2e séance
muscu en 2 jours (Upper B le 03/08) » alors que `week_overview.done_this_week.strength = 1`,
que `recent_activities_by_week['2026-W32']` ne contient qu'une course, et que le modèle se
contredit dans le même paragraphe (« 1 run 6,4km hier »). Le chiffre varie d'une exécution à
l'autre (« 4e en 6 jours », puis « 2e en 2 jours ») : c'est une fabrication, pas une lecture
erronée. **Aucune correction de données ou de prompt ne peut l'éliminer** — il n'y a plus
d'ambiguïté à supprimer.

### Options évaluées

| Option | Verdict |
|---|---|
| Retirer les dates individuelles du payload | inutile : la date inventée n'existe pas dans les données |
| Durcir encore le prompt | rendements décroissants, 3 itérations déjà |
| Sortie structurée contrainte | casse le format narratif de `strava_block` |
| **Vérification post-génération + régénération** | mécanique, testable, non invasif — **retenu** |

### Conception

- `lambda_functions/processing/coach_output_check.py` :
  `verify_weekly_claims(feedback, week_overview) -> list[str]`.
- Champs vérifiés : `strava_block`, `detailed_analysis`, `recommendation_next`
  (les 3 champs texte, cf. `embedded_prompts.py:845-847`).
- Détection ciblée sur les motifs qui ont réellement menti, pas de NLP ambitieux :
  - `(\d+)\s*(?:e|ème)?\s*séances?\s*(?:de\s*)?muscu` → vs `done_this_week.strength`
  - `(\d+)\s*courses?` et `(\d[\d,.]*)\s*km` adjacents à « cette semaine » → vs `runs` /
    `run_km` (tolérance 0,1 km)
  - `il (?:te )?reste (\d+)` → vs `campus_remaining.count`
- Écart détecté → **une seule** régénération, avec `verification_errors: [...]` ajouté au
  payload (« tu as écrit 2 muscu, la donnée dit 1 »).
- Échec de la 2e passe → **retirer la phrase fautive** plutôt que publier un chiffre faux
  (supprimer une affirmation de décompte coûte moins cher que la publier fausse), puis
  émettre `metrics.add_metric("CoachClaimMismatch")` et stocker `unverified_claims` avec le
  feedback (`store_coach_feedback`, `coach_generator.py:1051`).
- Faisabilité vérifiée : `_invoke_coach_agent(activity_data, user_config, historical_summary)`
  accepte un payload enrichi sans changement de signature. Durées réelles mesurées sur 24
  invocations : médiane 25s, max 29s, timeout Lambda à 120s → deux passes tiennent avec marge.
- **`verification_errors` doit être documenté dans le prompt** (il y apparaît 0 fois
  aujourd'hui) : sans règle, le modèle ignore le champ. WP3 implique donc un redéploiement
  runtime coach.
- Hors périmètre : le chat (streaming token par token, pas de post-traitement avant émission).
  Couvert indirectement par WP1/WP2 qui suppriment la matière à fabrication. Risque résiduel
  assumé, réévalué à la lumière de la métrique.

**Acceptation** : les 5 phrases fautives réelles du §1 sont détectées, les formulations
correctes équivalentes passent ; rejouer `19596127525` ne produit plus de décompte muscu ≠ 1,
ou renseigne `unverified_claims` ; la métrique donne enfin une **mesure** du phénomène,
aujourd'hui visible seulement en lisant les sorties à la main.

---

## 7. WP4 — Mensurations structurées

### Constat

La donnée existe, mais uniquement en prose dans `athlete_profile` : *« Pierre est un athlète
masculin de 1m92 pour environ 92kg »*. **Ne pas parser ce texte** : le même paragraphe
contient quatre valeurs en kg.

| Valeur | Signification |
|---|---|
| 92kg | poids de corps (la cible) |
| 92kg | « poids de forme » en 2017 |
| 120kg | PR développé couché |
| 120kg | PR squat |

Une regex « nombre suivi de kg » attrape 120, et la valeur cible est précédée de « environ ».
Fonder un tonnage publié sur Strava sur l'interprétation d'une prose ambiguë reproduirait la
faute corrigée aujourd'hui.

### Conception

Deux champs à plat dans `user_preferences`, même convention et même validation que `max_hr`
(`user_preferences_api.py:201-206`) :

| Champ | Type | Bornes | Amorçage |
|---|---|---|---|
| `body_weight_kg` | number | 30-250 | **Strava**, automatique |
| `height_cm` | number | 100-250 | 192, une fois, confirmé par l'athlète |

**Le poids est déjà récupéré depuis Strava, et jeté.** `activity_fetcher.py:387` lit
`profile_data.get('weight')` de l'API athlète (valeur en kg, structurée, maintenue par
l'athlète) puis se contente de la logger :

```python
weight = profile_data.get('weight')
if weight:
    logger.info(f"Athlete Weight: {weight}kg")   # jamais persisté
```

Source idéale : structurée, déjà dans une réponse existante, sans interprétation.
- Persister dans `body_weight_kg` quand Strava renvoie une valeur, **sans jamais écraser une
  saisie manuelle** (la saisie explicite est autoritaire ; Strava peut être périmé ou vide).
- Aucune requête API supplémentaire.
- Strava n'expose **pas** la taille : `height_cm` reste manuel.

Le texte libre `athlete_profile` reste inchangé — contexte narratif, jamais calcul.
`height_cm` remplacera la phrase en prose dans le contexte athlète injecté.

**Livrables** : validation API, page Preferences (frontend), README (tableau Personal
Profile), persistance depuis Strava dans `activity_fetcher`.

**Acceptation** : les deux champs sont saisissables et validés ; une valeur Strava amorce le
poids sans écraser une saisie ; le tonnage (WP5) les consomme.

---

## 8. WP5 — Tonnage des séances de musculation

### Objectif

Pour une activité `WeightTraining`, exposer des chiffres **calculés en code** : séries
totales, répétitions totales, et volume soulevé = Σ (séries × reps × charge).
Exemple : 4x10 à 80 kg → 3 200 kg. Les mouvements au poids du corps utilisent
`body_weight_kg` : 4 tractions → 4 × poids de corps.

### Acquis réutilisable

`_extract_strength_sets()` (`content_generator.py:737`) produit déjà
`parsed_sets = [{exercise, sets, reps, weight_kg}]`, noms normalisés sur les 40
`CANONICAL_STRENGTH_EXERCISES`. Stocké par `_track_strength_history()` (ligne 807), déjà
consommé par le dashboard (`dashboard_api.py:499-548`, qui calcule un `volume_kg` partiel).

### Ambiguïté à traiter : `weight_kg = null`

Le prompt d'extraction dit *« null for bodyweight **or unknown** »* (ligne 727). Un null seul
ne distingue pas « tractions au poids du corps » de « charge inconnue au développé couché ».

- `BODYWEIGHT_EXERCISES` dans `shared/strength_exercises.py` : table {nom canonique →
  coefficient}, **seule** source autorisée pour résoudre un null en poids de corps.
- `weight_kg = null` hors de cette table = charge inconnue → exclu du tonnage, et
  l'exclusion est **signalée**, jamais absorbée en silence.
- `volume_kg_incomplete: true` + `excluded_exercises: [...]` dès qu'un exercice n'a pas pu
  être valorisé (même convention que `counts_incomplete` de `week_overview`). Sous-estimer
  sans le dire serait la même classe de mensonge que celle corrigée aujourd'hui.
- Autres cas : lesté (« tractions +10kg » → poids de corps + 10), `reps = null` → exclu et
  signalé.

### Coefficients au poids du corps

| Exercice | Coefficient | Note |
|---|---|---|
| `Tractions` | 1.0 | corps entier déplacé |
| `Dips` | 1.0 | corps entier déplacé |
| `Pompes` | 1.0 | **règle de l'athlète appliquée** |

Réserve documentée : la charge réelle en pompes est d'environ **65 %** du poids de corps.
À 1.0, une séance de pompes est surestimée d'environ 35 % et son tonnage n'est pas comparable
à celui d'une séance de tractions. La règle explicite de l'athlète (« les tractions, les dips,
les pompes, va partir sur mon poids du corps ») est appliquée ; `Pompes: 0.65` est un
changement d'une ligne dans la table si la comparabilité devient prioritaire.

### Exercices unilatéraux — on compte les deux côtés

Un unilatéral noté « 4x10 @30kg » représente 4 séries **par côté**. Les trois chiffres sont
expansés ensemble pour rester cohérents :

| Chiffre | Valeur |
|---|---|
| séries | 8 |
| répétitions | 80 |
| volume | 8 × 10 × 30 = **2 400 kg** |

L'expansion porte sur les séries, pas sur un facteur appliqué au seul volume : sinon
`séries × reps × charge` ne redonnerait plus le volume affiché et l'incohérence serait visible.

- `UNILATERAL_EXERCISES` dans `shared/strength_exercises.py`, même forme que
  `BODYWEIGHT_EXERCISES`. Sur les 40 exercices actuels, un seul est explicite :
  `Tirage horizontal unilatéral machine`.
- `Curl marteau` et `Fentes` sont **ambigus** (alterné ou simultané ; les fentes alternent par
  nature) : **hors** de l'ensemble par défaut. Doubler à tort est une surestimation
  silencieuse. Ils y entrent sur confirmation de l'athlète.
- `per_exercise` porte `unilateral: true` sur les exercices doublés, pour que le doublement
  soit vérifiable et non implicite.
- Réserve de convention : la règle suppose la notation « par côté ». Si l'athlète note déjà
  le total des deux côtés, le doublement surestimerait. Point unique de changement.

### Livrables

- `lambda_functions/shared/strength_volume.py` :
  `compute_session_volume(parsed_sets, body_weight_kg) -> dict`
  → `{total_sets, total_reps, volume_kg, body_weight_kg_used, per_exercise[],
  volume_kg_incomplete, excluded_exercises[]}`.
- **`body_weight_kg_used` est obligatoire dans le résultat** : le poids de l'athlète dérive
  (construction hybride), et sans cette trace une comparaison de tonnage entre deux mois
  devient fausse sans qu'on puisse le détecter.
- Champ absent → mouvements au poids du corps non calculés, marqués incomplets. **Jamais de
  valeur par défaut** : un 70kg arbitraire produirait un chiffre plausible et faux, le pire cas.
- Injection dans le payload du content agent **et** du coach : même champ, une seule source.
- Règle de prompt (les deux prompts, invariant 8) : ces chiffres sont fournis, ne jamais les
  recalculer ni les estimer ; si `volume_kg_incomplete`, ne pas présenter le total comme exact.
- Le dashboard calcule déjà un `volume_kg` partiel (`dashboard_api.py:523`) : le faire
  consommer le module partagé, sinon deux définitions du tonnage divergeront.

**Acceptation** : 4x10@80 = 3 200 ; 4 tractions @92kg = 368 ; lesté correct ; `reps = null`
→ incomplet signalé ; exercice inconnu → incomplet signalé ; `body_weight_kg` absent →
incomplet signalé sans crash ; unilatéral → séries doublées et volume cohérent ;
dashboard et pipeline rendent le même tonnage pour la même séance.

---

## 9. WP5a — Persistance de `strength_history` (prérequis bloquant de WP5)

### Constat

L'extraction **fonctionne** (`Extracted 8 structured strength sets from description`) mais
l'écriture échoue :

```
Failed to track strength history: ValidationException ...
The document path provided in the update expression is invalid
```

Conséquence vérifiée : `strength_history` **n'existe pas** dans `user-configuration`.
Aucune entrée, pour aucune activité.

### Cause

`_track_strength_history` (`content_generator.py:807`) fait :

```
SET user_preferences.strength_history.entries = list_append(
      if_not_exists(user_preferences.strength_history.entries, :empty), :entry)
```

`if_not_exists` couvre la **liste** mais pas la **map parente** : DynamoDB refuse
`SET a.b.c` quand `a.b` n'existe pas et ne crée jamais les niveaux intermédiaires.
`user_preferences` existe, `user_preferences.strength_history` non → l'expression est
invalide pour tout athlète qui n'a jamais eu d'entrée. C'est-à-dire tous.

### Impact

- Aucun historique de musculation accumulé : le suivi de progression du coach
  (« low row à 90kg vs 80kg il y a 6 jours ») n'a **aucune source persistée**, il est
  reconstruit à chaque fois depuis les descriptions brutes.
- Le graphique de force du dashboard (`dashboard_api.py:499-548`, qui consomme
  `parsed_sets`) n'a rien à afficher.
- **WP5 tel que spécifié supposait `parsed_sets` stocké : hypothèse fausse.**
- Deuxième défaillance silencieuse sur ce chemin : un commentaire du code documente déjà un
  « live incident 2026-07-18/20: entries were silently dropped ». L'exception est avalée en
  `warning`, donc la perte de données ne remonte nulle part.

### Livrables

- Initialiser la map avant l'append : un `SET user_preferences.strength_history =
  if_not_exists(...)` séparé (chemins qui se chevauchent interdits dans une seule
  expression), puis l'append. Idempotent, deux écritures pour un événement rare.
- **Rendre l'échec bruyant** : `metrics.add_metric("StrengthHistoryWriteFailed")`. Une perte
  de données qui se produit deux fois en silence est un défaut d'observabilité autant que de
  code.
- `scripts/backfill_strength_history.py` (`--dry-run` par défaut, `--apply` pour écrire) :
  rejouer l'extraction sur les activités `WeightTraining` existantes. Même modèle que
  `migrate_campus_legacy_status.py`.
- Test : première écriture sur un athlète sans `strength_history` (le cas qui échoue
  aujourd'hui), puis append sur un athlète qui en a déjà une.

**Acceptation** : `strength_history.entries` contient une entrée par séance de musculation ;
le dashboard affiche la progression des charges ; une écriture en échec émet une métrique.

---

## 10. WP2b — Le chat ne voit rien des séances de musculation

### Constat

`_compact_activity` (`coach_chat_agent.py:238`) rend neuf champs : `activity_id`, `date`,
`type`, `name`, `distance_km`, `duration_min`, `pace`, `avg_hr`, `max_hr`.

Pour un `WeightTraining` le chat voit donc : type, nom, **0 km**, une durée, une FC.
Aucun exercice, aucune série, aucune répétition, aucune charge — la description brute est
elle-même absente. Aucun des cinq outils ne renvoie de charge ou de série.

**Et le prompt promet le contraire** : la description de `get_coach_observations` parle de
« progression des charges en musculation » (ligne 638) et le catalogue d'outils l'annonce
pour la « progression muscu » (ligne 695).

C'est le miroir de la contradiction corrigée hier. Hier une instruction désignait un mauvais
champ ; ici une instruction désigne un champ **inexistant**. Dans les deux cas le modèle
obéit et comble le vide en inventant. Une capacité annoncée sans données est une invitation
à fabriquer.

### Livrables

- **Immédiat, sans attendre l'outil** : retirer du prompt du chat la promesse de
  « progression muscu » / « progression des charges ». Un prompt qui ne promet rien vaut
  mieux qu'un prompt qui promet du vide.
- `get_strength_sessions(user_id, weeks_back=4)` : 6e outil, rendant par séance les
  exercices avec `sets`/`reps`/`weight_kg` et les totaux **calculés** (mêmes chiffres que
  WP5 : `total_sets`, `total_reps`, `volume_kg`, `body_weight_kg_used`,
  `volume_kg_incomplete`).
- Source : `strength_history` (donc **après WP5a**), lu via `get_item` sur
  `user-configuration` — l'IAM du chat a déjà `dynamodb:GetItem` sur cette table
  (`deploy_agentcore_agents.sh:504-505`), aucun changement requis.
- Règle de prompt : les totaux viennent de cet outil, jamais d'un comptage sur les
  descriptions. Nouveau garde-fou au test anti-dérive, donc dans les deux prompts.

**Acceptation** : « combien de reps hier ? » au chat rend le total calculé (238 pour la
séance du 04/08), identique à celui du pipeline ; aucune promesse de prompt sans outil
correspondant.

---

## 11. WP6 — Outillage (dette, non bloquant)

- **Venv 3.12** : l'environnement n'a que Python 3.9 avec pytest ; 4 modules ne se chargent
  pas (`datetime.UTC`, `uvicorn`). Créer `.venv-test/` et exécuter la suite sans `--ignore`.
- **`test_docs_sync`** : comptage par parsing de source, fragile (interdit `parametrize` en
  unit, en exige exactement 1 en régression). Remplacer par `pytest --collect-only`.
- **`test_memory_retrieval.py`** : 4 tests dépendants de l'ordre (passent en suite complète,
  échouent isolés) — mock `uvicorn` manquant localement.
- **`configure_agentcore_integration.sh` ~844** : écrit `AWS_PROFILE=` vide dans
  `.env.agentcore` sous le fallback ambiant.
- **Scans non documentés** : `content_generator.py:452` (table sessions, convertible en
  Query), `dashboard_api.py:1444-1452` (scan + second scan complet en fallback).

---

## 12. Ordre d'exécution

1. **WP7 — commit de l'existant.** 35 fichiers modifiés non commités : seul risque de perte
   totale. Découpage : (a) retrait statut legacy + migration, (b) consolidation hebdo +
   prompts, (c) matcher et scoring PPG, (d) scripts, docs et spec.
   *Demander validation avant tout commit.*
2. **WP0** — entiers nus. Correctif mécanique, même classe de bug que l'origine du chantier,
   sur un chemin qui écrit en base. Avant tout le reste.
3. **WP4** — mensurations (prérequis de WP5).
4. **WP1 + WP2 + WP3** — un seul cycle de déploiement : les trois touchent un prompt, donc
   redéploiement des runtimes de toute façon.
5. **WP5a** — persistance de `strength_history` + backfill. **Bloquant pour WP5 et WP2b** :
   sans lui, le tonnage et l'outil du chat lisent du vide.
6. **WP5** — tonnage (consomme WP5a et WP4).
7. **WP2b** — outil muscu du chat. Le retrait de la promesse de prompt peut se faire
   dès l'étape 4, sans attendre l'outil.
8. **WP6** — outillage, aucun déploiement.
9. Régression prompt live (`run_prompt_regression.py`, ~0,20 $, venv 3.11) — non relancée
   depuis les derniers changements de prompt, à faire dans tous les cas.
10. Validation réelle : `19596127525` (gym — ne doit pas fermer la PPG, décompte muscu = 1,
   tonnage cohérent) et question chat « qu'est-ce qu'il me reste cette semaine ? » (attendu :
   4, avec titres).

**Rappels d'environnement** : jamais `--profile` (credentials par variables
d'environnement uniquement, le fichier est vide) ; `cdk diff` avant chaque deploy (a déjà
évité l'effacement de `STRAVA_SUBSCRIPTION_ID`) ; stacks `StravaAIBoost-Content` et
`-Webhook` ; toute migration de données **avant** le code qui change une précédence de lecture.

---

## 13. Risques

| Risque | Mitigation |
|---|---|
| Les regex du vérificateur ratent des formulations | assumé : elles visent les motifs ayant menti en production ; la métrique dira s'il faut élargir |
| Faux positifs → régénérations inutiles | tolérances chiffrées, une seule repasse, jamais bloquant |
| Retrait de phrase (WP3) mutile le texte | ne retirer qu'une phrase porteuse d'un décompte, jamais un paragraphe ; testé sur les 5 cas réels |
| Miroirs chat (statut, iso_week, bucketing) qui dérivent | tests anti-dérive sur fixtures communes ; modèle déjà éprouvé. **Si un 4e miroir devient nécessaire, régler la contrainte de bundle plutôt que multiplier les miroirs** |
| Nouveau garde-fou oublié dans un des deux prompts | invariant 8, test anti-dérive |
| Tonnage faussé par une dérive de poids | `body_weight_kg_used` tracé dans chaque résultat |
| Surestimation silencieuse (pompes à 1.0, unilatéral doublé à tort) | coefficients dans une table explicite ; `unilateral: true` visible ; exercices ambigus exclus par défaut |
| Une capacité annoncée dans un prompt sans outil ni champ correspondant | audit croisé prompt↔outils : toute mention d'une donnée doit être traçable à un champ réellement retourné |
| Écriture de données qui échoue en silence | métrique dédiée ; le cas `strength_history` a échoué deux fois sans alerte |
| Une évolution change la couverture d'un champ sans relire le prompt | invariant 7 ; seul garde-fou possible à ce niveau, humain |

---

## 14. Décisions prises et restant ouvert

**Prises** : compter les deux côtés en unilatéral (expansion des séries) ; coefficient 1.0
pour les pompes (règle de l'athlète, réserve documentée) ; champs structurés plutôt que
parsing de prose ; amorçage du poids depuis Strava ; vérification post-génération plutôt que
sortie structurée ; retrait de la phrase fautive plutôt que publication d'un chiffre faux.

**Ouvert** : `Curl marteau` et `Fentes` sont-ils unilatéraux dans la pratique de l'athlète ;
convention de notation des unilatéraux (« par côté » supposé) ; basculer `Pompes` à 0.65 si
la comparabilité des tonnages devient prioritaire.

---

## 15. Incident du 2026-08-05 : 52 entrées écrasées par le backfill

**Ce qui s'est passé.** Après le passage à `sets_detail`, un `--replace` a réécrit les 64
entrées d'historique. 52 ont été stockées **vides**.

**Cause.** `maxTokens: 800` sur l'appel d'extraction. `sets_detail` émet un objet JSON par
série, soit environ 4x le volume de l'ancien schéma plat : la réponse était tronquée en plein
objet, `json.loads` échouait, et `_extract_strength_sets` renvoyait `[]` — ce qu'il fait par
conception pour ne jamais casser le pipeline. Correct pour une activité, faux pour un rejeu en
masse : un appel tronqué devient « cette séance n'avait aucun exercice ».

**Récupération.** Les descriptions brutes étaient conservées sur chaque entrée, donc la donnée
était reconstructible. `maxTokens` porté à 3000, puis rejeu complet.

**Ce qui a été durci, dans l'ordre où les défauts sont apparus.**
1. `maxTokens` dimensionné pour la pire séance réaliste, avec le pourquoi en commentaire.
2. Retry avec backoff sur extraction vide.
3. **Abandon** du `--replace` dès qu'une extraction échoue : c'est ce garde-fou qui a empêché
   le second écrasement.
4. Distinction entre « échec » et « rien à extraire » : la première version du garde-fou
   confondait les deux et refusait de rejouer 32 séances dont la description ne contient
   légitimement aucun chiffre (« les sensations reviennent petit à petit »). Un
   `_looks_quantified()` sur les motifs de séries tranche.

**Leçon transposable.** Une fonction best-effort qui avale ses erreurs est sûre en écriture
unitaire et dangereuse en rejeu de masse. Tout script de migration qui appelle une telle
fonction doit traiter le résultat vide comme un échec possible, et refuser d'écrire en cas de
doute plutôt que d'écrire une absence.
