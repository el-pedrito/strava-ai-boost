# Séances Campus vers l'Apple Watch (fichiers `.workout`)

Statut : plan validé (revue à deux modèles, 3 tours, Claude Opus 5.5 et GPT-5.6 Sol
READY 9/10), **pas implémenté**. Le comportement iPhone/Watch n'est pas supposé : il est
prouvé par le Gate 0 avant tout déploiement.

## But

Depuis le plan Campus, un bouton sur le site ajoute une séance à l'app Exercice de la
Watch, sans app iOS à écrire.

## Ce qui est établi

1. Le fichier `.workout` est celui que produit « Partager l'exercice » sur la Watch ou
   l'iPhone, et celui qu'encode `WorkoutKit.WorkoutPlan` (`dataRepresentation`,
   `init(from:)`, iOS 17 / watchOS 10).
2. Le format n'est pas documenté par Apple. C'est du protobuf simple, décodé par trois
   projets MIT indépendants : [DotnetWorkoutKit](https://github.com/changeforan/DotnetWorkoutKit),
   [dotworkout](https://github.com/javierferrersb/dotworkout) (20 exports réels
   ré-encodés à l'octet près) et [@bibixx/workoutkit](https://github.com/bibixx/workoutkit)
   (échantillons produits par le WorkoutKit Swift d'Apple, couverture iOS 26 / watchOS 26).
3. Import web documenté par dotworkout : Safari, téléchargements, toucher le fichier, il
   s'ouvre dans Exercice ; sinon Fichiers, Partager, Exercice.
4. Spike : un écrivain protobuf Python sans dépendance reconstruit **à l'octet près**
   4 fichiers faits par Apple : 3 exports réels de Watch (allure RANGE AVERAGE, allure
   RANGE CURRENT avec alerte FC sur l'échauffement, allure VALUE) et 1 fichier du CLI Swift
   d'Apple (HIIT, étapes nommées). 49 séances Campus réelles s'encodent ; 7 sorties
   représentatives se décodent avec un décodeur indépendant.
5. Un `.workout` arrive dans la liste des exercices personnalisés, **pas à une date**.
   La planification par date demande une app iOS native (`WorkoutScheduler`) : hors champ.
6. L'athlète enregistre aujourd'hui sur Apple Watch Ultra 2 : renfo en Strava
   `WeightTraining`, course en `Run`. Le pipeline reconnaît le PPG par `WeightTraining`
   et par les mots `campus`/`ppg` écrits par l'athlète lui-même.

## Conception

### A. Encodeur `lambda_functions/shared/workout_file.py`

Écrivain protobuf sans dépendance et builders typés : CustomWorkout, IntervalBlock,
IntervalStep (WORK / RECOVERY), WorkoutStep, objectifs TIME et OPEN, alerte d'allure RANGE
(CURRENT ou AVERAGE, borne basse = allure la plus lente). Conteneur : GUID=9, custom=11,
version=1000:1, format=1002:5, en constantes nommées avec un test anti-changement silencieux.
Pas de décodeur en production (tests seulement).

### B. Mapper `lambda_functions/shared/campus_workout.py`

Fonction pure `map_session(session, guid=None) -> MapResult {encodable, reason_code,
bytes?, summary?}`.

| Règle | Choix |
|---|---|
| Sport | `road` -> RUNNING extérieur ; `ppg` -> TRADITIONAL_STRENGTH_TRAINING intérieur ; autre -> `unsupported_sport` |
| Forme legacy | entrée plate avec `repeat > 1` -> `legacy_shape` (structure perdue, on ne devine pas) |
| Échauffement / retour au calme | seulement l'index 0 / le dernier index ; les autres deviennent des étapes WORK |
| Blocs | étapes plates consécutives -> 1 bloc x1 ; `block` -> bloc x clamp(repeat, 1, 100) ; `bad_repeat` sinon |
| Durées | `N sec`, `N min`, `M:SS min`, `N h`/`hour`/`hours` ; sinon objectif OPEN + métrique `WorkoutStepOpenFallback` |
| Alertes d'allure | seulement sur les étapes WORK >= 180 s d'une famille qualité ; RANGE CURRENT, `PACE_TOLERANCE = 0.025` ; courses (`Competition`, `low-priority-race`) en AVERAGE |
| Familles | normalisées (minuscules, sans accents, chiffres et ponctuation retirés, espaces fusionnés) ; qualité = {semi marathon, tempo, seuil, course, allure, marathon} ; sans alerte = {ef, lent, aerobie, rapide} ; inconnue -> pas d'alerte + métrique `WorkoutUnknownPaceFamily` |
| Noms d'étape | course « Semi Marathon 4:35 » ; renfo « <exercice> x<n> rép. », 32 caractères max avec table d'abréviations testée (« avec charge additionnelle » -> « lesté ») |
| Nom de l'exercice | « <titre> W<nn> » ; les mots `campus` et `ppg` sont retirés (le matcher ne doit rien changer) |
| Limites | > 30 étapes par bloc, total d'étapes ou octets au-delà de `MAX_TOTAL_STEPS_PER_WORKOUT` / `MAX_WORKOUT_BYTES` -> item non encodable |
| GUID | UUIDv4 neuf à chaque export (GUID fixe seulement dans les tests) |
| Résumé | une ligne tirée de la même structure (« WU 15' · 4x(9' Semi 4:35 + 2') · CD 5' ») |

### C. API `GET /plan/workouts` (Lambda DashboardAPI existante)

- Autorizer Cognito ; puis `custom:strava_id == CAMPUS_OWNER_STRAVA_ID` (nouvelle variable,
  depuis le contexte CDK `default_user_id`). Absent, vide, différent ou variable non posée
  -> 403. La branche n'utilise jamais `_get_user_id`.
- Le client Cognito reçoit des `write_attributes` explicites **sans** `custom:strava_id`
  (le flux OAuth le pose côté serveur par `admin_update_user_attributes`, le SPA ne modifie
  jamais d'attribut). `read_attributes` reste absent ou contient `custom:strava_id`.
  Assertion CDK sur les deux.
- Scan paginé (`LastEvaluatedKey`) sur `is_current_week OR is_future`, puis filtre
  `week_date >= lundi 00:00 UTC de la semaine ISO de la date de Paris` (encodage de la sync).
  Statut `effective_status(...) not in {DONE, SKIP}`. Tri `week_iso`, `training_index`
  numérique, `session_id`.
- Chaque séance est mappée dans un `try/except Exception` : un échec donne
  `encodable:false, reason_code:"internal"` + métrique `WorkoutMapFailed`, sans texte Campus
  dans les logs.
- Réponse `{workouts, count, truncated}` par `create_success_response`, en-têtes CORS +
  `Cache-Control: no-store`, y compris sur les erreurs de cette branche (try propre à la
  branche). Plafond 120 items et plafond d'octets de la réponse : au-delà, on garde les
  semaines les plus proches et `truncated:true`. Pas de cache module.
- Item : `session_id, week_iso, training_index, title, training_type, sport, duration_min`
  (= `expected_duration_min`), `summary, filename, encodable, reason_code, workout_b64?`.
  Nom de fichier `<semaine>-<index>-<slug>.workout`, ASCII, 60 caractères max.
- IAM inchangé. Nouvelle ressource et méthode API, test CDK de la route et de l'autorizer.

### D. Frontend

- `src/lib/downloadWorkout.ts` : base64 -> Uint8Array -> Blob `application/octet-stream`
  -> `<a download rel="noopener">` ajouté au DOM, clic synchrone, retrait et `revokeObjectURL`
  après 30 s.
- Page `/plan` par semaine, bouton « Ajouter à la Watch », items non encodables grisés avec
  leur raison, aide iPhone FR/EN (Safari -> téléchargements -> toucher ; sinon Fichiers ->
  Partager -> Exercice ; un nouveau téléchargement ajoute une entrée, supprimer l'ancienne).
- Flag `workoutExportEnabled` optionnel dans `AppConfig` et `config.json.example`, absent =
  désactivé : il masque l'entrée de nav, et `/plan` redirige vers `/`
  (`<Navigate to="/" replace />`). Les deux états sont testés. Barre du bas vérifiée à 375 px.

### E. Tests

- Les 4 fichiers Apple vendorisés en binaire dans `tests/fixtures/workout/` (README : dépôt,
  commit, générateur, SHA-256, licence MIT), reconstruits à l'octet près.
- Goldens du Gate 0 dans `tests/fixtures/workout/gate0/` : séances synthétiques de la même
  forme que les vraies, GUID fixes, `map_session(...) == golden`. Modifier un golden après le
  Gate 0 oblige à refaire au moins l'étape 2b du Gate 0 (commentaire en tête du test).
- Décodeur de test qui échoue sur tout champ inconnu : activité, lieu, objectifs, ordre des
  étapes, CURRENT vs AVERAGE, bornes ordonnées, noms UTF-8.
- API : 403 (absent, vide, mauvais propriétaire, variable absente), pagination, filtre de
  semaine (dimanche 23:30 Paris, lundi 00:30 Paris, en CET et en CEST), statuts, isolation
  par item, enveloppe, `no-store` sur 200 et 500.
- Frontend : octets exacts dans le Blob, MIME, nom, un clic, révocation différée, états
  vides / erreur / non encodable, flag, nav.
- Pas de `parametrize` ni de `.each` ; décomptes Python et frontend mis à jour dans les docs.

## Étapes et gates

1. **Code sans exposition** : A, B, module de téléchargement, goldens, sur `dev`. Pas de
   route, pas de nav, rien de déployé. CI verte.
2. **Gate 0, sur les appareils de l'athlète**, avec les fichiers produits par l'étape 1 et une
   page HTML d'un seul fichier qui embarque le module de téléchargement livré (config Vite
   séparée `vite.gate0.config.ts`, hors `npm run build`, empreinte SHA-256 notée).
   - Hébergement : bucket privé existant des audios, préfixe `gate0/`, `Content-Type:
     text/html; charset=utf-8`, `<meta name="apple-mobile-web-app-capable">` en ligne, URL
     présignée de 2 h. Vérifier avant que l'expiration réelle des identifiants couvre le test
     (`MaxSessionDuration` du rôle). Le bucket est versionné : supprimer chaque version
     ensuite, puis vérifier que l'URL ne répond plus.
   - a. Onglet Safari / écran d'accueil (vraiment en plein écran) / Chrome iOS : ça s'ouvre
     dans Exercice ? Noter iPhone, iOS, watchOS, unités, langue.
   - b. Sur la Watch : étapes, noms (accents, coupure), durées dont un `M:SS`, répétitions,
     plages d'allure, étapes OPEN utilisables avec des charges en main. **Bloquant.**
   - c. Identité : même fichier deux fois ; contenu modifié et même GUID ; même contenu et
     GUID neuf ; comment supprimer.
   - d. Faire une vraie séance Intensité et un vrai renfo depuis les fichiers. Relever dans
     Strava le nom, la description, `type`, `sport_type` ; les laps face à une course normale ;
     le score de match et sa source ; où et quand le mot `campus`/`ppg` a été écrit (titre ou
     description, avant ou après le 1er traitement, 1re passe ou dictée tardive) ; statut
     done ; historique de force écrit ; gardes passées ; au plus 2 alertes parasites par bloc
     de 9' à l'allure cible. Contre-test : une muscu hors plan sans le mot ne ferme pas le PPG.
   - Go si a (au moins l'onglet Safari), b et d passent. « Go avec aide » si seul l'onglet
     Safari marche. Si le renfo n'arrive pas en `WeightTraining`, stop. Un échec de match dû
     seulement à l'ordre d'édition du texte est classé « workflow existant », pas « feature ».
   - Résultats dans un artefact : commit, fixtures, empreintes, GUID, appareils, champs
     Strava bruts, scores.
3. **Code exposé, flag éteint** : C, page, flag. Déployé. Vérifier séparément : refus
   anonyme par API Gateway ; refus par le handler d'un jeton sans claim ou avec un autre ;
   200 pour le propriétaire.
4. **Gate 1** : mettre `workoutExportEnabled: true` dans le `config.json` du bucket du site,
   `create-invalidation --paths /config.json`, relancer l'app depuis l'écran d'accueil.
   Importer une séance depuis la vraie page, la faire, comparer l'enregistrement au plan.
   Retour arrière : flag à `false`, même invalidation.

## Risques restants

- Format non documenté : une mise à jour iOS/watchOS peut le casser. Refaire le Gate 0
  (au moins 2a et 2b) après chaque version majeure.
- Les seuils d'alerte se règlent sur le terrain : une constante, un test.
- Endpoint mono-athlète par construction : la table Campus n'a pas de clé utilisateur.
