# Design spec — Chantier court terme (muscu, Coach Trends, anomalie santé, déautorisation)

**Statut :** spec (2026-07-16) — recherche + faisabilité faites, décisions prises, implémentation à valider.
**Méthode :** doc-first (changelog Strava + API reference + Intervals.icu) → challenge → décision par item.

Ce doc couvre les 4 items « court terme » de la [ROADMAP](../ROADMAP.md). Il corrige
une hypothèse fausse (les sets Strava ne sont **pas** lisibles via l'API) et acte
le pivot associé.

---

## Résumé exécutif des décisions

| # | Item | Faisabilité | Décision |
|---|------|-------------|----------|
| 1 | Alimenter `strength_history` via l'API Strava (sets FIT) | ❌ **Bloqué** côté lecture | Pivot : **parser structuré des descriptions** que l'athlète écrit déjà |
| 2 | Coach Trends : graphiques progression muscu | ✅ dépend de #1 (pivot) | Charts par exercice, alimentés par le parser #1 |
| 3 | Détection d'anomalie santé (déterministe) | ✅ données déjà présentes | Règle sur trends Intervals.icu + banner Dashboard + contexte coach |
| 4 | Endpoint de déautorisation Strava | ✅ **confirmé** (changelog 1 juin 2026) | Flow « Déconnecter Strava » (⚠️ supprime les tokens) |

---

## Item 1 — Sets structurés muscu : l'API Strava ne les expose PAS en lecture

### Ce que dit la doc (vérifié le 2026-07-16)

Changelog Strava (`developers.strava.com/docs/changelog`) :

> **21 mai 2026** — Addition of `set` message support for FIT file **uploads**.
> Strava now **ingests** set data (exercise type, repetitions, weight, duration,
> start time) from FIT files. Introduction of **JSON upload** format, limited to
> weight training activities.

**Analyse.** Ces deux ajouts concernent exclusivement le chemin **écriture / upload**
(FIT + JSON entrants). Les partenaires (Fitbod, etc.) *poussent* les sets dans
Strava ; l'app Strava les affiche. **Rien** dans le changelog ni dans le modèle
`DetailedActivity` (référence API) n'ajoute de champ `sets`/`exercises` en
**lecture** sur `GET /activities/{id}`. Le dernier champ ajouté à
`DetailedActivity` reste ancien (device_name, laps, pace zones…).

**Conclusion.** On ne peut **pas** récupérer les sets structurés que l'athlète (ou
un partenaire) enregistre dans Strava via l'API publique. L'hypothèse initiale de
la roadmap (« lire ces données via l'API pour alimenter `strength_history` ») est
**infirmée**. À revérifier si Strava publie un champ de lecture (surveiller le
changelog). Test live impossible actuellement : l'app Strava est `Inactive` (pas
d'abonnement payant) → tout appel renvoie 403.

### Pivot — parser structuré des descriptions

L'athlète **continue d'écrire ses séances en commentaire** (choix explicite). Le
coach conversationnel lit déjà ces descriptions (tool `query_activities`, ajouté).
Le gain manquant est la **structuration** pour les graphiques de progression.

État actuel (`content_generator._track_strength_history`) : à chaque
`WeightTraining`, la description brute (≤1000 car.) est append dans
`user_preferences.strength_history.entries` sous forme `{date, activity_id,
duration_min, description}`. **Aucune structuration** — le LLM interprète le texte.

**Proposition.** Ajouter un parser déterministe best-effort qui extrait des lignes
type `DC 4x8 @80kg`, `Tractions 4x10`, `Squat 5x5 100kg` en
`{exercise, sets, reps, weight_kg}`, stocké à côté de la description brute (jamais
à la place — la description reste la source de vérité). Grammaire tolérante :

```
<exercice> <sets>x<reps> [@]<poids>(kg)?      → DC 4x8 @80kg
<exercice> <sets>x<reps>                       → Tractions 4x10  (poids du corps)
<exercice> <poids>kg x<reps> x<sets>           → variantes tolérées
```

- Normalisation des alias d'exercice (DC/développé couché, tractions/pull-ups…),
  réutiliser le principe des `_TYPE_ALIASES` déjà en place côté coach_chat.
- Parser **best-effort** : si une ligne ne matche pas, on l'ignore (pas d'échec) —
  la description reste lisible par le coach LLM.
- Champ ajouté : `entry['parsed_sets'] = [{exercise, sets, reps, weight_kg}]`.
- Idempotent (déjà géré : skip si `activity_id` déjà présent).

**Risques.** Descriptions en texte libre très variables → parser ne capturera pas
tout. Acceptable : c'est additif, la description brute reste. Pas de régression si
`parsed_sets == []`.

**Effort.** ~½ journée (parser + tests unitaires sur un corpus de descriptions
réelles) + redéploiement content stack.

---

## Item 2 — Coach Trends : graphiques de progression muscu

**État actuel** (`CoachPage.tsx`, onglet Trends) : section « Historique
Musculation » qui **liste** les descriptions brutes (date + texte) avec la note
placeholder « les graphiques de progression apparaîtront après 3+ séances ». Les
charts sont **promis mais pas implémentés**, faute de données structurées.

**Proposition (dépend de #1).** Une fois `parsed_sets` disponible :

1. Backend `/coach/summary` : agréger `strength_history` en séries par exercice —
   `{exercise: [{date, top_weight_kg, total_volume_kg}]}` (top set + volume =
   Σ sets×reps×poids). Exposer sous `trends.strength_progression`.
2. Frontend : dans l'onglet Trends, remplacer/compléter la liste brute par un
   `LineChart` recharts (même pattern que pace/EF) : sélecteur d'exercice (top 3–5
   par fréquence) + courbe charge max ou volume dans le temps. Garder la liste
   brute en repli si `parsed_sets` vide.
