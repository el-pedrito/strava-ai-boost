# Ressenti de séance (RPE) saisi depuis une notif (plan minimal, non implémenté)

Décision de Pierre (17/10) : strict minimum. Les plans v1 à v8 (versions,
ressaisie, republication) sont abandonnés. L'attente d'1 h est portée par
Step Functions (callback `waitForTaskToken`) : pas de balayeur, pas de
Scheduler, pas de statut `queued`.

Révision 2 (17/10 soir) : intègre la relecture Opus + GPT
(`/tmp/push-port/rpe9-*.md`, 6/10 chacun) : 5 bloquants et les points
« à corriger ».

Révision 3 : intègre la relecture suivante (`rpe10-*.md`, 8/10 READY chacun) :
Choice avant `TransformInput`, report depuis la fermeture, écriture du flag,
client PushSend borné, IAM `Resource: "*"`, redrive, route sous
`/activities/{activityId}`, métrique `expired`, nettoyage du jeton.

## Le flux

```
webhook create
  -> processeur : attente Enduraw 2 min si activé (inchangé)
  -> processeur calcule wait_for_input, start_execution (nom déterministe)
  -> Choice ShouldWaitForInput (lit l'entrée brute, avant TransformInput)
       non -> TransformInput
       oui -> WaitForAthleteInput (waitForTaskToken, timeout 1 h)
                Lambda input_wait : ouvre la fenêtre, envoie la notif
                l'athlète envoie RPE + résumé -> API -> SendTaskSuccess
                rien en 1 h / panne -> catch -> on continue
              -> TransformInput
  -> TransformInput (inchangé) -> FetchActivityData
     (ferme la fenêtre, relit Strava, lit la saisie)
  -> contenu + coach -> assemblage -> mise à jour Strava (inchangé)
```

Une seule exécution par activité : c'est elle qui attend. Pas de ressaisie,
pas de reprocessing déclenché par la saisie. La dictée tardive et la boucle de
feedback restent comme aujourd'hui.

## Décisions

| # | Décision |
|---|---|
| D1 | La saisie va aux agents, jamais telle quelle sur Strava |
| D2 | RPE et résumé peuvent apparaître dans le post public |
| D3 | Une seule saisie par activité ; fenêtre fermée -> 409 |
| D4 | Sans saisie : le run part tout seul au bout d'1 h (timeout du Task) |
| D5 | Push éteint, `sent == 0` ou erreur de `input_wait` : le run part tout de suite |
| D6 | Attente Enduraw : comme aujourd'hui, avant `start_execution` |
| D7 | RPE et `suffer_score` donnés au coach séparément, jamais combinés |
| D8 | Échec ouvert : un problème dans l'attente ne perd jamais le run |
| D9 | Le résumé est un champ à part (`athlete_summary`), pas collé au texte d'origine : il reste isolé dans le prompt, ne se duplique pas, et le texte Enduraw n'est jamais touché |

## Ce qu'on code

### 1. Flag (`athlete_input_enabled`)

- Stocké comme module : `modules_config.athlete_input.enabled` (défaut
  `False`).
