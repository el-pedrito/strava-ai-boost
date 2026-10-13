# Plan d'implémentation — fiabilité avant publication (octobre 2026)

Issu de la revue multi-modèles du 2026-10-12 (Opus 5.5, Opus 4.8, Sonnet 5.5) après
l'incident Sonnet/Haiku 5.5 : trois traitements muets pendant des jours sans aucun
signal. Principe directeur : **une sortie qui n'a pas été produite doit faire du bruit**.
Aucune nouvelle feature tant que les lots 1 à 4 ne sont pas livrés.

Légende effort : S ≈ ½ jour, M ≈ 1-2 jours, L ≈ 3+ jours. ⚙️ = étape à lancer depuis le
terminal de l'auteur (déploiement agent, script boto3 avec creds exportées).

---

## Lot 1 — Détecter les sorties vides (M) — priorité absolue

Constat : les métriques `Errors` Lambda restaient à ~0 alors que le voice debrief
échouait sur chaque activité. Le handler renvoie des `batchItemFailures` (retry du
stream, 85 invocations pour 10 activités) au lieu de lever, et synthèse/récap renvoient
`statusCode: 500` dans le payload, ce qu'aucune alarme ne lit. Les 3 alarmes existantes
(`webhook_processing_stack.py`) ne couvrent que la DLQ, les vieux messages et une Lambda.

1. **Métrique métier « artefact produit »** (namespace `StravaAIBoost`, via le logger
   Powertools déjà en place, `@metrics.log_metrics`) :
   - `ContentProduced` / `CoachProduced` (dimension `outcome=ok|empty|failed`) dans
     `content_generator.py`, `coach_generator.py` ;
   - `VoiceDebriefProduced`, `WeeklySynthesisProduced`, `WeeklyRecapProduced` ;
   - `ActivityPublished` dans `strava_updater.py`.
2. **Échecs typés au lieu de `return None`** : sur les chemins pipeline uniquement
   (`content_generator`, `coach_generator`, `voice_debrief_generator`,
   `weekly_synthesis`, `weekly_audio_recap`). Une exception métier `GenerationFailed`
   qui émet la métrique `failed` puis est soit levée (synthèse, récap : la Lambda passe en
   `Errors`), soit comptée (voice debrief : on garde `batchItemFailures` mais on émet la
   métrique). Les `except` best-effort documentés (extraction de séries, mémoire) restent,
   mais émettent `outcome=degraded`.
3. **Alarmes** (nouvelle construct `ops_alarms` dans la stack existante qui porte le topic
   SNS `strava-ai-boost-ops-alerts`) :
   - `ActivityPublished` = 0 sur 72 h alors que `ActivityProcessed` > 0 ;
   - `outcome=failed` ≥ 1 sur 1 h pour content/coach/voice ;
   - `WeeklySynthesisProduced` et `WeeklyRecapProduced` absents le lundi 06:00 UTC
     (`treat_missing_data=BREACHING`) ;
   - Step Functions `ExecutionsFailed` ≥ 1 ;
   - ratio voice : `VoiceDebriefProduced{ok}` / activités publiées < 50 % sur 24 h.
4. **Tests** : unitaires sur chaque chemin vide/échec (métrique émise, bonne issue) ;
   anti-dérive qui interdit `return None` dans un `except` des 5 fichiers pipeline sans
   métrique associée.
- **Fait quand** : rejouer l'incident (forcer `maxTokens: 50` en env sur le voice
  debrief) déclenche un mail SNS en < 1 h.

## Lot 2 — Contrat de modèle + smoke test (S-M)

Constat : `thinking`, `temperature`, `max_tokens` et timeouts diffèrent par modèle et
sont dispersés (`no_thinking()` ajouté le 2026-10-12, budgets dans 3 agents, timeouts
dans 2 Lambdas).

1. **Registre de profils** dans `src/config/llm_config.py` (miroir
   `lambda_functions/shared/llm_models.py`, test de synchro existant étendu) :
   `MODEL_PROFILES[model_id] = {thinking_off, accepts_temperature, default_max_tokens}`.
   `no_thinking()` lit le profil au lieu de tester la sous-chaîne `sonnet`.
