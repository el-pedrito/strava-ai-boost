# Jeu « Monde » : avancer sur des parcours de course célèbres en suivant le plan

Statut : plan validé (revue à deux modèles, Claude Opus 5.5 READY 9/10, GPT-5.6 Sol READY 9/10). Pas implémenté.
strava-ai-boost, un seul athlète, dépôt PUBLIC.

## Le but

Une page « Monde » dans le site. Chaque activité gagne des points, qui font avancer un pion sur
une suite de parcours connus (Paris 42 km, Berlin, Boston, Durban–Pietermaritzburg, Tour du
Mont-Blanc). Pas de sport, pas de points. Différence avec The Conqueror (km = km, saisie manuelle
acceptée) et Run An Empire (tracé dans leur app) : on récompense le SUIVI DU PLAN Campus, pas le
volume.


## Principes non négociables

1. Ne rien casser (câblage attendu dans le `cdk diff` : nouveau stack, `app.py`, constructeur
   `ApiGatewayStack`, export de l'ARN de `GameStateAPI`, `Lambda::Permission`, méthode `OPTIONS`
   auto ; aucun nouvel export du stack Core). Pipeline inchangé : ni code, ni asset, ni droits. Le jeu LIT les tables
   existantes et n'écrit que dans la sienne. Seule modification d'un stack existant : la ressource
   `/game/state` de l'API. Preuve : `cdk diff` = nouveau stack + cette route + son déploiement.
2. Code isolé dans `game_functions/` (asset séparé, aucun import de `lambda_functions/`).
   `effective_status`, `paris_date`, `iso_week_label`, `is_owner` et les en-têtes CORS de `shared/responses.py`
   repris avec un test de parité contre les originaux. Tests sous `tests/unit` (seul dossier
   collecté par la CI avec `tests/regression`).
3. Données brutes en ajout seul ; tout le dérivé se recalcule. Changer une règle = recalcul.
4. Volume plafonné partout ; le hors plan rapporte peu.
5. Anti-triche fermé par défaut.
6. Onglet derrière `gameEnabled` dans `config.json` (front seulement ; l'API est en ligne dès le
   deploy mais réservée au propriétaire). Allumer = édition S3 manuelle + invalidation CloudFront de `/config.json`, commande fournie.
7. Porte propriétaire comme `/plan/workouts` (`custom:strava_id` == `CAMPUS_OWNER_STRAVA_ID`,
   sinon 403, avant toute lecture), `Cache-Control: no-store` partout (y compris `warming_up`),
   test CDK : méthode en COGNITO.

## A. Contrat de données (lecture seule)

Propriétaire = `default_user_id` du contexte CDK. Vide -> la Lambda n'écrit rien.

Activities : Query `UserActivitiesIndex` (user_id = propriétaire, `created_at >= saison - 7 j`),
paginée, puis filtre strict `saison <= start_date_local <= maintenant`. `start_date_local` est déjà
l'heure murale locale (Strava y met un `Z` trompeur) : lue telle quelle, jamais convertie ;
sa semaine vient de `iso_week_label`, comme le matcher. `maintenant` = heure de Paris (une vieille activité rejouée a un `created_at` récent), retriée par `start_date_local`. Attributs : `activity_id, updated_at, distance,
moving_time, total_elevation_gain, start_latitude, activity_data_json`. JSON parsé puis jeté ;
gardés : `sport_type`, `type`, `manual`, `has_heartrate`, `start_date_local`. La polyline n'est
jamais copiée. Nombres via une seule `_num`.

Campus-coaching-sessions : lignes `week-YYYY-Www` / `{weekDate}_{idx}` ; `athlete-context` exclu.

## B. Stack `StravaAIBoost-Game`

- Table `strava-ai-boost-game` (PK `pk`, SK `sk`, PITR, RETAIN, chiffrée).
- Lambda `GameSnapshot` (asset `game_functions/`, arm64, concurrence réservée 1, timeout 5 min),
  `cron(30 * * * ? *)` (la sync Campus tourne à la minute 0). Alarmes sur erreurs et sur durée. Lecture page par
  page ; le blob JSON (qui contient la polyline) n'est jamais journalisé. `completed_at` n'est pas
  copié dans `OBS` : il est toujours écrit avec `local_status`, qui suffit. SK au format
  explicite `%Y-%m-%dT%H:%M:%S.%fZ` ; suffixes de `session_id` comparés comme nombres.
- Lambda `GameStateAPI`, même asset, sur `GET /game/state`.
- IAM `GameSnapshot` : Query sur le GSI activities, Query/Scan campus, `PutItem` + `GetItem` +
  `Query` sur la table game. Pas de `DeleteItem`, pas d'`UpdateItem`.
- IAM `GameStateAPI` : `GetItem` table game, `dynamodb:LeadingKeys = ["STATE"]`. Rien d'autre.
- Tests CDK sur ces droits.

### Items

