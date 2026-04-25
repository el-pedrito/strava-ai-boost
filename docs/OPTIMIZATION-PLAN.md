# Strava AI Boost — Plan d'optimisation coûts & personnalisation

> Créé le 25 avril 2026 — Session de diagnostic et planification
> Auteur : Pierre Benard (SA) + Kiro
> Compte AWS : 123456789012 (profil `your-aws-profile`, us-east-1)

---

## 1. Diagnostic — Résumé exécutif

### Coûts avril 2026

| Service | Coût | % total |
|---|---|---|
| Amazon Bedrock Service (Claude 4.5 Sonnet) | $492.89 | 96.3% |
| AmazonCloudWatch | $9.74 | 1.9% |
| Amazon Bedrock AgentCore | $7.39 | 1.4% |
| AWS Secrets Manager | $1.28 | 0.2% |
| Autres (SQS, S3, Lambda, DynamoDB, Step Functions, API GW) | $1.42 | <1% |
| **Total** | **$512.72** | |

### Décomposition Bedrock

| UsageType | Quantité | Coût |
|---|---|---|
| Claude4.5Sonnet input tokens (cross-region global) | 159 364K tokens | $478.09 |
| Claude4.5Sonnet output tokens (cross-region global) | 986K tokens | $14.80 |

Un seul modèle consommé. Pas d'autre modèle (Haiku, etc.).

### Décomposition AgentCore

| Composant | Quantité | Coût |
|---|---|---|
| BrowserTool Memory | 415 GB-hours | $3.92 |
| Short-Term Memory (STM events) | 6 140 events | $1.54 |
| BrowserTool vCPU | 14.7 vCPU-hours | $1.32 |
| Runtime Memory | 44.8 GB-hours | $0.42 |
| Runtime vCPU | 0.64 vCPU-hours | $0.06 |
| LTM Storage | 71 records | $0.05 |
| LTM Retrieval | 33 retrievals | $0.02 |
| Data Transfer | ~5 GB | $0.06 |

### Root cause

**Le Campus Coach Browser Tool** est responsable de 96% des coûts.

Preuves :
- **6 335 invocations Bedrock** en avril pour seulement 60 Lambda invocations
- Corrélation horaire confirmée : le 24 avril, **330 invocations à 5h UTC** (heure du cron) + 1 invocation à 11h (content_gen)
- Session du 25 avril analysée : **273 turns LLM**, dont **2 tentatives** (1ère échoue sur auth après 130 turns, 2ème réussit après 130 turns)
- Aucun `max_turns` configuré dans le code → l'agent boucle sans limite
- Le STM event count (6 140) corrèle avec les invocations Bedrock (6 335) — chaque turn écrit un event mémoire

### Pattern d'une session Campus Coach (25 avril)

```
Tentative #1 (270s, ~130 turns) :
  init_session → navigate(auth) → screenshot → get_html → evaluate(body) 
  → click(Continue with email) → evaluate → click(Log in) → evaluate 
  → type(email) → type(password) → click(submit) → evaluate(url) 
  → ... boucle de retry login ... 
  → ÉCHEC "Authentication failed - password validation failing"

Tentative #2 (392s, ~130 turns) :
  init_session → navigate(auth) → ... même flow ...
  → login réussi → navigate(sessions) → scroll → evaluate 
  → extraction JSON → SUCCÈS (3 sessions sauvées)

Total : 610s, 273 turns, ~$8-10 en tokens
```

### Problèmes secondaires identifiés

1. **Sécurité** : credentials Campus Coach (email + mot de passe) loggés en clair dans les OTEL logs CloudWatch via les arguments du browser tool `type`
2. **Cost tracking impossible** : les cost allocation tags ne fonctionnent pas pour AgentCore (bug connu, confirmé re:Post août 2025). Les Application Inference Profiles ne propagent pas les tags pour les agents.
3. **Prompt caching non activé** : le system prompt content_gen fait 34 917 bytes, identique entre invocations, candidat parfait pour le cache
4. **Memory Strategy utilise Sonnet 4.5** : `configure_memory_strategy.py` utilise `eu.anthropic.claude-sonnet-4-5-20250929-v1:0` pour extraction et consolidation
5. **Hook STM désactivé** dans content_agent.py : la mémoire ne s'enrichit pas en temps réel
6. **CloudWatch custom metrics** : $5.40/mois + dashboards $2.40/mois

---

## 2. Décisions architecturales

### Campus Coach : scrape hebdomadaire + update statut (Option A)

**Contexte** : le plan d'entraînement change 1x/semaine, mais le statut des séances (fait/à faire) change quotidiennement.

**Problème** : `modules_processing.py` filtre avec `status = "À faire"`. Si on scrape 1x/semaine, les séances faites restent "À faire" en DynamoDB → le content_gen matche avec des séances déjà réalisées.

