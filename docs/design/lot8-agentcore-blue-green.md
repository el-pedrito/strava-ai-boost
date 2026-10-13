# Lot 8 — Déploiement reproductible des runtimes AgentCore (plan final)

Statut : **validé, pas implémenté**. Plan revu en 6 tours par deux modèles (Claude Opus 5.5 et
GPT-5.6 Sol), verdict final READY 9/10 des deux. Rien n'a été déployé.

Lien : section « Lot 8 » de [reliability-plan-2026-10.md](reliability-plan-2026-10.md).

## Pourquoi

Les 3 runtimes (`content_gen`, `strava_ai_boost_coach`, `coach_chat`) sont déployés par le
starter toolkit `bedrock-agentcore-starter-toolkit`, que AWS ne supporte plus. Sa config
`.bedrock_agentcore.yaml` est gitignorée, contient des chemins absolus, et
`scripts/deploy_agentcore_agents.sh` y réinjecte un ARN mémoire avec `*` à la place du compte
(l.146 et l.273), ce qui bloque le deploy. Le bucket des zips n'est pas versionné : chaque deploy
écrase le zip précédent, il n'y a donc aucun retour arrière propre.

Objectif : `./scripts/deploy.sh dev` déploie tout, agents compris, sans étape manuelle, avec le
smoke en fin.

## Chemin retenu : blue/green via CDK

Les runtimes actuels (blue) restent intacts. De nouveaux runtimes (green) sont créés à côté par
CDK, testés sans trafic, puis on bascule un ARN à la fois. Le retour arrière = remettre l'ancien
ARN.

Écartés :

| Option | Raison |
|---|---|
| `cdk import` des runtimes en place | le 1er deploy après import pousse le template sur la prod (env, zip, authorizer) |
| CLI `@aws/agentcore` + `agentcore import` | importe aussi la mémoire dans une stack du CLI, 2e outil jeune, AGUI/JWT non prouvés |
| Durcir le starter toolkit seul | garde un outil non supporté ; sert seulement de mesure d'attente |

## Invariants

- La mémoire n'est jamais recréée ni supprimée. Les runtimes green la référencent par id.
- Aucune publication Strava de test. Tests en preview ou par invocation directe du runtime.
- L'IAM des Lambdas appelantes garde `runtime/*` jusqu'au nettoyage final (sinon le retour arrière
  vers blue renvoie AccessDenied).
- Un runtime à la fois, sur go explicite, 48 h d'observation entre chaque.
- Repo public : aucun id de compte ni ARN commité.

## Étapes

### 0. Sauvegarde (aucun changement prod)

- Nouveau bucket `strava-ai-boost-agentcore-artifacts-<account>` : versionné, SSE-S3, accès public
  bloqué, RETAIN.
- Copier les 3 `deployment.zip` blue sous `backup/<agent>/`. Noter clé, VersionId, SHA-256.
- Sauver `get-agent-runtime` complet des 3, les policies (inline + attachées) des 3 rôles toolkit
  (dont `CoachChatToolsDataAccess`), et le `config.json` servi par le frontend avec son VersionId S3.
- Écrire `agentcore.schema_version = 2` dans `cdk.context.json` (écriture atomique) une fois la
  sauvegarde vérifiée. Dès ce moment, `deploy_agentcore_agents.sh` et
  `configure_agentcore_integration.sh` sortent en erreur : plus aucun redeploy blue possible.

### 1. Durcir sans redéployer

- Corriger le `*` et supprimer les fonctions définies deux fois dans `deploy_agentcore_agents.sh`.
- Verrouiller les deps de `src/agents/` avec un lock uv complet, aligné sur les versions du zip prod
  (ex. `content_gen` : strands-agents 1.29.0, strands-agents-tools 0.2.22, bedrock-agentcore 1.4.3).
- Retirer `playwright` et le starter toolkit des deps runtime s'ils ne sont importés nulle part.
- Remplacer dans `deploy.sh` les messages qui renvoient vers `deploy_agentcore_agents.sh`.

### 2. Code (CI verte, rien déployé)

**Source unique de config.** Module `stacks/agentcore_context.py` : fonction pure
`resolve_agentcore_config(ctx, account, mode)` + adaptateur CDK qui passe `Stack.of(scope).account`.