| Item | Clé | Contenu | Écriture |
|---|---|---|---|
| Observation | `OBS` / `<semaine>#<observé_le ISO UTC, largeur fixe>` | toutes les lignes de la semaine : `session_id`, `title`, `training_type`, `sport`, `expected_duration_min`, `expected_distance_km`, `local_status`, `provider_status`, `matched_activity_id` ; empreinte SHA-256 de ces colonnes triées | seulement si la semaine a au moins 1 ligne ET l'empreinte diffère de la dernière observation ; `attribute_not_exists` ; jamais modifiée. Semaines énumérées depuis la table Campus (jamais depuis la saison) : une semaine absente, ou un run sans aucune ligne (accès Campus perdu), n'écrit rien |
| État | `STATE` / `current` | état dérivé, `RULES_VERSION`, calculé le | réécrit à chaque run |

Pas de description ni de texte du coach dans `OBS`. Taille : ~7 lignes courtes par observation.

Départ : l'étape 1 livre seulement l'écriture des observations (code minimal, testé à fond avant
deploy) pour arrêter la perte : chaque sync efface une vieille semaine. Saison = lundi de la plus
ancienne semaine observée (1re SK de la partition `OBS`). La dérivation lit TOUJOURS la partition `OBS` entière, jamais la liste des semaines de Campus. Rattrapage optionnel sur go de Pierre : restauration PITR de la table
Campus dans une table temporaire, un script en tire des `OBS` dont la SK porte l'heure du POINT DE RESTAURATION T (pas l'heure du
script ; test), et SEULEMENT pour les semaines déjà closes à T (test : semaine close entre T et
le déploiement, observation live avec une ligne de moins -> le live gagne), puis la
table temporaire est supprimée.

Angles morts documentés : activité supprimée sur Strava reste comptée (le webhook ignore
`delete`) ; amélioration en pause ou module `campus_coach` coupé = pas de points plan ; GPX
importé = `manual` faux, accepté ; si Campus permute deux séances après un match, la ligne garde
le match sous un autre titre (le contrôle de sport ci-dessous limite le cas).

## C. Dérivation et barème (`game_functions/game_points.py`, pur)

Clôture d'une semaine = lundi suivant 00:00 heure de Paris (`paris_date`). On parcourt les
observations de la semaine dans l'ordre de la SK ; chacune est acceptée, sauf une observation
prise APRÈS la clôture qui a moins de lignes que la dernière observation prise AVANT la clôture
(Campus qui rogne ou réindexe une vieille semaine). Si aucune observation n'est d'avant la
clôture (semaine vue pour la 1re fois au déploiement ou par rattrapage), la base est la 1re
observation de la semaine. Vérité d'une semaine = la dernière
observation NON VIDE acceptée, et elle seule, pour les activités comme
pour le bonus. Une activité est « matchée » seulement si cette observation-là la porte. Si Campus
a retiré ou re-rattaché la ligne entre-temps, l'ancien lien ne compte plus (pas de repli sur une
observation plus ancienne : un créneau ne peut payer qu'une fois). Une semaine sortie de la
fenêtre Campus n'a plus de nouvelle observation, donc sa dernière reste la vérité pour toujours.

Si A est portée par plusieurs lignes d'une observation : on retient celle dont le `sport` concorde
avec l'activité, puis la durée prévue la plus proche de `moving_time`, puis le plus petit
`session_id`. Les autres lignes sont traitées comme non faites.

Éligibilité : `sport_type` (sinon `type`) dans {Run, TrailRun, VirtualRun, WeightTraining} ;
`manual` explicitement faux ; Run/TrailRun : `start_latitude` ou FC ; VirtualRun et
WeightTraining : `has_heartrate` vrai ; `moving_time` > 0 (sinon `no_duration`, testé avec 0,
"0", None, absent) ; course : vitesse moyenne (distance / `moving_time`) <= 6 m/s.
Toute exception sur une activité -> 0 point, raison `bad_data`, métrique `GameBadData` : le run
continue et `STATE` est écrit.
Sinon 0 point au total, exclue du bonus, raison codée (`speed_outlier` pour la vitesse).
Sélection globale canonique, faite AVANT tout score et tout bonus : pour chaque activité, on
liste ses occurrences dans les vérités de toutes les semaines. S'il y en a une dans SA semaine ISO
(`start_date_local`), c'est elle (puis départage intra-observation ci-dessus). Sinon : raison
`other_week`, volume hors plan dans sa semaine. Toute occurrence non retenue rend sa ligne « non
faite » pour le bonus de la semaine qui la porte. Égalité d'ordre chronologique tranchée par
`activity_id`.

« Séance du plan faite » (seul prédicat) : ligne retenue, semaine ISO de `start_date_local` ==
semaine de la ligne, la ligne concorde avec l'activité, avec la MÊME règle que le matcher
(`modules_processing.py` l. 389-390) : séance de renfo = titre contenant `renforcement` ou `ppg`
<-> WeightTraining ; autre séance <-> course (Run, TrailRun, VirtualRun). Règle un peu plus stricte que le matcher (qui compare `type` en minuscules à `virtual run`) : test
qui couvre VirtualRun rattaché à une ligne renfo -> `sport_mismatch` ;
durée prévue > 0, `moving_time` (s) >= 0,5 × 60 × durée prévue (min).