**Solution retenue** :
- Campus Coach scrape **1x/semaine** (lundi 5h UTC) → récupère les 5 séances
- Quand le content_gen matche une activité avec une séance → **update DynamoDB** `status = "Fait"`
- Le filtre `status = "À faire"` fonctionne naturellement le reste de la semaine

**Fichiers impactés** :
- `stacks/webhook_processing_stack.py` ou `stacks/content_generation_stack.py` : modifier le cron EventBridge
- `lambda_functions/processing/content_generator.py` ou `src/agents/content_agent.py` : ajouter l'update DynamoDB après match
- `lambda_functions/processing/modules_processing.py` : vérifier que le flow de match retourne l'ID de la séance matchée

### Langfuse : non retenu

Pas pertinent pour 2 agents. La combo CloudWatch Logs Insights + IAM Principal cost allocation couvre le besoin. À reconsidérer si le projet scale à 10+ agents.

### Cost tracking : IAM Principal cost allocation

Nouvelle feature AWS (13 avril 2026). Capture l'ARN IAM principal sur chaque invocation Bedrock server-side. Les runtimes AgentCore assument des IAM roles différents → visibilité par agent dans CUR 2.0 et Cost Explorer.

---

## 3. Plan d'implémentation

### P0 — Immédiat (ce week-end)

#### P0.1 — Cron Campus Coach → hebdomadaire

**Quoi** : modifier la règle EventBridge de `cron(0 5 ? * * *)` (quotidien) à `cron(0 5 ? * MON *)` (lundi uniquement)

**Où** : `stacks/content_generation_stack.py` ou `stacks/webhook_processing_stack.py` (chercher `StravaAIBoost-CampusCoach-DailyExtraction`)

**Impact coût** : -$458/mois (de ~$478 à ~$20)

**Risque** : statuts séances pas à jour → mitigé par P0.2

**Test** : vérifier que le cron se déclenche le lundi suivant, vérifier les logs

#### P0.2 — Update statut DynamoDB après match séance

**Quoi** : quand le content_gen matche une activité Strava avec une séance Campus Coach, marquer la séance `status = "Fait"` dans la table `strava-ai-boost-campus-coaching-sessions`

**Où** :
- `lambda_functions/processing/modules_processing.py` : la fonction `_apply_campus_coach_processing()` retourne les sessions matchées
- `src/agents/content_agent.py` ou `lambda_functions/processing/content_generator.py` : après génération réussie, si une séance a été matchée, update DynamoDB

**Logique** :
```python
# Après que le content_gen a matché une séance
if matched_session_id:
    table = dynamodb.Table(COACHING_SESSIONS_TABLE)
    table.update_item(
        Key={'session_date': session_date, 'session_id': matched_session_id},
        UpdateExpression='SET #status = :done, completed_at = :ts, matched_activity_id = :aid',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':done': 'Fait',
            ':ts': datetime.now(UTC).isoformat(),
            ':aid': activity_id
        }
    )
```

**Complexité** : le match est fait par l'agent (sémantique), pas par le code Python. Il faut que l'agent retourne l'ID de la séance matchée dans sa réponse, ou parser la réponse pour l'extraire.

**Risque** : faux match → une séance marquée "Fait" alors qu'elle ne l'est pas. Mitigé par le fait que le scrape hebdo remet à jour les statuts depuis Campus Coach.

**Test** : déclencher manuellement un webhook pour une activité qui correspond à une séance "À faire", vérifier que le statut passe à "Fait"

#### P0.3 — `max_turns=150` sur Campus Coach Agent

**Quoi** : ajouter le paramètre `max_turns=150` au constructeur `Agent()` dans `campus_coach_agent.py`

**Où** : `src/agents/campus_coach_agent.py`, ligne ~155 (dans `scrape_campus_sessions`)

**Avant** :
```python
agent = Agent(
    model=model,
    tools=[browser_tool.browser],
    system_prompt=CAMPUS_COACH_PROMPT,
    hooks=[AgentCoreMemoryHook()] if MEMORY_ID else [],
    state={...}
)
```

**Après** :
```python
agent = Agent(
    model=model,
    tools=[browser_tool.browser],
    system_prompt=CAMPUS_COACH_PROMPT,
    hooks=[AgentCoreMemoryHook()] if MEMORY_ID else [],
    max_turns=150,
    state={...}
)
```

**Justification du chiffre** : session réussie = ~130 turns. 150 donne 15% de marge. Si l'agent atteint 150 turns sans résultat, c'est qu'il boucle.

**Risque** : si Campus Coach change son UI et que le scraping nécessite plus de steps → échec. Mais 150 est déjà très généreux.

**Test** : vérifier que le scraping fonctionne toujours après le changement

#### P0.4 — Fix retry auth

