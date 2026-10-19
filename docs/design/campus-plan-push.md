# Push « Plan Campus mis à jour » (plan v3, non implémenté)

Statut : **design revu, bloqué sur 2 décisions** (voir la fin). Rien n'est codé.
Base : le Web Push porté depuis la PR #26 d'Adrien (branche `feat/web-push-port`).

## But

Quand une séance que Pierre va faire bientôt apparaît ou change dans son plan
Campus Coach, une seule notification ouvre `/plan` pour (re)télécharger le
fichier `.workout`. Un `.workout` importé ne se met jamais à jour sur la Watch :
une séance modifiée compte autant qu'une nouvelle.

## Ce que la revue a trouvé dans le code existant

Deux tours de revue (Opus 5.5 et GPT-5.6 Sol, 4 revues) ont trouvé deux bugs
**déjà présents** dans `lambda_functions/webhooks/campus_coach_sync.py`, à
corriger avant la notification :

1. **Identité positionnelle.** Une ligne a pour clé `f"{week_date}_{idx}"`
   (l.115) et l'upsert garde `local_status`, `matched_activity_id`,
   `completed_at` sur cette clé. Si Campus insère ou réordonne une séance, une
   nouvelle séance hérite de la complétion d'une autre (cachée de `/plan`), et
   la séance faite réapparaît comme ouverte.
2. **Suppression destructrice.** `_delete_stale_sessions` (l.466-493) supprime
   toute ligne absente de la réponse. Une réponse vide ou partielle efface des
   lignes et leur état local. La borne de la fenêtre (`now - 6 semaines`, avec
   l'heure) ne tombe pas sur un lundi : la semaine limite peut être supprimée
   juste après son upsert.

## Lot A : identité des séances (prérequis)

Dépend de la **décision 1**.

- Si Campus expose un id de séance stable : c'est la clé de rattachement de
  l'état local, et le contenu ne sert qu'à détecter un changement.
- Sinon : rattachement prudent. D'abord empreinte exacte, puis à la même
  position une identité faible (`title`, `sport`, `training_type`). En cas de
  doute, on **garde** l'état local, on ne le supprime jamais (une recalibration
  des allures change toutes les empreintes, séances faites comprises).
- Un seul canonicaliseur partagé (A et C) : `Decimal` entier -> `int`, JSON
  trié. Les lignes relues de DynamoDB ont des `Decimal`, `json.dumps` plante
  dessus.
- Le REMOVE est conditionné à l'état relu (une complétion écrite entre la
  lecture et l'écriture n'est pas écrasée). Le champ hérité `status='Fait'`
  suit la même règle.
- Tests : insertion en tête, réordonnancement, jumeaux, allures recalibrées sur
  une séance faite (la complétion reste), lignes relues via `TypeDeserializer`.

## Lot B : suppression sûre (prérequis)

- Ne supprimer que dans les partitions `week-*`.
- Une semaine absente de la réponse, ou présente avec 0 séance : rien n'est
  supprimé dans cette semaine.
- Une séance disparue d'une semaine renvoyée et non vide : supprimée seulement
  après 2 synchros consécutives où elle manque.
- Élagage des vieilles semaines aligné sur le lundi qui contient le début de
  la fenêtre.

## Lot C : la notification

**Quand.** En fin de synchro réussie, dans un `try/except` qui ne logue que des
compteurs : le push ne peut jamais transformer une bonne synchro en 500. Rien
n'est lu dans la table push si `PUSH_ENABLED` est faux.

**Empreinte de changement.** Pour une séance exportable : sha256 des octets de
`map_session(item, GUID fixe)`. Pour une séance non exportable : un jeton
`{exportable: false, raison}`. C'est exactement « le fichier Watch a changé ».

**Séances suivies.** Celles de `/plan` (`api.plan_workouts._is_open`), calculées
sur les items en mémoire de la synchro, exportables ou non.

**État.** Table push, partition `state#campus#<owner>`, item `plan` :
`sessions: {id -> empreinte notifiée}` par semaine, `weeks_seen`,
`last_sent_date`, `last_run_at`, `version`, `config_generation`.
PushSend ne lit que la vraie partition `user_id` et ignore les lignes qui ne
sont pas des abonnements.