- Valeurs sous la clé `agentcore` de `cdk.context.json` (le bloc périmé actuel est sauvegardé puis
  remplacé) : memory id, ARN par runtime, guardrail id et version.
- `default_user_id` reste à la racine, inchangé (lu par 5 stacks).
- Modes via `STRAVA_AGENTCORE_MODE` ou `-c agentcore_mode` :
  - `strict` (exporté par `deploy.sh` avant synth, list et deploy) : tous les champs requis et
    valides, sinon le synth échoue.
  - `ci` (défaut) : accepté seulement pour le compte `123456789012`, avec des valeurs factices.
    Compte réel, `None` ou token non résolu en mode `ci` = échec.
- Un synth `strict` raté devient fatal dans `deploy.sh`. Le premier déploiement ne saute plus le synth.
- Les 4 stacks lecteurs (Content, API, Feedback, VoiceDebrief) ne lisent plus que ce module. Un test
  échoue si un stack importe encore les lecteurs de `env_loader`.
- `smoke_models.py`, `run_prompt_regression.py`, `run_managed_evals.py` lisent les ARNs via la
  même fonction (après bascule ils testent green ; `--agent-arn` permet de tester blue).

**Stack `StravaAIBoost-Agents`**, instanciée dans tous les modes (en `ci`, un petit zip factice
commité dans `tests/fixtures/` ; un test vérifie qu'il n'est jamais pris en `strict`).

- Build du zip en pré-étape de `deploy.sh`, pas dans le synth :
  `uv export --locked` (avec hashes) puis
  `uv pip install --require-hashes --target build/<agent>/pkg --python-version 3.12 --python-platform aarch64-manylinux2014 --only-binary=:all:`,
  zip déterministe (tri, mtime fixe, droits 644/755).
- Gate : liste des fichiers green comparée à blue, `bin/opentelemetry-instrument` présent et
  exécutable, tailles sous les limites.
- Un `BucketDeployment` par runtime : `extract=False`, `destination_key_prefix=runtimes/<agent>/`,
  `prune=False`, `retain_on_delete=True`, `memory_limit=1024`, stockage éphémère 2 GiB.
- `CfnRuntime` : `Code.S3` = `Fn.select(0, object_keys)` + `Fn.select(0, object_version_ids)`.
  Un test vérifie que chaque runtime référence les sorties de son propre déploiement.
- Un rôle d'exécution par runtime, géré par CDK, porté depuis les policies blue, trust
  `bedrock-agentcore.amazonaws.com` avec `aws:SourceAccount` et `aws:SourceArn`.
- `coach_chat` : même `customJWTAuthorizer` que blue (pool et client lus dans les sorties du stack
  Frontend), `requestHeaderConfiguration` nul comme blue.
- Tags déclarés dans CDK. Suppressions cdk-nag justifiées pour le handler BucketDeployment et le
  custom resource.

**Groupes de logs.** Pas de `CfnLogGroup` (course possible avec AgentCore). Un custom resource
idempotent, après le runtime, sur Create et Update : CreateLogGroup (ignore AlreadyExists),
rétention 30 j, `PutDataProtectionPolicy`, `TagResource` sur
`/aws/bedrock-agentcore/runtimes/<runtimeId>-DEFAULT`. Delete = no-op.

- Propriétés : `RuntimeId` et le SHA-256 du fichier de policy, pour relancer l'Update si l'un change.
- La policy vit dans un seul fichier commité `config/log_data_protection_policy.json` (dont les 2
  identifiants custom CampusCoachPassword et BasicAuthHeader). `tag_agentcore_resources.py` et le
  custom resource le lisent. Un test vérifie l'égalité avec le document inline actuel.
- Permissions logs du Lambda limitées à `/aws/bedrock-agentcore/runtimes/*`.

**Écriture mémoire de `coach_chat`.** Nouvelle variable `MEMORY_WRITE_ENABLED`, fermée par défaut :
écriture seulement si la valeur vaut exactement `"true"`. Log « désactivé » une seule fois au
démarrage. Tests : absente, `"false"`, `"true"`, `"True"`.