**Quoi** : si la 1ère tentative échoue sur "Authentication failed", ne pas relancer une 2ème tentative. Envoyer une alerte SNS à la place.

**Où** : `src/agents/campus_coach_agent.py`, dans `scrape_campus_sessions()`, après le parsing JSON

**Logique** :
```python
sessions_data = json.loads(json_text)

# Si auth failed, ne pas retenter
if sessions_data.get('error') and 'authentication' in sessions_data['error'].lower():
    logger.error(f"❌ Auth failed, not retrying: {sessions_data['error']}")
    # Publier alerte SNS
    sns = boto3.client('sns', region_name=region)
    sns.publish(
        TopicArn=os.environ.get('ALERT_TOPIC_ARN', ''),
        Subject='Campus Coach: Authentication Failed',
        Message=f"Login failed: {sessions_data['error']}"
    )
    return {"success": False, "error": sessions_data['error'], "retry": False}
```

**Note** : vérifier comment le retry est actuellement implémenté. D'après les logs, il semble que le Lambda invoker appelle 2x le runtime, pas que le code interne retente.

**Risque** : si l'échec est transitoire (timeout réseau), on perd le scrape de la semaine. Acceptable car le scrape suivant est lundi prochain.

**Test** : simuler un échec d'auth et vérifier qu'il n'y a pas de 2ème tentative

#### P0.5 — IAM Principal cost allocation

**Statut** : ✅ Partiellement fait (2026-04-25)

**Fait automatiquement** :
- IAM execution roles des 2 runtimes AgentCore tagués avec `agent={campus_coach|content_gen}`, `Project`, `CostCenter`, `ManagedBy`
- Script `scripts/deploy_agentcore_agents.sh` étendu pour tagger aussi les IAM roles à chaque deploy (fonction `tag_agentcore_resources`)

**Reste à faire manuellement (console AWS)** :
1. **Billing Console → Cost Allocation Tags → User-defined tags** : activer les tags `agent`, `Project`, `CostCenter` (si pas déjà). Délai : 24-48h avant apparition dans Cost Explorer.
2. **Billing Console → Data Exports → Create export** : créer un CUR 2.0 export et cocher **"Include resource IDs"** + **"Include resource tags"** + **"Split cost allocation data"**. Pour capturer l'ARN du principal IAM qui invoque Bedrock, utiliser la colonne `line_item_resource_id` côté data plane Bedrock.
3. Alternative plus simple : utiliser **Cost Explorer → Group by → Tag: agent** une fois les tags activés. Les coûts Bedrock n'apparaîtront pas groupés par agent sans CUR 2.0, mais les coûts AgentCore (runtime, browser tool, memory) seront groupés correctement.

**Limitation connue** : les tags `agent` sur IAM roles ne propagent PAS aux invocations Bedrock sous-jacentes. Pour ça il faut vraiment la feature **IAM Principal data in CUR 2.0** (annoncée 13 avril 2026) activée dans un export CUR 2.0.

**Roles tagués** :
```
AmazonBedrockAgentCoreSDKRuntime-us-east-1-XXXXXXXXXXXX → agent=campus_coach
AmazonBedrockAgentCoreSDKRuntime-us-east-1-XXXXXXXXXXXX → agent=content_gen
```

#### P0.6 — Campus Coach → Claude 4.5 Haiku

**Quoi** : changer le modèle du Campus Coach de `global.anthropic.claude-sonnet-4-5-20250929-v1:0` vers `global.anthropic.claude-4-5-haiku-20250414-v1:0`

**Où** : `src/agents/campus_coach_agent.py` (env var `BEDROCK_MODEL_ID` dans `.bedrock_agentcore.yaml` ou dans la stack CDK)

**Impact** : Haiku 4.5 = $0.80/M input, $4/M output vs Sonnet 4.5 = $3/M input, $15/M output. ~4x moins cher. Session hebdo ~130 turns × ~25K tokens avg = ~3.25M tokens/semaine × $0.80/M = ~$2.60/semaine = **~$10.40/mois** (vs ~$40 avec Sonnet hebdo).

**Pourquoi Haiku 4.5 et pas 3.5** : Haiku 4.5 est significativement meilleur que 3.5 pour le raisonnement et le tool use. Le pilotage browser nécessite de comprendre le DOM, décider quoi cliquer, gérer les erreurs de login. Haiku 4.5 est le bon compromis coût/capacité.

**Fallback** : si Haiku 4.5 échoue sur le scraping, revenir à Sonnet 4.5 mais garder le `max_turns=150` + cron hebdo.

**Test** : invoquer manuellement le Campus Coach avec Haiku 4.5 et vérifier que le scraping réussit.

---

### P1 — Cette semaine

#### P1.1 — ~~Campus Coach → Haiku 3.5~~ → **Déplacé en P0.6**

Voir P0.6 ci-dessus. Modèle retenu : **Claude 4.5 Haiku** (pas 3.5).

