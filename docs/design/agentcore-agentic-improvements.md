# AgentCore — Améliorations de l'aspect agentic

**Date :** 2026-07-10 (validé contre doc officielle AgentCore + Strands le 2026-07-10)
**Statut :** Implémenté pour A1/A2a/A2b/A2b-bis/A3/A4 (mis à jour le 2026-07-17) — voir [ROADMAP.md](../ROADMAP.md) § Chantier agentic. Ce document reste la trace des études et décisions.
**Contexte :** Revue des 3 agents AgentCore (`content_gen`, `strava_ai_boost_coach`, `campus_coach`) et des deux chemins conversationnels (buffered `/coach/ask` + streaming AG-UI).

---

## Constat

Les "agents" n'ont **aucun tool**. Tout le contexte est pré-assemblé en Python
(`shared/coach_context.py`, `coach_generator.py`) puis injecté dans le prompt
(context stuffing), et le LLM fait un seul passage. AgentCore sert surtout de
wrapper de prompt. C'est robuste et prédictible, mais c'est là que se trouve la
marge agentic : l'agent ne peut répondre qu'aux questions dont la donnée est
déjà dans le dump de contexte.

---

## Spec d'implémentation A1+A2b (validée le 2026-07-16, deep dive + tests réels)

> Fusion des chantiers 1 et 2 ci-dessous, décidée après étude doc-first,
> tests protocolaires réels et challenge. Les sections 1 et 2 restent la
> motivation ; cette section est la spec d'exécution.

### Décisions (avec preuves)