2. **`scripts/smoke_models.py`** : un appel Converse réel par profil × usage
   (texte court sans réflexion, JSON, appel avec budget agent) ; vérifie `stopReason`,
   présence d'un bloc `text`, coût en tokens. ~0,05 $/run.
3. **Smoke post-déploiement** des 3 runtimes : invocation de la fixture
   `run_easy` (content_gen), d'un payload coach minimal, d'un message chat (JWT de test
   hors scope : on vérifie seulement `/ping` du runtime chat).
4. Hook dans `deploy.sh` et `deploy_agentcore_agents.sh` : le smoke tourne en fin de
   script, échec = sortie non nulle.
- **Fait quand** : changer `DEFAULT_HAIKU_MODEL_ID` vers un modèle sans profil fait
  échouer le test de synchro, et un profil faux fait échouer le smoke.

## Lot 3 — Idempotence, rejeu, retries (M)

Constat : retry botocore → appel dupliqué (08/10) ; pas de retry → activité perdue sur
502 (09/10) ; P1 « dictée tardive perdue » (`activity_processor.should_skip_processing`
ignore les `update` après traitement).

1. **Retries Step Functions** sur les tâches content/coach : `Retry` sur
   `Lambda.ServiceException`, `Sandbox.Timedout` et une erreur métier
   `TransientAgentError` (levée sur 502/503/timeout AgentCore), 2 tentatives, backoff 2.
   Côté Lambda, botocore garde `standard/3` (déjà en place, `12d180b`).
2. **Verrou d'exécution** : nom d'exécution Step Functions déterministe
   `activity-{id}-v{version}` (Step Functions refuse un doublon de nom) au lieu du
   suffixe timestamp actuel ; `version` = `updated_at` de la description Strava.
3. **P1 dictée tardive** : sur `update` d'une activité déjà `completed`, si la
   description Strava contient du texte athlète absent de `original_description`
   (et pas notre signature), relancer la génération en mode merge : nouvelle note
   athlète + données existantes, sans écraser les éditions manuelles postérieures
   (comparer avec `final_description` si déjà analysé). Spec détaillée dans BACKLOG P1.
4. **Retry 429 Strava** dans `strava_updater.py` : backoff exponentiel borné (3
   essais), puis échec typé → retry Step Functions.
5. **`scripts/replay_activity.sh <id>`** : rejoue une activité depuis l'input de sa
   dernière exécution (procédure utilisée à la main le 09/10).
- **Tests** : unitaires sur la décision merge/skip des `update` (4 cas : dictée
  ajoutée, édition manuelle, notre propre update, rien de nouveau) ; test CDK sur les
  `Retry`.
- **Fait quand** : un 502 injecté sur la première invocation (env de test) se termine
  en `completed` ; une dictée ajoutée 10 min après traitement est intégrée.

## Lot 4 — Mémoire, phase 1 (S-M)

1. **Couper la pollution du coach** : `feedback_analyzer.write_feedback_to_memory`
   n'écrit plus dans la mémoire partagée (flag `FEEDBACK_TO_MEMORY=false` par défaut).
   Les préférences existantes (22) restent lisibles.
2. **Formateur déterministe** post-génération (`content_generator`, après
   `_strip_title_echo`) : découpe tout paragraphe > 280 caractères au point le plus
   proche, garantit une ligne vide entre paragraphes, n'altère jamais le bloc coach ni
   la signature. + tests.
3. **Vérifier la garde numérique** (`content_guard.verify_content`) : mesurer sur les
   descriptions d'août-octobre combien de corrections de chiffres restent dans les
   éditions de l'athlète. N'étendre la garde (secondes ≥ 60, cohérence
   distance/durée/allure) que si > 0.
4. **Purge** des records du coach issus des diffs d'édition (liste présentée avant
   suppression).