- Écriture : `athlete_input` ajouté à l'allowlist de `configure_module`
  (`configuration_api.py:667`, aujourd'hui `campus_coach`, `enduraw`,
  `intervals_icu`). Toggle « Ressenti après séance » dans Préférences, à côté
  de la carte Notifications (qui, elle, ne gère que l'abonnement appareil).
- Lecture : `fetch_user_configuration` (`activity_processor.py:612-665`) le
  renvoie avec les autres modules.

### 2. Processeur (`activity_processor.py`)

- Calcule un seul booléen, toujours écrit dans l'entrée d'exécution :
  `wait_for_input = athlete_input_enabled and aspect_type == "create"`.
  `aspect_type` est lu au bon endroit : le message SQS est imbriqué
  (`$.webhook_data.webhook_data.aspect_type`, voir `:183` et `:547`).
  Une dictée tardive (`update`) ne réattend donc jamais.
- `should_skip_processing` ignore déjà tout webhook tant que le statut est
  `processing` (`:244-247`, posé avant `start_execution`) : un `update` Strava
  pendant l'heure ne lance rien. Aucun changement.

### 3. State machine (`stacks/content_generation_stack.py`)

- `ShouldWaitForInput` (Choice) devient le premier état, AVANT
  `TransformInput` : il lit l'entrée brute.
  `And(IsPresent("$.wait_for_input"), BooleanEquals("$.wait_for_input", true))`
  -> attente ; sinon `TransformInput`. `TransformInput` (`:444-452`) reste
  inchangé : il ne référence jamais `wait_for_input`, donc un champ absent ne
  lève pas `States.Runtime`. Raison : `app.py:69` déploie la state machine
  avant le processeur ; pendant cette fenêtre, l'ancien processeur lance des
  exécutions sans le champ.
- Le processeur, seul appelant de `start_execution` (`:554`), écrit toujours
  `wait_for_input` (booléen) une fois déployé.
- `WaitForAthleteInput` : `LambdaInvoke`,
  `integration_pattern=IntegrationPattern.WAIT_FOR_TASK_TOKEN`, payload
  `{activity_id, user_id, task_token: JsonPath.task_token}`,
  `task_timeout=Timeout.duration(Duration.hours(1))`,
  `result_path=JsonPath.DISCARD`, `retry_on_service_exceptions=False` (un
  retry créerait un nouveau jeton et fermerait la fenêtre).
- Un seul catcher : `add_catch(TransformInput, errors=["States.ALL"],
  result_path="$.input_wait_error")`. `States.ALL` couvre `States.Timeout` et
  doit être seul dans sa liste (règle ASL). Succès -> `TransformInput`.
- `definition = should_wait_for_input` (le Choice est l'état de départ).
- `TransformInput` ne recopie pas `input_wait_error` : le comptage `expired`
  se fait dans le fetcher, d'après l'état avant fermeture (§7).
- Timeout global : `Duration.minutes(30)` -> `Duration.minutes(120)`
  (1 h d'attente + contenu jusqu'à 2 × 11 min + coach + mise à jour, avec marge).

Standard workflow (déjà le cas) : pas de coût pour la durée d'attente, on paie
les transitions. Logs `include_execution_data=False` (déjà le cas) : le
jeton n'est pas dans les logs Step Functions.

### 4. Helper push synchrone (branche web push)

`notify_activity_enriched` (`push_notify.py:53-63`) est asynchrone
(`InvocationType="Event"`), sans `url`, et ne voit jamais `sent`. Nouveau
helper :

```python
def notify_input_request(user_id, activity_id, title, body, url) -> int
```

- Appelle PushSend en `RequestResponse`, passe `url`, `tag="input-<id>"`,
  `ttl=3600`, renvoie `payload["sent"]`.
- Toute erreur -> `0`.
- PushSend accepte déjà `url` (`push_send.py:74,87`) et renvoie `sent`
  (`:124`). Si `tag`/`ttl` ne sont pas acceptés, les ajouter en options.
- Client boto3 dédié : `Config(read_timeout=95, connect_timeout=5,
  retries={"total_max_attempts": 1})`. PushSend a un timeout Lambda de 90 s
  (`push_stack.py:223`) ; sans `total_max_attempts=1`, un timeout de lecture
  relancerait PushSend et doublerait la notif.

### 5. Lambda `input_wait` (nouvelle, `lambda_functions/athlete_input/`)

1. `UpdateItem` : `SET athlete_input_state = :awaiting, input_task_token = :t,
   input_deadline_at = :d, user_id = :u`, condition
   `attribute_not_exists(athlete_input_state)`. Le `user_id` vient de
   l'entrée d'exécution (source sûre) : la ligne activité n'a pas encore de
   propriétaire avant le fetcher, l'API en a besoin pour le contrôle.
2. Condition échouée (fenêtre déjà ouverte ou fermée, exécution rejouée) ->
   `SendTaskSuccess` tout de suite (D3).
3. `notify_input_request(..., title="Nouvelle séance", body="Ton ressenti ?",
   url="/activities/<id>/feedback")`. Le jeton n'est jamais dans la notif.
4. `sent == 0` ou exception -> `SET athlete_input_state = :closed REMOVE
   input_task_token`, `SendTaskSuccess` tout de suite (D5). Le `GET` renvoie
   alors `closed` sans attendre le fetcher.
5. `user_id` est écrit en `str(user_id)` (même type que `webhook_handler.py:323`
   et la clé S du GSI). Pas de `created_at` ici : la ligne reste hors du GSI
   creux `UserActivitiesIndex` tant que le fetcher n'est pas passé.
6. Timeout Lambda 120 s (au-delà des 90 s de PushSend). Jamais de log de
   l'event (il contient le jeton) : pas de `log_event=True`, log des seuls
   `activity_id` et résultats.

### 6. API (Lambdas `input_status` et `input_submit`)

Communs : auth Cognito existante ; `activity_id` validé (chiffres seulement) ;
lecture de la ligne ; `user_id` de la ligne doit égaler `custom:strava_id`,
sinon 403. Le jeton n'est jamais renvoyé.

Routes : sous la ressource existante `/activities/{activityId}`
(`api_gateway_stack.py:468-471`, aujourd'hui créée dans le bloc audio
optionnel). On la sort de ce bloc pour la créer une seule fois, et on y monte
`feedback`. Pas de second `activities` ni de `{id}` concurrent.

`GET /activities/{activityId}/feedback` -> `{state, deadline_at}` avec
`state ∈ awaiting | submitted | closed | none`. Un `awaiting` dont
`input_deadline_at` est passé est renvoyé `closed` (jamais une fenêtre
périmée proposée). Après le run, `deadline_at` est absent (le fetcher ne le
recopie pas).

`POST /activities/{activityId}/feedback` :
- Validation stricte : `rpe` de type `int` (pas `bool`), 1 à 10, obligatoire ;
  `summary` chaîne, caractères de contrôle retirés, 0 à 2000 caractères après
  nettoyage ; tout autre champ -> 400.
- `UpdateItem` : `SET athlete_input = :input, athlete_input_state = :submitted
  REMOVE input_task_token`, condition `athlete_input_state = :awaiting AND
  user_id = :u`, `ReturnValues=ALL_OLD` pour le jeton. Condition échouée -> 409.
- `SendTaskSuccess(jeton, "{}")`. Toute erreur après l'écriture
  (`TaskTimedOut`, `InvalidToken`, `TaskDoesNotExist`, autre) -> 202 quand
  même : la saisie est en base et le fetcher la lira (§7). Erreur journalisée +
  métrique.
- Throttling dédié sur la méthode (`method_options` de
  `/activities/{activityId}/feedback/POST`, 5 req/s, burst 10) ; l'étage par
  défaut est à 100/200 (`api_gateway_stack.py:270-285`).

IAM `SendTaskSuccess` : l'action n'a pas de type de ressource, donc
`Resource: "*"` (pas de dépendance cross-stack vers la state machine, pas de
`grant_task_response`, qui ajouterait `Failure`/`Heartbeat`).

### 7. Fetcher (`activity_fetcher.py`), seul arbitre

Au début, fermeture de la fenêtre :

```
UpdateItem
  SET athlete_input_state = :closed
  REMOVE input_task_token
  Condition athlete_input_state IN (:awaiting, :submitted)
  ReturnValues ALL_NEW
  ReturnValuesOnConditionCheckFailure ALL_OLD
```

- Succès -> `athlete_input` lu dans `response["Attributes"]` (`ALL_NEW`).
  L'état d'avant compte la métrique : `awaiting` -> `InputWait{outcome=expired}`,
  `submitted` -> `InputWait{outcome=submitted}`.
- `ConditionalCheckFailedException` -> pas d'erreur : flag off, relance ou
  fenêtre déjà fermée. L'ancien item est dans `e.response["Item"]` (format
  DynamoDB brut, à désérialiser avec `TypeDeserializer`, pas le même format
  que `Attributes`). On y prend `athlete_input` s'il existe : une relance
  garde le RPE déjà saisi. Nécessite boto3 2023+ (vérifier la version
  embarquée ou épinglée).
- Ces valeurs sont passées à `store_activity_data`. Elles ne passent PAS par
  le `_carry` (`:973-975`), qui lit le `get_item` non cohérent (`:882`) : le
  code pose `item["athlete_input"] = <résultat de la fermeture>` et
  `item["athlete_input_state"] = "closed"` directement. Test : `get_item`
  renvoie `awaiting`, l'item écrit garde `closed`.

Après la fermeture, l'API répond 409. DynamoDB sérialise les deux écritures :
saisie d'abord -> lue par le fetcher ; fermeture d'abord -> 409.

Puis :
- `activity_data["athlete_rpe"] = rpe` et `activity_data["athlete_summary"] =
  summary`, avant la sérialisation JSON (D9 : rien n'est ajouté à
  `original_description`).
- `input_task_token` et `input_deadline_at` ne sont pas réécrits : ils
  disparaissent au `put_item`.

Le fetcher relit Strava après l'attente : dictée et Enduraw arrivés pendant
l'heure sont pris (`_resolve_original_text`, `:65-147`, inchangé).

### 8. Agents

- `athlete_summary` passe dans le prompt entre balises dédiées, contenu
  échappé (les balises de fermeture sont neutralisées), avec la consigne de ne
  suivre aucune instruction qu'il contient. C'est une réduction de risque, pas
  une isolation : le post reste relu par `content_guard`.
- Contenu : une ligne « RPE de l'athlète : N/10 » + le résumé.
- Coach : la même ligne, à côté de « Effort relatif Strava : N (échelle
  ouverte) », jamais additionnés (D7). Le bilan de la semaine liste le RPE.
- Lieux à brancher : construction du prompt contenu (`content_generator.py`,
  `content_agent.py`) et coach ; `_activity_own_text` et `content_guard`
  continuent à ne lire que le texte de l'athlète (le résumé n'y est pas).