| Décision | Justification |
|---|---|
| **MCP Strava officiel : ÉCARTÉ (watch item)** | Testé en réel : OAuth 2.1 + PKCE obligatoire, DCR fermé (400 sur tous payloads dont SDK), allowlist `client_id` → `{"resource":"MCP Authorize","field":"client_id","code":"invalid"}` avec l'app existante. FAQ officielle : Claude-only volontairement. Re-tester quand Strava ouvrira. |
| **Gateway : ÉCARTÉ** | Sans MCP externe à fronter, aucun cas d'usage (1 agent, 4 tools, mono-user). Noté : Gateway supporte désormais le 3LO vers targets mcpServer (doc `gateway-target-MCPservers`) — utile le jour où le MCP Strava ouvrira. |
| **`get_strava_streams` : ÉCARTÉ** | Les laps (DynamoDB) couvrent le besoin coach ; le decoupling vient d'Intervals.icu. Code de fetch streams existant (`enduraw_module.py`) reste dispo si besoin futur. |
| **Runtime dédié `coach_chat`** (pas de réutilisation du runtime coach) | Conflits vérifiés : 1 protocole par runtime (pipeline=HTTP JSON vs chat=AGUI SSE) et 1 authorizer (pipeline=IAM SigV4 vs navigateur=customJWT). Même codebase, deux ressources. |
| **Appel navigateur DIRECT au data plane** (pas de proxy Lambda) | CORS testé sur `bedrock-agentcore.us-east-1.amazonaws.com` : `access-control-allow-origin: *`, header `authorization` autorisé, POST OK. Invalide le ⚠️ de la roadmap. |
| **Région us-east-1** | Runtimes existants déjà en us-east-1 (`.bedrock_agentcore.yaml`), comme Cognito/DynamoDB/frontend. |
| **Runtime AGUI plutôt que garder la Lambda Starlette** | Les tool loops Strands ne streament pas via `converse_stream` simple (la raison d'être d'A2b dans la roadmap) ; le protocole AGUI est supporté nativement par Runtime avec intégration Strands first-party (`ag-ui-strands`, doc `runtime-agui`) et les événements émis sont exactement ceux que le frontend parse déjà. Bonus : sessions runtime, observabilité GenAI dashboard, suppression du vendoring Starlette/uvicorn. |
| **Auth navigateur : Bearer JWT Cognito plutôt que SigV4** | Le frontend détient déjà le JWT (login existant) ; le customJWT authorizer du runtime le valide directement. Supprime toute la machinerie SigV4 (Identity Pool, signing @aws-crypto, credentials temporaires) — moins de code, moins de surface d'erreur, mêmes garanties (authentifié, scoped au User Pool). |
| **Tools plutôt que context stuffing (chat uniquement)** | Le stuffing fige le contexte : « compare mes 6 séances de seuil » échoue car la donnée n'est pas dans le dump. L'agent va chercher exactement ce dont il a besoin, quand il en a besoin. Le pipeline feedback garde le stuffing déterministe (reproductible, testable — principe roadmap inchangé). |
| **Bascule en 2 phases plutôt que big bang** | Le chat est une feature utilisée au quotidien ; les chemins actuels (Starlette + buffered, tous deux fonctionnels post-A2a) servent de filet pendant la validation réelle du nouveau chemin. Décommission seulement après preuve d'usage. |
| **Guardrail sur le chat (recommandé)** | Écart documenté au threat model (T4 : le chat passe aujourd'hui par `converse_stream` sans guardrail, contrairement au pipeline content). Le passage par Runtime est l'occasion de le combler à coût quasi nul (le guardrail existe déjà). |

### Architecture

```
CoachChat.tsx ──POST SSE, Authorization: Bearer <JWT Cognito>──> Runtime coach_chat (--protocol AGUI, customJWT → User Pool existant)
                                                                   └─ FastAPI :8080 /invocations + /ping (ag-ui-strands, pin version)
                                                                      └─ Agent Strands (Claude Sonnet 4.5) [+ Guardrail existant — comble T4]
                                                                         ├─ @tool query_activities / get_campus_plan / get_pace_zones / get_intervals_metrics
                                                                         └─ Memory coaching_observations (existante) + write_chat_to_memory
```

> **As-built (2026-07-17)** : 5 tools au final (`get_coach_observations`
> ajouté pour la continuité chat↔pipeline) ; la lecture memory ne passe pas
> par le namespace `coaching_observations` (jamais alimenté — cf. audit
> [memory-improvements.md](./memory-improvements.md)) mais par les namespaces
> unifiés `/strategies/{strategyId}/actors/{actorId}/`.

- `user_id` extrait du **claim JWT `custom:strava_id`** (plus le body client)
- Multi-tour : `RunAgentInput.messages` natif AG-UI (transpose A2a côté serveur)
- Context stuffing minimal (profil) ; le reste via tools — le cœur d'A1
- **UX tool loops** : le frontend affiche les événements `TOOL_CALL_*`
  (« analyse de tes activités… ») pour couvrir les 3-8 s avant le premier token
- Runtime `coach_agent` existant : **inchangé, redevient pipeline-only**
  (le chat buffered `_invoke_coach_session` migre vers `coach_chat`)

### Plan (3-4 j, bascule en 2 phases)

1. **Agent** (`src/agents/coach_chat_agent.py`, 1 j) : Agent Strands + 4 `@tool`
   (logique portée de `coach_context.py`/`coach_ask_api.py`) + wrapper
   `ag-ui-strands` + FastAPI. Test local : `curl -N` SSE sur :8080.
2. **Deploy** (0.5 j) : `agentcore configure -e … --protocol AGUI` + customJWT
   (discovery URL User Pool + client id), execution role (DynamoDB read ×3,
   Secrets Intervals, Bedrock, Memory), intégré à `deploy_agentcore_agents.sh`.
3. **Frontend** (1 j) : transport SSE direct + Bearer JWT dans `coachStream.ts`
   (supprime le signing SigV4), payload AG-UI, affichage `TOOL_CALL_*`.
   Flag config `coachRuntimeArn` — chemins actuels en fallback (phase A).
4. **Tests réels + tuning prompt** (1 j).
5. **Phase B — décommission** (0.5 j) : Lambda `coach_stream`, Function URL,
   Identity Pool SigV4, `coach_ask_api` + nettoyage CDK. Le helper A2a
   `build_converse_messages` part avec le chemin Starlette (durée de vie
   courte assumée ; son fix du buffered aura servi toute la phase A).

### Risques assumés

- Cold start runtime (pattern retry connu du projet) ; latence tool loops
  (mitigée par l'affichage des tool calls) ; coût ×2-4 appels LLM par question
  (négligeable au volume) ; `ag-ui-strands` v0.1 (pin + tests locaux).

### Notes de déploiement (customJWT authorizer — issues de la review)

- Le frontend envoie l'**ID token** Cognito (seul porteur du claim
  `custom:strava_id`). L'ID token a une claim `aud` (= app client id), pas
  `client_id` : configurer l'authorizer avec **`allowedAudience`** (et non
  `allowedClients`).
- **Exiger le claim `custom:strava_id`** dans l'authorizer (custom claims,
  cf. §5) : sans cela, tout JWT valide du pool sans le claim retombe
  silencieusement sur `DEFAULT_USER_ID` (fallback actif en prod, documenté
  dans le code — acceptable mono-user mais à verrouiller).