**Règles.**
- Premier passage, état périmé (`last_run_at` > 14 jours) ou nouvelle
  `config_generation` (réactivation) : baseline sans notifier.
- `last_run_at` est rafraîchi à chaque synchro (heartbeat), sous condition de
  `version`.
- Semaine courante ou suivante sans entrée alors que l'état est frais : on
  compare à vide, ses séances notifient. Les semaines plus lointaines sont
  baselinées. Le passage du lundi ne change rien (déjà connues).
- Une séance qui disparaît ne déclenche rien et ne retire rien de l'état tant
  qu'elle n'a pas manqué 2 fois (pas de faux « nouvelle » après une réponse
  partielle).
- Envoi seulement entre 8 h et 21 h heure de Paris (cron réel : 9 h-21 h l'été,
  8 h-20 h l'hiver), au plus 2 par jour avec 4 h d'écart. Hors fenêtre, rien
  n'est écrit : la différence attend le passage suivant.

**Envoi atomique.** UpdateItem conditionnel sur `version` (réservation), puis
invoke asynchrone de PushSend, accepté seulement sur un 202. Sinon rollback qui
restaure l'état précédent. Livraison best-effort (PushSend n'est pas rejoué).

**Contenu.** Une notification par passage, pour les deux semaines :
```json
{"title": "Plan Campus mis à jour",
 "body": "S43 : 2 séances nouvelles ou modifiées. Ouvre le plan pour ta Watch.",
 "url": "/plan#plan-week-2026-W43",
 "tag": "campus-plan-2026-10-17"}
```
Jamais de titre de séance, d'allure, de durée, de conseil, d'objectif ou de date
de course (écran verrouillé, Watch). Tag par jour : la notification du lendemain
alerte vraiment.

**Câblage (seulement si `push_enabled`).** Sur `webhook_stack.campus_coach_sync` :
`PUSH_ENABLED`, `PUSH_SEND_FUNCTION`, `PUSH_SUBSCRIPTIONS_TABLE`, `PUSH_OWNER_ID`
(jamais lu dans l'événement), `grant_notify`, et une politique explicite
`dynamodb:GetItem/PutItem/UpdateItem` sur la table push avec
`ForAllValues:StringEquals dynamodb:LeadingKeys = ["state#campus#<owner>"]`.
Jamais Query ni Scan. Synth refusée si l'owner est vide. Pas de cycle de stacks
(vérifié). Nouveau helper générique `shared.push_notify.notify(user_id, title,
body, url, tag)`.

**Frontend.** `PlanPage` recharge le plan quand l'app redevient visible ou que
le hash change, puis fait défiler jusqu'à la semaine du hash. Sinon une app
déjà ouverte sur `/plan` montrerait l'ancien plan après un clic sur la notif.

**Tests.** Empreinte = octets ; réordonnancement neutre ; baseline silencieuse ;
nouvelle séance = 1 notif ; aucun changement = rien ; réponse partielle puis
retour = rien ; heures calmes sur les 9 passages réels en CET et CEST ;
plafond journalier ; heartbeat et 14 jours ; réactivation ; concurrence ;
rollback ; contenu sans texte de séance ; jamais de 500 ; IAM figée ; flag off
identique.

## Décisions à prendre

1. **Id de séance stable chez Campus ?** À lire dans la sortie de
   `probe_schema` (`session_keys`), puis à relancer après une modification de
   séance dans Campus pour voir si l'id survit. Ça décide le lot A.
2. **Consentement.** Les reviewers divergent :
   - Opus : un seul interrupteur, nouveau texte (« activité publiée et plan
     Campus modifié »), puisque tu es le seul utilisateur et que tu le demandes.
   - GPT : un interrupteur Campus séparé, éteint par défaut, filtré côté serveur.

## Plus tard

Débrief audio de la semaine prêt (cron du dimanche en heures calmes l'été),
échec final d'enrichissement, « séance Campus validée » dans la notif
d'activité, synchro Campus bloquée, fin d'abonnement, compte à rebours de
course. À ne pas faire : rappel du jour (aucune date de séance stockée),
relances d'assiduité, chiffres sur l'écran verrouillé, boutons d'action
(non supportés par Safari).
