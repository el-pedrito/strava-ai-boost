# AgentCore — Améliorations de l'aspect agentic

**Date :** 2026-07-10 (validé contre doc officielle AgentCore + Strands le 2026-07-10)
**Statut :** Proposition (aucune implémentation démarrée)
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

**Alternative légère** (si on garde la Lambda Starlette) — **étudiée et amendée
le 2026-07-15** : l'idée initiale (`get_last_k_turns` de la memory avant chaque
`converse_stream`) est **rejetée** — `write_chat_to_memory` filtre volontairement
les tours courts (question < 20 chars, réponse < 100 chars, tronquée à 500),
donc l'historique en memory est lossy et manque précisément les follow-ups.
Décision : l'historique est fourni par le frontend (qui le construit déjà pour
le chemin buffered) et normalisé côté serveur. Plan détaillé, contrat du helper
et analyse sécurité : [a2a-multi-turn-chat.md](./a2a-multi-turn-chat.md).

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

- **Guardrail `9vaecu56g20r` en version `DRAFT`** — à publier en version numérotée.
- **Rule EventBridge legacy `StravaAIBoost-CampusCoach-DailyExtraction`**
  (lundi 05:00 UTC, Browser Tool) tourne encore en parallèle du sync REST
  quotidien `strava-ai-boost-campus-coach-daily-sync`. À désactiver si le
  fallback Browser Tool n'est plus nécessaire.
  ⚠️ `configuration_api.py` a une policy IAM Enable/DisableRule sur cette rule
  (toggle du module Campus Coach) — à migrer vers la nouvelle rule avant suppression.
- **Runtime `campus_coach`** conservé en fallback alors qu'il n'est plus invoqué
  par le flux nominal (remplacé par `campus_coach_sync.py` depuis mai 2026).
- **⚠️ Toolchain déprécié** : le projet utilise
  `bedrock-agentcore-starter-toolkit` (pip) + `.bedrock_agentcore.yaml`
  (`requirements.txt`, `scripts/deploy_agentcore_agents.sh`). AWS l'a déprécié
  au profit du CLI `agentcore` (npm `@aws/agentcore`, config
  `agentcore/agentcore.json`, déploiement CDK). Le SDK runtime
  `bedrock-agentcore` (utilisé dans `src/agents/*.py`) reste inchangé — seule
  la partie scaffolding/déploiement migre. À planifier avant que le toolkit
  pip ne casse.

---

## Recommandation

Priorisation détaillée et séquencement : voir [ROADMAP.md](../ROADMAP.md)
(section « Chantier agentic AgentCore », items A1-A5). En résumé : release
open-source v0.1.0 d'abord, puis l'alternative légère du point 2
(`get_last_k_turns`, ~1 j), puis les tools (point 1, ~1 sem), puis
Evaluations en régression. La refonte streaming complète (point 2) et la
stratégie memory (point 3) seulement si le besoin se confirme après les tools.