- Env vars du runtime : `GUARDRAIL_ID`/`GUARDRAIL_VERSION` (guardrail branché
  nativement via Strands `BedrockModel`), tables DynamoDB, `MEMORY_ID`,
  `DEFAULT_USER_ID`.
- Comportement fallback frontend (phase A) : si `coachRuntimeArn` est défini et
  que le runtime échoue, le fallback va **directement au buffered** `/coach/ask`
  (le chemin SigV4 legacy n'est plus tenté — de facto mort dès que le flag est
  posé ; sa suppression est la phase B).

## 1. Donner des tools au coach conversationnel — **impact le plus fort**

**Problème :** dans `src/agents/coach_agent.py` (mode `conversation`) et
`lambda_functions/coach_stream/app.py`, la question de l'athlète est arbitraire
mais le contexte est figé (dernières activités + plan Campus). Des questions comme
« Compare mes 6 dernières séances de seuil » ou « quelle était ma FC moyenne en
côte le mois dernier » échouent car la donnée n'est pas dans le dump.

**Solution :** avec Strands, déclarer des tools et laisser l'agent chercher ce
dont il a besoin :

```python
@tool
def query_activities(activity_type: str, date_from: str, date_to: str) -> list:
    """Requête DynamoDB (UserActivitiesIndex) filtrée par type et période."""

@tool
def get_campus_plan(week_iso: str) -> dict:
    """Séances Campus Coach d'une semaine donnée (table coaching-sessions)."""

@tool
def get_pace_zones() -> dict:
    """Zones d'allure + records personnels depuis user-configuration."""

@tool
def get_intervals_metrics(date_from: str, date_to: str) -> dict:
    """CTL/ATL/Form/HRV depuis les données Intervals.icu stockées."""
```

Garder un context stuffing minimal (profil athlète) ; l'agent complète à la
demande via les tools. Changement contenu dans `coach_agent.py` + IAM du
runtime coach (lecture DynamoDB).

> ✅ Validé (doc Strands) : `@tool` sur fonction Python avec docstring + type
> hints génère la spec automatiquement ; `Agent(tools=[...])` suffit. Pattern
> « agents as tools » disponible plus tard si besoin d'orchestration.

## 2. Unifier le streaming via AgentCore Runtime

**Problème :** deux chemins parallèles aujourd'hui :

| Chemin | Transport | Session multi-tours | Memory |
|---|---|---|---|
| Buffered `/coach/ask` | API GW → Lambda → AgentCore Runtime (`runtimeSessionId`) | ✅ | ✅ |
| Streaming AG-UI | Function URL → Starlette → `converse_stream` direct | ❌ | écriture seule |

Le chemin streaming n'a **pas d'historique de conversation** : chaque question
est indépendante (le follow-up « et pourquoi ? » ne sait pas de quoi on parle).

**Solution :** AgentCore Runtime supporte les réponses streamées (entrypoint
async générateur + Strands `stream_async`). Faire streamer le coach agent
lui-même et mapper sur les événements AG-UI existants. Gains : sessions
multi-tours + memory + observabilité GenAI dashboard, et suppression du chemin
Lambda Web Adapter dupliqué.

> ✅ Validé (doc AgentCore Runtime) : pattern officiel documenté —
> `@app.entrypoint` async qui `yield` les events de `agent.stream_async()` ;
> le runtime sert du SSE sur `/invocations`. AgentCore supporte même un
> protocole **AGUI natif** (SSE sur port 8080), ce qui colle exactement à notre
> frontend AG-UI. Sessions : `runtimeSessionId` (33+ chars, déjà respecté par
> `coach_ask_api.py`), idle timeout 15 min, max 8 h.
>
> ⚠️ Point d'attention : le côté **client** doit consommer le stream de
> `invoke_agent_runtime` (boto3) et le relayer — soit la Lambda AWS_IAM
> Function URL actuelle devient un simple proxy runtime→SSE, soit on invoque
> le runtime directement depuis le frontend (SigV4 déjà en place via Identity
> Pool). À prototyper avant de supprimer le chemin Starlette.

**Alternative légère — A2a (plan validé le 2026-07-15, à faire AVANT la refonte
Runtime)** : on garde la Lambda Starlette et on rend le chat multi-tour.