**Contrôle de parité.** Script qui compare `get-agent-runtime` green et blue champ par champ (env,
entryPoint, runtime, protocole, réseau, authorizer, requestHeaderConfiguration, lifecycle).
Différences admises : nom, rôle, artefact, et `MEMORY_WRITE_ENABLED` (`"false"` avant bascule,
`"true"` à la bascule). Toute autre différence = échec.

**Bascule.** `deploy.sh --flip <agent>` et `--rollback <agent>` :

- Carte des stacks consommateurs tirée du synth (ARN sentinelle distinct par agent, scan des
  templates), testée dans les deux sens. Aujourd'hui : `content_gen` → Content + API ;
  coach → Content seulement ; `coach_chat` → `config.json` du frontend seulement.
- Sauvegarde du contexte, écriture atomique du nouvel ARN + `agentcore.previous.<agent>`.
- Deploy des stacks concernés seulement, un par un (`cdk deploy <stack> --exclusively`).
- En cas d'échec : contexte restauré, redeploy en ordre inverse des stacks déjà passés, puis
  contrôle de chaque variable d'env Lambda (et de l'IAM là où il est exact ; Content garde
  `runtime/*`). Le stack en échec doit être en `UPDATE_ROLLBACK_COMPLETE`. Si le retour échoue
  (ou `UPDATE_ROLLBACK_FAILED`) : arrêt, manifeste de récupération (stack → ARN réel), code 2.
- `coach_chat` : remplacement atomique de `config.json` sur S3, invalidation CloudFront, contrôle de
  la valeur servie. Retour arrière = restauration du VersionId sauvegardé.
- Test d'intégration avec un faux exécuteur : consommateur 1 OK, consommateur 2 KO → tout revient à blue.

**Désinstallation.** `uninstall.sh` liste les 8 stacks de `app.py` + Agents, supprime via
`aws cloudformation delete-stack` dans l'ordre des dépendances (`cdk list`), Agents avant les stacks
dont il importe des exports. Pas de mode spécial côté synth.

### 3. Green `content_gen` sans trafic

- Déployer le stack Agents avec le seul `content_gen` green.
- Invocations directes du runtime green avec le payload de la Lambda, sur 3 à 5 activités passées.
  Comparer avec blue en preview Lambda. Le runtime `content_gen` ne fait que lire la mémoire (hook
  désactivé dans `src/agents/content_agent.py`).
- Logs : `Loaded N preference records` présent, aucun refus IAM, cold start correct.
- Gates : parité OK, masquage présent sur le groupe de logs green.

### 4. Bascule `content_gen`

Sur go explicite. `--flip content_gen`, preview Lambda, puis 48 h d'exécutions réelles. La première
publication réelle est la prochaine sortie. Smoke lancé une fois sur blue (`--agent-arn`) pour
prouver que le retour arrière marche.

### 5. Coach, puis `coach_chat`

- Coach : test par invocation directe du runtime green seulement. La Lambda `coach_generator` écrit
  en mémoire et n'a pas de preview : la première exécution après bascule est réelle, retour arrière
  = ARN.
- `coach_chat` : green avec `MEMORY_WRITE_ENABLED=false`, test SSE avec un vrai ID token Cognito,
  puis passage à `"true"` (nouvelle version), une question courte, puis bascule de `config.json`.
  Blue reste en ligne pour les onglets déjà ouverts.
- `smoke_models.py` étendu pour couvrir `coach_chat` avec un token.

### 6. Nettoyage (après 2 semaines vertes, sur go)

Allowlist explicite qui refuse l'id mémoire. Suppression des runtimes blue, des rôles toolkit, des
anciens objets du bucket toolkit, puis des deux scripts toolkit. L'IAM des Lambdas peut alors passer
de `runtime/*` aux ARNs exacts (forme runtime et runtime-endpoint), avec les stacks concernés
ajoutés à la carte de bascule. `deploy.sh dev` déploie alors tout, smoke en fin.

## Points non prouvés à vérifier pendant l'implémentation

- Limite de taille décompressée du direct code deploy.
- Résolution de `bin/opentelemetry-instrument` installé par `uv --target` dans le runtime.
- Moment exact où AgentCore crée le groupe de logs du runtime.
- Forme d'ARN exigée par `InvokeAgentRuntime` si l'IAM passe en ARNs exacts.