- **Fait quand** : plus aucun événement de diff dans la mémoire coach après une nuit,
  aucun paragraphe > 280 caractères sur 10 fixtures.

## Lot 5 — ~~Supprimer le runtime coach~~ (retiré le 2026-10-12)

Écarté : le coach n'a pas failli pendant l'incident (le 502 venait de `content_gen`), le
gain (un déploiement manuel en moins) ne justifie pas de perdre l'observabilité GenAI et
le pattern commun avec `content_gen`. Le mode `conversation` de `coach_agent.py`, mort
depuis `coach_chat`, pourra être retiré à l'occasion.

## Lot 6 — CI minimale (M)

GitHub Actions (`.github/workflows/ci.yml`, à côté de `release-please.yml`), sur PR et
push `dev` : `pytest tests/unit tests/regression`, `npm test` + `npm run lint`
frontend, `cdk synth` (sans credentials, contexte factice), cdk-nag
(`AwsSolutionsChecks`, suppressions justifiées), `pip-audit`, `npm audit`,
detect-secrets. Corriger les 5 tests CDK périmés. Jamais d'appel Bedrock en CI.
- **Fait quand** : la CI est verte sur `dev` et bloque une PR qui casse un test.

## Lot 7 — Durcissement pré-publication (M)

- `verify_token` aléatoire dans Secrets Manager, lu par le script, puis fermeture
  (ordre du BACKLOG P1).
- IAM : `foundation-model/*` → `llm_config.all_iam_resources()` dans
  `security_stack.py:124` et `core_infrastructure_stack.py:255,291`.
- `RemovalPolicy.RETAIN` + PITR sur les tables DynamoDB et les secrets
  (`core_infrastructure_stack.py`), `DESTROY` conservé sur les buckets frontend/audio.
- Throttling sur l'étage webhook (`methodSettings`), budget de tokens par appel
  (garde-fou `max_tokens` déjà là, ajouter une alarme coût Bedrock quotidienne).
- Relire les fixtures de régression (format de notes réel) et vérifier les CGU de
  l'API Strava sur l'usage des données avec un LLM.

## Lot 8 — Déploiement reproductible des runtimes (M-L)

Migrer `content_gen` et `coach_chat` hors du starter toolkit (déprécié côté AWS) :
constructs CDK AgentCore si disponibles pour `direct_code_deploy`, sinon le CLI
`@aws/agentcore`. Objectif : `./scripts/deploy.sh dev` déploie tout, sans étape
⚙️ manuelle, avec le smoke du lot 2 en fin.

Plan détaillé validé (blue/green via CDK, non implémenté) :
[lot8-agentcore-blue-green.md](lot8-agentcore-blue-green.md).

## Lot 9 — Mémoire, phase 2 puis publication (L)

1. Deuxième ressource mémoire « préférences » (stratégie built-in conservée), diff
   filtré en événement ASSISTANT/USER enrichi, clés de style fermées, lecture par
   `ListMemoryRecords` paginé, verrou IAM, script admin de réconciliation. Rejeu
   chronologique des 95 éditions jugé contre un résultat attendu écrit à l'avance.
   Détail : échanges du 2026-10-12.
2. Documentation (architecture, coût mensuel, teardown, modules optionnels), passage
   public, puis blog post.

---

## Gelé jusqu'à la fin du lot 4

Chronos-2, Strava MCP, PWA push, briefing matinal, revue de cycle Campus, race
readiness, backfill PRs, Nova Sonic, app mobile, refactor `CoachPage.tsx`.

## Ordre et dépendances

```
Lot 1 ─┬─> Lot 3 ─────────> Lot 8 ─> Lot 9
Lot 2 ─┘     │
Lot 4 ───────┘   Lot 6 ─> Lot 7 ─────────┘
```

Lots 1 et 2 en parallèle (fichiers distincts), lot 3 s'appuie sur la métrique du lot 1
pour être vérifiable. Si le temps manque, on sacrifie le lot 9 phase 1 avant les lots 1
à 3.