L'idée initiale (`get_last_k_turns` de la memory avant chaque `converse_stream`)
est **rejetée après étude** : `write_chat_to_memory` filtre volontairement les
tours courts (question < 20 chars, réponse < 100 chars, tronquée à 500 — filtres
qui protègent la qualité de l'extraction LTM), donc l'historique en memory est
**lossy** et manque précisément les follow-ups. Décision : **l'historique est
fourni par le frontend** (qui le construit déjà — `messages.slice(-10)` dans
`CoachChat.tsx` — mais ne l'envoie aujourd'hui qu'au chemin buffered) et
**normalisé côté serveur**. `write_chat_to_memory` reste inchangé (rôle LTM).

Plan (5 changements, zéro CDK/IAM) :

1. **`shared/coach_context.py`** — helper pur `build_converse_messages(history,
   current_question)` : whitelist stricte des rôles `{user, assistant}` (bloque
   le smuggling de rôle `system` par le client), cap 10 messages, troncature
   asymétrique 500 chars/user et 2500 chars/assistant, drop du leading
   assistant + merge des rôles consécutifs (contrainte Converse Claude :
   1er message `user`, rôles alternés), historique invalide → dégradation
   silencieuse en single-turn.
2. **`coach_stream/app.py`** — consommer `body.history` ; contexte athlète
   déplacé dans le paramètre `system` (données serveur séparées des `messages`
   client, meilleure isolation anti-injection — cohérent threat model T4).
3. **`api/coach_ask_api.py`** — `_fallback_bedrock` refactoré sur le même
   helper (aujourd'hui : aucune validation du `history`, alternance non
   garantie — bug latent).
4. **Frontend** (~3 lignes) — ajouter `history` à `CoachStreamRequest`
   (`coachStream.ts`) et à l'appel dans `CoachChat.tsx`.
5. **Tests** — unitaires du helper (alternance, merge, drop, troncature, rôles
   invalides, vide) + non-régression des 3 tests AG-UI de
   `test_coach_stream.py`.

## 3. Memory : passer d'événements bruts à une stratégie

**Problème :** `write_coaching_observation` (`coach_generator.py`) écrit du
texte tronqué à 1000 chars comme événement conversationnel brut, et la
retrieval query est statique (`"recent coaching observations and athlete
patterns"`).

**Solutions :**
- Ajouter une stratégie (semantic ou custom) sur le namespace
  `coaching_observations` pour que la memory **consolide** au lieu d'accumuler
  (comme `StravaContentPreferences` le fait déjà pour le contenu).
- Rendre la `searchQuery` dynamique selon le type d'activité analysée
  (intervalles vs sortie longue vs renfo).

> ✅ Validé (guide Memory) : 4 stratégies built-in — SEMANTIC, SUMMARIZATION,
> USER_PREFERENCE, **EPISODIC** (avec `reflectionNamespaces`). Pour des
> observations coaching par séance, EPISODIC est un candidat naturel
> (namespace `users/{actorId}/episodes/{sessionId}` + réflexions consolidées).
> Vérifier les jobs d'extraction avec `list_memory_extraction_jobs` — si la
> stratégie est ajoutée mais qu'aucun record long-terme n'apparaît, c'est le
> premier endroit à regarder.

## 4. AgentCore Gateway (optionnel, après 1–3)

Les 3 agents + la Lambda de stream dupliquent les accès DynamoDB / Strava /
Intervals.icu. Un Gateway avec targets Lambda exposerait ces capacités comme
tools MCP partagés — un seul endroit à maintenir, découverte dynamique par les
agents. Pour un projet solo : confort plus que besoin.

---

## 5. Nouvelles briques AgentCore — évaluation de pertinence

> **Re-vérifié le 2026-07-16** contre les dernières annonces, à la lumière de la
> spec A1+A2b : (1) **Policy** doublement écarté — il intercepte les tool calls
> *via Gateway*, qu'on n'utilise pas ; (2) **Evaluations** renforcé — l'évaluateur
> built-in « tools selection » cible exactement la validation du nouvel agent à
> tools (fait d'A3 la suite naturelle d'A1) ; (3) **Runtime streaming
> bidirectionnel** débloque les agents vocaux → le « Coach vocal live (Nova
> Sonic) » du long terme devient faisable sur l'archi coach_chat ; (4) **Identity
> custom claims** : exiger `custom:strava_id` dans le customJWT authorizer du
> runtime (défense en profondeur gratuite, à inclure dans l'implémentation A1+A2b).

### Evaluations — **à prendre** (GA depuis mars 2026)

Répond directement au backlog P1 (« review coach feedback quality », « iterate
on COACH_AGENT_SYSTEM_PROMPT based on real outputs ») qui est aujourd'hui 100%
manuel.

- **Online evaluation** : scoring continu du trafic de prod (chaque feedback
  coach / contenu généré) — 13 évaluateurs built-in (qualité de réponse,
  sécurité, task completion, tool usage).
- **On-demand evaluation** : tests de régression quand on modifie
  `COACH_AGENT_SYSTEM_PROMPT` ou `embedded_prompts.py` — comparer avant/après
  sur un jeu d'activités de référence.
- **Custom evaluators** (LLM-judge ou Lambda Python) : parfait pour nos règles
  maison — vérifier que le `strava_block` parle de tendances et pas de récap
  de séance, absence d'em dash, absence de clichés IA, chiffres hebdo réels.
- S'intègre à AgentCore Observability (déjà en place via la Security stack).

Cas d'usage concret : évaluateur custom « anti-hallucination des totaux
hebdo » — le bug qu'on a corrigé à la main en juin serait détecté
automatiquement.

### Policy (Cedar) — **plus tard, couplé à Gateway**

Autorisation Cedar sur les invocations de tools, attachée à un **Gateway**
(mode `LOG_ONLY` puis `ENFORCE`). Sans Gateway (piste 4) il n'y a rien à
protéger, et en mono-utilisateur le besoin est faible. À revisiter si :
multi-tenant (P3) ou adoption Gateway. Bonus notable : génération de policies
Cedar depuis du langage naturel (assets à promouvoir sous 7 jours).

### Identity — **optionnel, gain modéré**

Token vault (Secrets Manager managé) + credential providers OAuth2/API key +
décorateurs runtime (`@requires_access_token`, `@requires_api_key`) qui
injectent les credentials **sans passer par le contexte LLM**. Pourrait
remplacer notre plomberie maison (`shared/strava_oauth.py`, secrets Campus
Coach / Intervals.icu) — mais cette plomberie fonctionne et le refresh OAuth
Strava est déjà géré. À considérer seulement si on migre les agents vers le
CLI `agentcore` (voir hygiène) : la section `credentials` d'`agentcore.json`
viendrait naturellement à ce moment-là.

### Payments (x402) — **non pertinent** pour ce projet.

---

## Hygiène relevée au passage

> **Mise à jour 2026-07-17 : les 4 items ci-dessous sont résolus** (détail dans la ROADMAP).

- ✅ **Guardrail `<GUARDRAIL_ID>` en version `DRAFT`** — **résolu** : publié en v1 (quick wins 2026-07-10, avec fix au passage d'un fail-open silencieux : le runtime `content_gen` pointait sur un guardrail ID inexistant).
- ✅ **Rule EventBridge legacy `StravaAIBoost-CampusCoach-DailyExtraction`** — **résolue** : supprimée (quick wins 2026-07-10), toggle IAM nettoyé (le sync REST vérifie l'activation module en DynamoDB).
- ✅ **Runtime `campus_coach`** conservé en fallback — **résolu** : décommissionné le 2026-07-16 (runtime + mémoire détruits, Lambda `campus_coach_invoker` supprimée, code/CDK/scripts/tests nettoyés).
- ✅ **« Toolchain déprécié »** — **infirmé** : la « dépréciation » du `bedrock-agentcore-starter-toolkit` (pip) venait des guides MCP, **pas d'une annonce AWS officielle** (vérifié le 2026-07-10, aucune notice publique). Migration vers le CLI `agentcore` (npm) désormais **réactive** seulement (ROADMAP item A5).

---

## Recommandation

Priorisation détaillée, séquencement et état d'avancement : voir
[ROADMAP.md](../ROADMAP.md) (section « Chantier agentic AgentCore »,
items A1-A5). Le séquencement initialement recommandé ici a été **entièrement
réalisé** (2026-07-16/17), avec un amendement : la reco d'origine
« alternative légère via `get_last_k_turns` » était contredite par l'étude du
§2 lui-même (historique memory lossy par design → rejetée) ; A2a a été livré
avec l'historique fourni par le frontend et normalisé serveur-side
(`build_converse_messages`). Ont suivi : tools + runtime AGUI (A1+A2b),
décommission legacy (A2b bis), évals de régression V1+V2 (A3), et l'audit/fix
mémoire (point 3 → réalisé en A4, cf.
[memory-improvements.md](./memory-improvements.md) : 5 tools au final avec
`get_coach_observations`, lecture memory via les namespaces unifiés
`/strategies/`, stratégie EPISODIC ajoutée).