3. Insight texte auto (même pattern que `volumeInsight`/`efInsight`) : « +5 kg au
   DC sur 4 semaines », « volume muscu stable ».

**Risque.** Peu de points au début (parser best-effort) → afficher le fallback
liste tant que < 3 points structurés par exercice.

**Effort.** ~1 journée (agrégation backend + chart frontend + i18n FR/EN + tests).

---

## Item 3 — Détection d'anomalie santé (déterministe)

**Données déjà disponibles.** `activity_fetcher._compute_wellness_trends` calcule
déjà, sur 30 j de wellness Intervals.icu : `resting_hr`, `hrv`, `vo2max`, `ctl`,
`sleep_duration`, `sleep_quality`, chacun avec `current`, `avg_30d`, `delta_7d`,
`direction`. Le coach « now » affiche déjà une carte récupération
(form/vo2max/resting_hr/sleep + deltas 7 j). **Aucune nouvelle intégration
externe** — pur calcul déterministe sur l'existant.

**Proposition.** Fonction pure `detect_health_anomalies(trends) -> list[Anomaly]`
avec des règles seuils explicites et documentées, ex. :

| Règle | Condition | Sévérité | Message |
|-------|-----------|----------|---------|
| Sous-récupération | `resting_hr.delta_7d ≥ +5` **ET** `hrv.delta_7d ≤ -10%` | warning | « FC repos ↑ et HRV ↓ sur 7 j — signes de fatigue, envisage du repos » |
| FC repos élevée | `resting_hr.delta_7d ≥ +7` | info | « FC repos +N bpm sur 7 j » |
| Sommeil en baisse | `sleep_duration.delta_7d ≤ -45 min` | info | « Sommeil −N min/nuit sur 7 j » |
| Forme dégradée | `form (TSB) < -20` | warning | « Forme très négative — surcharge, prudence » |

- Seuils centralisés en constantes (faciles à ajuster, testables).
- Sortie : `[{rule_id, severity, message_key, values}]` (i18n via clés).
- **Surfaces** (V1, sans push — pas d'infra notif) :
  - Banner/card sur le **Dashboard** (via `/dashboard` ou `/coach/summary`).
  - **Injection dans le contexte coach** (`shared/coach_context.py`) : le coach
    mentionne l'anomalie s'il y en a une.
- **Garde-fous** : ne rien afficher si Intervals.icu désactivé ou < N points de
  données (`data_points`), pour éviter les faux positifs sur données partielles.

**Risque.** Faux positifs si peu de données → garde sur `data_points ≥ 3`.
Déterministe, testable à 100 %, additif (aucune régression possible).

**Effort.** ~1 journée (fonction + seuils + tests exhaustifs + expo API + banner
frontend + injection contexte coach).

---

## Item 4 — Endpoint de déautorisation Strava

**Confirmé** (changelog 1 juin 2026) : *« Introduction of new deauthorization
endpoint »*. Endpoint Strava : `POST https://www.strava.com/oauth/deauthorize`
avec le `access_token` (révoque l'accès de notre app à l'athlète).

**Proposition.** Flow « Déconnecter Strava » :

1. Frontend (Configuration) : bouton « Déconnecter Strava » + **dialog de
   confirmation** (action destructive).
2. API Gateway (Cognito-authed) : `POST /strava/disconnect` → Lambda qui :
   - récupère l'`access_token` courant (refresh si besoin) ;
   - `POST /oauth/deauthorize` côté Strava ;
   - **efface** les tokens dans Secrets Manager (`STRAVA_OAUTH_SECRET`) ou les
     remet à un état vide + `strava_connected=false` dans user_config ;
   - idempotent : si déjà déconnecté / token invalide, renvoyer succès.
3. Webhook de déautorisation Strava (déjà supporté depuis 2018) : gérer aussi
   l'événement `updates.authorized=false` entrant pour nettoyer côté nous si
   l'athlète révoque depuis Strava.

**⚠️ Risque — moyen/élevé.** Supprime des credentials (tokens OAuth). Garde-fous :
dialog de confirmation explicite, opération idempotente, log d'audit, **pas** de
suppression des données d'activités (seulement les tokens + flag). Réversible via
un nouveau flow OAuth « Connect with Strava ».
**Test live impossible** actuellement (app Inactive) → implémenter + tester en
unitaire (mock Strava), valider le live quand l'abonnement sera actif.

**Effort.** ~½ journée (Lambda + route API + bouton/dialog frontend + tests).

---

## Séquencement recommandé

1. **Item 3 (anomalie santé)** — additif, données présentes, zéro dépendance, zéro
   régression possible. Bon premier pas.
2. **Item 1 (parser muscu)** — débloque #2 ; touche le pipeline content (tests).
3. **Item 2 (charts muscu)** — dépend de #1 ; frontend + agrégation.
4. **Item 4 (déautorisation)** — bien cadré mais destructif (tokens) et non
   testable live pour l'instant ; à faire en dernier, avec confirmation.

**Points de décision à valider avant implémentation :**
- Item 1 : confirmer le pivot (parser descriptions) puisque l'API ne fournit pas
  les sets. Parser **déterministe** (proposé) vs extraction LLM (plus robuste au
  texte libre mais coût/latence + non déterministe).
- Item 4 : valider la stratégie de nettoyage des tokens (effacement vs état vide)
  et le fait qu'on ne supprime pas les données d'activités.