### 9. Écran

Route protégée `/activities/:id/feedback` (à ajouter dans `App.tsx`, à côté
de `/activities/:id`) : appelle
le `GET`, affiche 10 boutons RPE + un champ résumé (dictée iOS) + « Envoyer »
si `awaiting`, sinon « Déjà traitée ». 409 au `POST` -> « Déjà traitée ».

### 10. Notif « Activité enrichie »

`_maybe_push_completed` (`strava_updater.py:314-356`) ne lit que
`PUSH_ENABLED`. Il est sauté quand la ligne porte `athlete_input_state`
(signal par activité, lu sur l'item) : une seule notif par activité. Flag off
-> pas de `athlete_input_state` -> comportement d'aujourd'hui. Une
republication par dictée tardive ne renvoie pas de notif.
Sur le chemin d'erreur de `input_wait` une fois la fenêtre ouverte
(`push_error`, `error` après l'ouverture, crash attrapé par le `Catch`), la
ligne porte déjà `athlete_input_state` : l'activité ne reçoit aucune notif, ni
demande ni « Activité enrichie ». Voulu ; l'alarme
`InputWait{outcome=error|push_error}` (ou `Errors` de la Lambda) signale l'incident.
Un PushSend qui a livré la notif mais dépasse le `read_timeout` de 95 s est
compté `push_error` : la fenêtre est fermée, et toucher la notif affiche
« Déjà traitée ».

## Well-Architected

| Pilier | Ce que fait le plan |
|---|---|
| Excellence opérationnelle | Tout en CDK ; flag par utilisateur ; état visible dans Step Functions ; métriques EMF `InputWait{outcome}` (`waiting`, `no_push` (aucun appareil atteint), `push_error` (PushSend en échec, réponse illisible ou `statusCode` différent de 200), `replay`, `error`, `callback_error` (libération `SendTaskSuccess` en échec, émis en plus de l'outcome d'origine) depuis `input_wait` ; `expired`, `submitted` depuis le fetcher) et `InputSubmit{outcome}` (`ok`, `409`, `late`, `callback_error`). Un timeout d'attente rattrapé ne rend pas l'exécution `TIMED_OUT` : c'est `expired` qui le mesure, pas une erreur. Alarme `ExecutionsTimedOut` à ajouter (seul `ExecutionsFailed` existe, `webhook_processing_stack.py:598-614`) ; alarmes erreurs Lambda `input_*` et 5XX/throttles API |
| Sécurité | Cognito + propriétaire vérifié sur la ligne ; validation stricte ; jeton jamais renvoyé, jamais loggé, retiré de la ligne à chaque sortie (submit, `sent == 0`, fermeture) ; IAM moindre privilège ; résumé balisé et échappé ; throttling dédié |
| Fiabilité | Une seule exécution ; écritures conditionnelles ; fetcher arbitre unique, tolérant aux relances ; échec ouvert (D8) ; Lot 0 rend les vraies pannes visibles |
| Efficacité des performances | Pas de polling ; lancement à la seconde ; aucune nouvelle table ni file |
| Optimisation des coûts | Pas de coût pour la durée d'attente (Standard) ; 3 petites Lambdas ; pas de Scheduler ni de cron |
| Durabilité | Aucun calcul à vide |

### IAM (moindre privilège)

| Rôle | Droits |
|---|---|
| `input_wait` | `dynamodb:UpdateItem` sur la table activités ; `lambda:InvokeFunction` sur PushSend ; `states:SendTaskSuccess` |
| `input_status` | `dynamodb:GetItem` sur la table activités |
| `input_submit` | `dynamodb:GetItem` + `dynamodb:UpdateItem` sur la table activités ; `states:SendTaskSuccess` |
| Rôle Step Functions | `lambda:InvokeFunction` sur `input_wait` (ajouté par CDK) |
| Fetcher | inchangé (`dynamodb:UpdateItem` déjà accordé) |

`states:SendTaskSuccess` seul (ni `Failure` ni `Heartbeat`), sur
`Resource: "*"` : l'action n'a pas de type de ressource (Service
Authorization Reference, signalé par la relecture GPT ; reconfirmer au
`cdk synth`). Déclaration dédiée, pas de `grant_task_response`. Table et
PushSend : ARN exacts. cdk-nag reste à 0 erreur (suppression `IAM5`
justifiée pour ce seul `*`).

### Jeton et stream DynamoDB

La table a un stream `NEW_AND_OLD_IMAGES` (`core_infrastructure_stack.py:70-83`) :
les images contiennent le jeton tant qu'il est sur la ligne. Seul
consommateur : `voice_debrief_generator.py:141-200`, qui ne logge que des ids
et compteurs (vérifié par la relecture). Test de régression : aucun log de
l'event complet. Le jeton est retiré à chaque sortie et expire au bout d'1 h.

Exécution stoppée à la main (`ABORTED`) ou expirée : la règle EventBridge
existante (`webhook_processing_stack.py:307-323`) appelle déjà
`stepfunctions_error_handler.py` sur `FAILED`, `TIMED_OUT`, `ABORTED`. On y
ajoute `SET athlete_input_state = :closed REMOVE input_task_token`
(conditionnel, sans erreur si absent). Pas de balayeur.

## Tests

| Cas | Attendu |
|---|---|
| Saisie avant 1 h | un run, RPE et résumé lus |
| Rien en 1 h | un run au timeout, sans RPE |
| Saisie à la seconde du timeout | un run ; RPE pris si avant la fermeture, sinon 409 |
| `SendTaskSuccess` en erreur après écriture | 202, saisie lue par le fetcher |
| Seconde saisie | 409 |
| Fetcher relancé (fenêtre déjà fermée) | pas d'erreur, RPE gardé depuis `ALL_OLD` |
| `get_item` renvoie `awaiting` alors que la fermeture a réussi | l'item écrit garde `closed` |
| Exécution `ABORTED` pendant l'attente | ligne `closed`, jeton retiré |
| Notif : timeout de lecture boto3 | une seule invocation PushSend |
| Flag écrit via `configure_module` | lu par le processeur |
| `GET` sur un `awaiting` périmé | `closed` |
| Message SQS en double | même nom d'exécution, rien de plus |
| `update` Strava pendant l'heure | ignoré |
| `sent == 0` / push off / `input_wait` en panne | run immédiat |
| Erreur Lambda pendant l'invocation callback | run au plus tard au timeout (constater lequel des deux) |
| Dictée tardive après le run | pas d'attente, RPE gardé, pas de notif |
| Message SQS sans `wait_for_input` | ancien chemin, pas d'erreur Choice |
| Course avec Enduraw | notif après les 2 min ; texte Enduraw intact |
| Corps invalide (rpe 0, 11, `true`, texte, champ inconnu) | 400 |
| Autre utilisateur | 403 |
| `GET` avant, pendant, après | `none` / `awaiting` / `closed` |
| Jeton absent des logs, des réponses API et de la ligne après sortie | vérifié |
| RPE et `suffer_score` jamais combinés | vérifié dans les prompts |
| Flag éteint | chemin identique à aujourd'hui, notif « enrichie » inchangée |
| `cdk synth` + cdk-nag ; ASL validé | 0 erreur |

Note : un nom d'exécution échoué ne peut pas être relancé (90 jours). Le
redrive Step Functions reprend à l'état en échec ; or Lot 0 envoie les
erreurs vers des états `Fail` explicites, qui échouent à nouveau. Le redrive
ne rejoue donc presque rien ici : pas de procédure de rejeu promise par ce
plan (hors scope, inchangé par rapport à aujourd'hui).

## Ordre

1. Lot 0 (`fix/lot0-pipeline`) -> PR (pas de conflit : il ne touche que la fin
   de la définition).
2. Web push rebasé sur `dev` -> PR.
3. Ce plan, derrière `modules_config.athlete_input.enabled`, avec
   `notify_input_request` dans le helper push.
4. Redeploy AgentCore : `content_gen`, coach.