#### P1.2 — Prompt caching content_gen

**Quoi** : activer le prompt caching Bedrock sur le system prompt du content_gen (34 917 bytes, identique entre invocations)

**Où** : `src/agents/content_agent.py` — ajouter les cache breakpoints dans l'appel Converse API

**Doc** : https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html

**Impact** : -90% sur les input tokens du system prompt (les ~9K tokens de system prompt sont cachés, seuls les ~3K tokens du user prompt sont facturés full price)

**Risque** : faible. Le cache expire après 5 minutes d'inactivité. Avec ~11 invocations/mois (pas quotidien), le cache sera souvent froid. Impact réel probablement -30% plutôt que -90%.

**Note** : vérifier si Strands SDK supporte nativement le prompt caching ou s'il faut passer par le Converse API directement.

#### P1.3 — Fix credentials en clair dans OTEL logs

**Quoi** : les credentials Campus Coach (email + mot de passe) apparaissent dans les OTEL logs CloudWatch via les arguments du browser tool `type(password)`

**Options** :
- A) Injecter les credentials via un cookie/localStorage pré-configuré dans le Browser Profile (feature AgentCore Browser depuis avril 2026)
- B) Filtrer les logs OTEL pour masquer les champs sensibles (CloudWatch log subscription filter)
- C) Modifier le prompt pour que l'agent utilise un mécanisme d'auth différent (API token si dispo)

**Risque** : si quelqu'un accède aux logs CloudWatch, il a les credentials Campus Coach

---

### P2 — Ce mois

#### P2.1 — Réduire le system prompt

**Quoi** : déplacer les dictionnaires statiques du `embedded_prompts.py` (AGE_CONTEXT, INTEREST_EXPRESSIONS, SPORT_APPROACH_EXAMPLES, ~8K chars) vers la mémoire LTM ou le code Python `build_profile_context()`

**Impact** : -20% input tokens sur content_gen

#### P2.2 — Améliorer la personnalisation

**Quoi** :
- Réactiver le hook STM dans content_agent.py
- Créer des namespaces séparés par type de préférence (style, contenu, sport)
- Implémenter un "style fingerprint" évolutif basé sur les diffs feedback

#### P2.3 — Memory Strategy → Haiku

**Quoi** : changer le modèle dans `configure_memory_strategy.py` de Sonnet 4.5 vers Haiku pour extraction et consolidation

#### P2.4 — Cleanup CloudWatch

**Quoi** : réduire les custom metrics ($5.40/mois) et supprimer le dashboard s'il n'est pas utilisé ($2.40/mois)

---

## 4. Projection coûts

| Scénario | Bedrock | AgentCore | CloudWatch | Autres | Total |
|---|---|---|---|---|---|
| **Actuel** | $493 | $7 | $10 | $3 | **$513** |
| **Après P0** (hebdo + Haiku 4.5 + fix retry + max_turns) | ~$12 | ~$1 | $10 | $3 | **~$26** |
| **Après P1** (+ prompt caching) | ~$8 | ~$1 | $10 | $3 | **~$22** |
| **Après P2** (+ prompt réduit + CW cleanup) | ~$6 | ~$1 | ~$2 | $3 | **~$12** |

---

## 5. Métriques de succès

| Métrique | Actuel | Cible P0 | Cible P1 | Cible P2 |
|---|---|---|---|---|
| Coût mensuel total | $513 | <$50 | <$20 | <$12 |
| Invocations Bedrock/mois | 6 335 | <800 | <800 | <800 |
| Turns Campus Coach/session | 273 (avec retry) | <150 | <150 | <150 |
| Visibilité coûts par agent | ❌ | ✅ (IAM Principal) | ✅ | ✅ |
| Séances Campus Coach à jour | ⚠️ (quotidien mais auth fail) | ✅ (hebdo + status update) | ✅ | ✅ |
| Credentials en clair dans logs | ❌ | ❌ | ✅ (fixé) | ✅ |

---

## 6. Références

- [Bedrock IAM Principal cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/iam-principal-cost-allocation.html) — sorti 13 avril 2026
- [Bedrock Projects](https://aws.amazon.com/blogs/machine-learning/manage-ai-costs-with-amazon-bedrock-projects/) — 7 avril 2026 (non retenu, API OpenAI-compatible only)
- [Bedrock prompt caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [AgentCore Observability avec Langfuse](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-observability-with-langfuse/) — non retenu pour l'instant
- [Cost tracking multi-tenant Bedrock](https://aws.amazon.com/blogs/machine-learning/cost-tracking-multi-tenant-model-inference-on-amazon-bedrock/) — requestMetadata Converse API
- [re:Post — Agent tags not showing in Cost Explorer](https://repost.aws/questions/QUrOgFusewSaCAvERQ7h0R-w) — bug confirmé
- [AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