| Cas (un seul par activité) | Points |
|---|---|
| Séance du plan faite | 30 + volume plan |
| Match mais prédicat faux | volume hors plan, raison codée |
| Pas de match | volume hors plan |

Volume (courses seulement, entier inférieur par activité) : 1/km ; D+ 1/100 m plafonné à 10 ;
VirtualRun D+ = 0. Plan : km × min(1, 1,25 × durée prévue / durée réelle), D+ inclus avec son plafond,
puis plafond 1,25 × `expected_distance_km` si > 0. Hors plan : km + D+ plafonnés ensemble à 15
par semaine ISO, dans l'ordre chronologique.

Bonus semaine +40, calculé dans la dernière observation de la semaine : semaine terminée (heure
de Paris), au moins 3 lignes non `skip`, au plus 1 `skip`, chaque ligne non `skip` portée par une
activité distincte qui satisfait le prédicat. Une semaine encore visible peut gagner ou perdre ce
bonus à l'observation suivante ; c'est voulu et affiché « en cours » tant que la semaine est
dans la fenêtre Campus.

Raisons : énumération fermée (`plan_done, off_plan, short_match, other_week, sport_mismatch,
no_planned_duration, no_duration, bad_data, manual, no_signal, not_eligible_type, speed_outlier, cap_week`).

## D. Le monde

`game_functions/game_world.json` validé par schéma. Paris 42 km, Berlin 42 km, Boston 42 km,
Durban–Pietermaritzburg 90 km, Tour du Mont-Blanc ~170 km. Noms géographiques ; aucune marque,
logo, GPX, image tierce ; cartes postales factuelles. Coûts au backtest (~3 semaines de plan
suivi pour Paris, ~3 mois pour le TMB). Fin de catalogue : « tout fini », le total continue.

`STATE` : total, parcours, fraction, prochaine étape, cartes, points de la semaine, 10 dernières
activités `{date, sport, points, raison}`. Test : aucune coordonnée, polyline, nom ou texte.

## E. Page `/monde`

`AppConfig.gameEnabled` + repli Vite + `config.json.example`, helper strict, nav, route lazy +
gate, client typé, traductions, tests flag on/off et `warming_up`.

## F. Étapes

1. Écriture des observations seule. Tests avant deploy : empreinte stable à l'ordre des lignes,
   pas d'écriture si inchangé, pas d'écriture à 0 ligne, écriture conditionnelle, propriétaire vide, aucune description,
   droits IAM sans delete/update. Deploy. Preuve : `cdk diff` limité, items `OBS` présents,
   alarmes à 0.
2. Dérivation + barème + catalogue + tests (réordonnancement, suppression de ligne, double ligne,
   deux séances identiques, rebind A->B sur un créneau entre O1 et O2 (payé une fois), semaine supprimée de Campus puis run suivant, par le vrai chemin de lecture (Query `OBS`) : points et bonus inchangés, run sans ligne Campus (rien écrit), vieille activité rejouée (0 point), date future, autre semaine, sport discordant, prévu absent, vitesse aberrante,
   nombres en chaîne, JSON cassé, parité, bonus qui change à l'observation suivante, faux Run à
   > 6 m/s rattaché à une EF (0 point, pas de créneau bonus), semaine qui perd une ligne en cours de
   semaine puis clôture (points et bonus gardés), semaine close qui rétrécit après clôture (vérité
   inchangée, pas de faux +40), même activité dans sa semaine ET dans une autre, dans les deux
   ordres de lecture (un seul cas, bonus de l'autre semaine non crédité), SK du
   rattrapage PITR, run du dimanche 23:30 dans la bonne semaine, semaine vue 1re fois après
   clôture puis ligne todo retirée (pas de faux +40), `moving_time` nul ou absent, exception
   sur une activité (le run écrit quand même `STATE`). Backtest lecture seule -> coûts et taux de chaque raison. Gate avant les coûts : mesurer sur
   les vraies activités la présence de `manual` et de `has_heartrate` (les fixtures du dépôt
   n'ont pas toujours ces champs ; la renfo peut n'avoir que `average_heartrate`). Si un champ
   manque souvent, on définit un repli explicite (ex. FC = `has_heartrate` ou `average_heartrate`
   > 0) avant d'aller plus loin ; si
   `no_planned_duration` dépasse 10 % des séances, on rouvre la règle avant de fixer les coûts.
3. `STATE` + `GameStateAPI` + route + tests CDK. Deploy. Preuve : 401, 403 autre compte,
   `no-store`, 200 pour Pierre.
4. Page `/monde`, publication du site, flag allumé par Pierre.

## Hors v1

Bonus EF, intervalles à l'allure, fantôme, carte des rues, mention dans le post ou le coach.
