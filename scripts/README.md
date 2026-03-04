# Scripts de Déploiement et Maintenance - Strava AI Boost

Ce dossier contient tous les scripts nécessaires pour déployer, configurer, maintenir et désinstaller Strava AI Boost.

## 📋 Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Scripts de Déploiement](#scripts-de-déploiement)
- [Scripts de Configuration](#scripts-de-configuration)
- [Scripts de Maintenance](#scripts-de-maintenance)
- [Scripts de Validation](#scripts-de-validation)
- [Scripts de Désinstallation](#scripts-de-désinstallation)
- [Workflows Complets](#workflows-complets)
- [Dépannage](#dépannage)

---

## Vue d'Ensemble

### Architecture en 2 Phases

**Phase 1 - Infrastructure CDK (Obligatoire)**
- Déploiement de l'infrastructure AWS complète
- Lambda, DynamoDB, Step Functions, API Gateway
- Mode Bedrock fallback (Claude Sonnet 4.5 direct)
- Système entièrement fonctionnel

**Phase 2 - AgentCore Enhancement (Optionnel)**
- Agents AgentCore avec mémoire persistante
- Personnalisation avancée du contenu
- Apprentissage du style utilisateur
- Fallback automatique si AgentCore indisponible

### Prérequis

```bash
# Variables d'environnement requises
export AWS_PROFILE=your-aws-profile
export AWS_REGION=eu-west-1

# Outils requis
- AWS CLI v2+
- AWS CDK v2+
- Python 3.12+
- Node.js 18+ (pour CDK)
- AgentCore CLI (optionnel, pour Phase 2)
```

---

## Scripts de Déploiement

### 1. `deploy.sh` - Déploiement Principal (Phase 1)

**Description:** Déploie toute l'infrastructure AWS CDK et prépare le système.

**Usage:**
```bash
./scripts/deploy.sh [dev|prod]
```

**Ce qu'il fait:**
- ✅ Valide les prérequis AWS
- ✅ Bootstrap CDK si nécessaire
- ✅ Build Lambda Layer avec dépendances
  - Exécute `lambda_layer/build_layer.sh` automatiquement
  - Installe les dépendances Python depuis `lambda_layer/requirements.txt`
  - Crée `lambda_layer/strava-ai-boost-dependencies-layer.zip`
  - CDK déploie ensuite le layer depuis le répertoire `lambda_layer/`
- ✅ Déploie tous les stacks CDK (Core, Content, Webhook, API, Monitoring)
- ✅ Crée les secrets Secrets Manager (placeholders)
- ✅ Vérifie les ressources déployées (DynamoDB, Lambda, SQS)
- ✅ Configure le mode Bedrock fallback (système fonctionnel)
- ✅ Génère un rapport de déploiement

**Stacks CDK déployés:**
- `StravaAIBoost-Core` - DynamoDB tables, IAM roles
- `StravaAIBoost-Security` - Secrets Manager, encryption
- `StravaAIBoost-Content` - Content generation Lambda
- `StravaAIBoost-Webhook` - Webhook handler, SQS queues
- `StravaAIBoost-API` - API Gateway pour le frontend
- `StravaAIBoost-Monitoring` - CloudWatch dashboards, alarms

**Sortie:**
- Fichier: `deployment-info-{env}.json`
- Logs: Console avec codes couleur
- Webhook URL pour configuration Strava

**Exemple:**
```bash
# Déploiement développement
export AWS_PROFILE=your-aws-profile
./scripts/deploy.sh dev

# Déploiement production
./scripts/deploy.sh prod
```

**Temps d'exécution:** ~10-15 minutes

---

### 2. `deploy_agentcore_agents.sh` - Déploiement AgentCore (Phase 2 - Optionnel)

**Description:** Déploie les agents AgentCore avec mémoire long-terme pour personnalisation avancée.

**Prérequis:**
- Phase 1 complétée (`deploy.sh`)
- Mémoires AgentCore créées (`create_agentcore_memories.sh`)
- AgentCore CLI installé

**Usage:**
```bash
./scripts/deploy_agentcore_agents.sh
```

**Ce qu'il fait:**
- ✅ Vérifie que les mémoires LTM existent
- ✅ Déploie l'agent `content_gen` (génération de contenu)
- ✅ Déploie l'agent `campus_coach` (extraction Campus Coach)
- ✅ Configure la mémoire long-terme (365 jours)
- ✅ Intègre les guardrails Bedrock (si configurés)
- ✅ Met à jour automatiquement les variables d'environnement Lambda
- ✅ Active le mode personnalisation avancée

**Agents déployés:**
- `content_gen` - Génération de contenu avec apprentissage du style
- `campus_coach` - Extraction automatique des sessions Campus Coach

**Sortie:**
- ARNs des agents déployés
- Configuration mémoire LTM
- Variables d'environnement Lambda mises à jour

**Exemple:**
```bash
# Après avoir créé les mémoires
./scripts/create_agentcore_memories.sh
./scripts/deploy_agentcore_agents.sh
```

**Temps d'exécution:** ~5-10 minutes

**Note:** Le système fonctionne sans AgentCore (mode Bedrock fallback). AgentCore ajoute la personnalisation avancée.

---

## Scripts de Configuration

### 3. `setup_local_env.sh` - Configuration Environnement Local

**Description:** Configure les variables d'environnement pour le frontend React.

**Prérequis:**
- Infrastructure CDK déployée (`deploy.sh`)
- API Gateway déployé

**Usage:**
```bash
./scripts/setup_local_env.sh
```

**Ce qu'il fait:**
- ✅ Récupère l'URL de l'API Gateway depuis CloudFormation
- ✅ Récupère l'API Key depuis AWS
- ✅ Affiche les valeurs à configurer dans `frontend/.env.local`
- ✅ Configure les variables AWS (region, profile)
- ✅ Configure l'ID utilisateur par défaut

**Variables d'environnement pour `frontend/.env.local`:**
```bash
VITE_API_GATEWAY_URL=https://your-api-id.execute-api.eu-west-1.amazonaws.com/prod
VITE_API_GATEWAY_KEY=your-api-key
VITE_DEFAULT_USER_ID=YOUR_USER_ID
```

**Sortie:**
- Configuration prête pour le frontend

**Exemple:**
```bash
# Après déploiement CDK
./scripts/deploy.sh dev
./scripts/setup_local_env.sh

# Démarrer le frontend
cd frontend
cp .env.example .env.local  # Edit with values from setup_local_env.sh output
npm install
npm run dev
# Ouvrir http://localhost:3000
```

**Temps d'exécution:** ~10 secondes

**Note:** Ce script doit être exécuté après chaque redéploiement si l'API Gateway change.

---

### 4. `create_agentcore_memories.sh` - Création Mémoires AgentCore

**Description:** Crée les mémoires long-terme (LTM) pour les agents AgentCore.

**Prérequis:**
- AgentCore CLI installé
- AWS credentials configurées

**Usage:**
```bash
./scripts/create_agentcore_memories.sh
```

**Ce qu'il fait:**
- ✅ Crée la mémoire `content_gen_mem` (génération de contenu)
- ✅ Crée la mémoire `campus_coach_mem` (Campus Coach)
- ✅ Configure la rétention à 365 jours
- ✅ Active la recherche sémantique
- ✅ Attend que les mémoires soient ACTIVE (~2 minutes)

**Mémoires créées:**
- `content_gen_mem` - Apprentissage du style utilisateur
- `campus_coach_mem` - Historique des sessions Campus Coach

**Sortie:**
- IDs des mémoires créées
- Status de création (CREATING → ACTIVE)

**Exemple:**
```bash
./scripts/create_agentcore_memories.sh

# Vérifier le status
agentcore memory list --region eu-west-1
```

**Temps d'exécution:** ~2-3 minutes (attente activation)

---

### 4b. `configure_memory_strategy.py` - Configuration UserPreferenceStrategy

**Description:** Configure la stratégie UserPreferenceStrategy sur la mémoire AgentCore pour l'extraction/consolidation automatique des préférences utilisateur.

**Prérequis:**
- Mémoires AgentCore créées (`create_agentcore_memories.sh`)
- Security stack déployé (Memory Execution Role)

**Usage:**
```bash
python scripts/configure_memory_strategy.py
```

**Ce qu'il fait:**
- ✅ Charge la configuration depuis `.bedrock_agentcore.yaml`
- ✅ Récupère le Memory Execution Role depuis CloudFormation
- ✅ Configure la stratégie `StravaContentPreferences` (UserPreferenceOverride)
- ✅ Prompts personnalisés pour extraction (LENGTH, EXPRESSIONS, EMOJIS, STRUCTURE, TONE, TECHNICAL_DETAIL)
- ✅ Prompts personnalisés pour consolidation (REINFORCE, CONTRADICT, ADD)

**Temps d'exécution:** ~10 secondes

---

### 5. `configure_agentcore_integration.sh` - Configuration IAM et Lambda

**Description:** Configure automatiquement les permissions IAM et les variables d'environnement Lambda pour l'intégration AgentCore.

**Prérequis:**
- Agents AgentCore déployés (`deploy_agentcore_agents.sh`)
- Mémoires AgentCore créées (`create_agentcore_memories.sh`)

**Usage:**
```bash
./scripts/configure_agentcore_integration.sh
```

**Ce qu'il fait:**
- ✅ **Détection intelligente des rôles AgentCore** : Extrait les rôles depuis `.bedrock_agentcore.yaml` (2 rôles au lieu de tous)
- ✅ **Création/mise à jour de policy IAM complète** : `StravaAIBoost-AgentCore-AllPermissions`
  - Permissions mémoire AgentCore (`ListEvents`, `GetEvent`, `CreateEvent`, `DeleteEvent`, `GetMemory`)
  - Accès Secrets Manager (credentials Campus Coach)
  - Accès DynamoDB (sessions Campus Coach)
  - Permissions Browser Tool (scraping Campus Coach)
- ✅ **Optimisation des policies** : Compare le contenu JSON avant de créer une nouvelle version
- ✅ **Attachement aux rôles AgentCore** : Uniquement les 2 rôles des agents déployés
- ✅ **Configuration Lambda IAM** : Policy pour invoquer les agents AgentCore
- ✅ **Mise à jour variables d'environnement Lambda** : Injection directe des ARNs agents (pas de redéploiement CDK)
- ✅ **Filtrage intelligent** : Ignore les custom resource handlers CDK (pas de warnings inutiles)
- ✅ **Mise à jour CDK context** : Sauvegarde des ARNs dans `cdk.context.json`
- ✅ **Création fichier .env.agentcore** : Configuration pour développement local

**Rôles AgentCore configurés:**
- `AmazonBedrockAgentCoreSDKRuntime-eu-west-1-XXXXXXXXXXXX` (content_gen)
- `AmazonBedrockAgentCoreSDKRuntime-eu-west-1-XXXXXXXXXXXX` (campus_coach)

**Variables d'environnement Lambda configurées:**
```bash
CONTENT_GENERATION_AGENT_ARN=arn:aws:bedrock-agentcore:eu-west-1:xxx:runtime/content_gen-xxx
CAMPUS_COACH_AGENT_ARN=arn:aws:bedrock-agentcore:eu-west-1:xxx:runtime/campus_coach-xxx
AGENTCORE_AGENTS_AVAILABLE=true
AGENTCORE_DEPLOYMENT_TYPE=direct_code_deploy
AGENTCORE_REGION=eu-west-1
AGENTCORE_MEMORY_ENABLED=true
```

**Permissions IAM ajoutées:**
```json
{
  "SecretsManagerAccess": ["secretsmanager:GetSecretValue"],
  "DynamoDBAccess": ["dynamodb:PutItem", "UpdateItem", "GetItem", "Query", "Scan"],
  "BrowserToolAccess": ["bedrock-agentcore:StartBrowserSession", "StopBrowserSession", ...],
  "AgentCoreMemoryAccess": ["bedrock-agentcore:ListEvents", "GetEvent", "CreateEvent", ...]
}
```

**Sortie:**
- Nombre de rôles AgentCore configurés (2)
- Nombre de fonctions Lambda mises à jour (~14, hors CDK handlers)
- Policies IAM créées/mises à jour
- Fichiers générés : `cdk.context.json`, `.env.agentcore`

**Exemple:**
```bash
# Après déploiement des agents
./scripts/deploy_agentcore_agents.sh
./scripts/configure_agentcore_integration.sh

# Vérifier la configuration
cat .env.agentcore
cat cdk.context.json | jq '.agentcore'

# Tester l'accès mémoire
aws logs tail /aws/bedrock-agentcore/runtimes/content_gen-* --follow --profile your-aws-profile
# Plus d'erreur "AccessDeniedException" sur ListEvents
```

**Temps d'exécution:** ~2-3 minutes

**Optimisations:**
- ✅ Détection précise des rôles (2 au lieu de 12)
- ✅ Pas de nouvelle version de policy si contenu identique
- ✅ Mise à jour Lambda directe (pas de redéploiement CDK)
- ✅ Filtrage des custom resource handlers CDK

**Note:** Ce script résout le problème `AccessDeniedException: bedrock-agentcore:ListEvents` en ajoutant les permissions mémoire manquantes aux rôles d'exécution AgentCore.

---

### 6. `configure_strava_webhook.sh` - Configuration Webhook Strava

**Description:** Configure le webhook Strava pour recevoir les notifications d'activités en temps réel.

**Prérequis:**
- Infrastructure CDK déployée (`deploy.sh`)
- Credentials Strava dans Secrets Manager

**Usage:**
```bash
./scripts/configure_strava_webhook.sh [dev|prod] [options]

Options:
  --auto-configure    Configuration automatique sans prompts
  --cleanup          Supprime les webhooks existants
  --validate-only    Valide la configuration sans créer de webhook
```

**Ce qu'il fait:**
- ✅ Récupère les credentials Strava depuis Secrets Manager
- ✅ Détecte l'URL du webhook depuis CloudFormation/API Gateway
- ✅ Teste la disponibilité du webhook endpoint
- ✅ Vérifie les webhooks existants
- ✅ Crée le webhook Strava avec verify token
- ✅ Valide la configuration complète
- ✅ Sauvegarde la configuration dans `webhook-config-{env}.json`

**Sortie:**
- Subscription ID du webhook
- Callback URL configurée
- Verify token utilisé
- Fichier de configuration

**Exemples:**
```bash
# Configuration interactive
./scripts/configure_strava_webhook.sh dev

# Configuration automatique
./scripts/configure_strava_webhook.sh dev --auto-configure

# Validation uniquement
./scripts/configure_strava_webhook.sh dev --validate-only

# Nettoyage des webhooks
./scripts/configure_strava_webhook.sh dev --cleanup
```

**Temps d'exécution:** ~1-2 minutes

**Note:** Les credentials Strava doivent être configurés dans Secrets Manager (`strava-ai-boost-oauth-tokens`).

---

## Scripts de Maintenance

### 7. `cleanup_strava_webhook.sh` - Nettoyage Webhooks

**Description:** Supprime les webhooks Strava existants pour réinitialisation.

**Usage:**
```bash
./scripts/cleanup_strava_webhook.sh [dev|prod]
```

**Ce qu'il fait:**
- ✅ Liste tous les webhooks Strava existants
- ✅ Supprime chaque webhook trouvé
- ✅ Nettoie les fichiers de configuration locaux
- ✅ Confirme la suppression

**Sortie:**
- Nombre de webhooks supprimés
- Confirmation de nettoyage

**Exemple:**
```bash
# Nettoyer les webhooks avant reconfiguration
./scripts/cleanup_strava_webhook.sh dev
./scripts/configure_strava_webhook.sh dev
```

**Temps d'exécution:** ~30 secondes

---

### 8. `reprocess_dlq.sh` - Retraitement Messages DLQ

**Description:** Retraite les messages en erreur de la Dead Letter Queue (DLQ).

**Usage:**
```bash
./scripts/reprocess_dlq.sh [dev|prod] [options]

Options:
  --max-messages N    Nombre maximum de messages à retraiter (défaut: 10)
  --dry-run          Affiche les messages sans les retraiter
  --delete-after     Supprime les messages après retraitement réussi
```

**Ce qu'il fait:**
- ✅ Récupère les messages de la DLQ
- ✅ Affiche les détails des messages en erreur
- ✅ Retraite les messages dans la queue principale
- ✅ Optionnellement supprime les messages traités
- ✅ Génère un rapport de retraitement

**Sortie:**
- Nombre de messages retraités
- Détails des erreurs
- Rapport de succès/échec

**Exemples:**
```bash
# Voir les messages sans retraiter
./scripts/reprocess_dlq.sh dev --dry-run

# Retraiter 5 messages
./scripts/reprocess_dlq.sh dev --max-messages 5

# Retraiter et supprimer
./scripts/reprocess_dlq.sh dev --max-messages 10 --delete-after
```

**Temps d'exécution:** Variable selon le nombre de messages

**Cas d'usage:**
- Activités échouées à cause d'une erreur temporaire
- Problème résolu et besoin de retraiter les activités
- Debugging des erreurs de traitement

---

## Scripts de Validation

### 9. `validate_deployment.sh` - Validation Post-Déploiement

**Description:** Valide que tous les composants AWS sont correctement déployés et fonctionnels.

**Usage:**
```bash
./scripts/validate_deployment.sh [dev|prod]
```

**Ce qu'il fait:**
- ✅ Vérifie la connectivité AWS
- ✅ Valide tous les stacks CloudFormation
- ✅ Vérifie les tables DynamoDB (existence, encryption)
- ✅ Valide les fonctions Lambda (runtime, état)
- ✅ Vérifie les queues SQS (principale + DLQ)
- ✅ Valide les state machines Step Functions
- ✅ Teste l'API Gateway (webhook endpoint)
- ✅ Vérifie les secrets Secrets Manager
- ✅ Valide les ressources AgentCore (si déployées)
- ✅ Effectue des tests d'intégration basiques (DynamoDB read/write)
- ✅ Génère un rapport de validation complet

**Composants validés:**
- CloudFormation: 5 stacks
- DynamoDB: 4 tables
- Lambda: 8+ fonctions
- SQS: 2+ queues
- Step Functions: 1+ state machines
- API Gateway: 1+ APIs
- Secrets Manager: 2+ secrets
- AgentCore: 2 agents + 2 mémoires (si déployés)

**Sortie:**
- Rapport détaillé avec ✅/❌/⚠️
- Compteurs: checks passed/failed/warnings
- Fichier: `validation-report-{env}-{timestamp}.json`
- Code de sortie: 0 (succès) ou 1 (échec)

**Exemple:**
```bash
# Validation après déploiement
./scripts/deploy.sh dev
./scripts/validate_deployment.sh dev

# Vérifier le rapport
cat validation-report-dev-*.json | jq '.'
```

**Temps d'exécution:** ~2-3 minutes

**Interprétation des résultats:**
- ✅ PASS: Composant fonctionnel
- ❌ FAIL: Problème critique nécessitant attention
- ⚠️ WARNING: Problème mineur ou configuration optionnelle

---

## Scripts de Désinstallation

### 10. `uninstall.sh` - Désinstallation Complète

**Description:** Supprime toutes les ressources AWS et AgentCore de manière sécurisée.

**Usage:**
```bash
./scripts/uninstall.sh [dev|prod] [options]

Options:
  --force        Pas de confirmation interactive
  --backup       Crée un backup avant suppression
  --keep-data    Conserve DynamoDB et Secrets Manager
```

**Ce qu'il fait:**
- ✅ Demande confirmation (sauf --force)
- ✅ Crée un backup optionnel (DynamoDB, Secrets, configs)
- ✅ Supprime le webhook Strava
- ✅ Supprime les agents AgentCore
- ✅ Supprime les mémoires AgentCore
- ✅ Supprime les stacks CDK (ordre inverse de dépendance)
- ✅ Nettoie les ressources orphelines (Lambda, logs, S3, IAM)
- ✅ Supprime les données (sauf --keep-data)
- ✅ Génère un rapport de désinstallation

**Ordre de suppression:**
1. Webhook Strava
2. Agents AgentCore
3. Mémoires AgentCore
4. Stacks CDK (Monitoring → API → Webhook → Content → Core)
5. Ressources orphelines
6. Données (DynamoDB, Secrets Manager)
7. Fichiers locaux

**Sortie:**
- Logs détaillés de chaque étape
- Fichier: `uninstall-log-{env}-{timestamp}.log`
- Backup: `backup-{env}-{timestamp}.tar.gz` (si --backup)

**Exemples:**
```bash
# Désinstallation interactive
./scripts/uninstall.sh dev

# Désinstallation avec backup
./scripts/uninstall.sh dev --backup

# Désinstallation forcée sans données
./scripts/uninstall.sh dev --force --keep-data

# Désinstallation production avec backup
./scripts/uninstall.sh prod --backup --force
```

**Temps d'exécution:** ~10-15 minutes

**⚠️ ATTENTION:**
- Opération destructive et irréversible (sauf --keep-data)
- Toujours créer un backup en production (--backup)
- Vérifier avec `verify_uninstall.sh` après suppression

---

### 11. `verify_uninstall.sh` - Vérification Désinstallation

**Description:** Vérifie que toutes les ressources ont été correctement supprimées.

**Usage:**
```bash
./scripts/verify_uninstall.sh [dev|prod]
```

**Ce qu'il fait:**
- ✅ Vérifie l'absence de stacks CloudFormation
- ✅ Vérifie l'absence de fonctions Lambda
- ✅ Vérifie l'absence de tables DynamoDB
- ✅ Vérifie l'absence de secrets Secrets Manager
- ✅ Vérifie l'absence de ressources AgentCore
- ✅ Vérifie l'absence de queues SQS
- ✅ Vérifie l'absence de state machines Step Functions
- ✅ Vérifie l'absence d'APIs API Gateway
- ✅ Vérifie l'absence de log groups CloudWatch
- ✅ Vérifie l'absence de buckets S3
- ✅ Vérifie l'absence de rôles IAM
- ✅ Vérifie l'absence de configuration webhook locale
- ✅ Génère un rapport de vérification complet

**Sortie:**
- Rapport détaillé avec ✅/❌/⚠️
- Fichier: `uninstall-verification-report-{env}-{timestamp}.json`
- Code de sortie: 0 (clean) ou 1 (ressources restantes)

**Exemple:**
```bash
# Après désinstallation
./scripts/uninstall.sh dev --backup
./scripts/verify_uninstall.sh dev

# Vérifier le rapport
cat uninstall-verification-report-dev-*.json | jq '.'
```

**Temps d'exécution:** ~2-3 minutes

**Interprétation des résultats:**
- ✅ CLEAN: Aucune ressource trouvée
- ❌ ISSUES: Ressources restantes nécessitant suppression manuelle
- ⚠️ RETAINED: Ressources conservées intentionnellement (logs, etc.)

**Actions si ressources restantes:**
```bash
# Supprimer manuellement les ressources identifiées
aws lambda delete-function --function-name <name> --profile your-aws-profile
aws dynamodb delete-table --table-name <name> --profile your-aws-profile
aws cloudformation delete-stack --stack-name <name> --profile your-aws-profile
```

---

## Workflows Complets

### 🚀 Installation Complète (Mode Standard)

```bash
# 1. Déploiement infrastructure CDK (Phase 1)
export AWS_PROFILE=your-aws-profile
./scripts/deploy.sh dev

# 2. Validation du déploiement
./scripts/validate_deployment.sh dev

# 3. Configuration webhook Strava
./scripts/configure_strava_webhook.sh dev --auto-configure

# 4. Démarrer le frontend
cd frontend
cp .env.example .env.local  # Configurer les variables
npm install
npm run dev
# Ouvrir http://localhost:3000
# Configurer OAuth Strava via le frontend
```

**Temps total:** ~15-20 minutes

---

### 🤖 Installation avec AgentCore (Mode Avancé)

```bash
# 1-3. Même que mode standard
./scripts/deploy.sh dev
./scripts/validate_deployment.sh dev
./scripts/configure_strava_webhook.sh dev

# 4. Déploiement AgentCore (Phase 2 - Optionnel)
./scripts/create_agentcore_memories.sh
./scripts/deploy_agentcore_agents.sh
./scripts/configure_agentcore_integration.sh

# 5. Validation AgentCore
./scripts/validate_deployment.sh dev

# 6. Démarrer le frontend
cd frontend
npm run dev
```

**Temps total:** ~25-30 minutes

---

### 🔄 Mise à Jour Infrastructure

```bash
# 1. Redéployer l'infrastructure
./scripts/deploy.sh dev

# 2. Valider les changements
./scripts/validate_deployment.sh dev

# 3. Si AgentCore déployé, reconfigurer l'intégration
./scripts/configure_agentcore_integration.sh
```

---

### 🧹 Maintenance Régulière

```bash
# Vérifier les messages en erreur
./scripts/reprocess_dlq.sh dev --dry-run

# Retraiter les messages
./scripts/reprocess_dlq.sh dev --max-messages 10 --delete-after

# Valider le système
./scripts/validate_deployment.sh dev
```

---

### 🗑️ Désinstallation Complète

```bash
# 1. Désinstaller avec backup
./scripts/uninstall.sh dev --backup

# 2. Vérifier la désinstallation
./scripts/verify_uninstall.sh dev

# 3. Si ressources restantes, supprimer manuellement
# Voir les commandes dans le rapport de vérification
```

---

## Dépannage

### Problèmes Courants

#### 1. Déploiement CDK échoue

**Symptômes:**
```
❌ CDK deployment encountered issues
Stack StravaAIBoost-Core failed
```

**Solutions:**
```bash
# Vérifier les credentials AWS
aws sts get-caller-identity --profile your-aws-profile

# Vérifier les quotas AWS
aws service-quotas list-service-quotas --service-code lambda

# Consulter les événements CloudFormation
aws cloudformation describe-stack-events \
  --stack-name StravaAIBoost-Core \
  --profile your-aws-profile \
  --max-items 20

# Redéployer après correction
./scripts/deploy.sh dev
```

---

#### 2. AgentCore agents ne se déploient pas

**Symptômes:**
```
❌ Failed to deploy content_gen agent
Memory not found
```

**Solutions:**
```bash
# Vérifier que les mémoires existent
agentcore memory list --region eu-west-1

# Si absentes, créer les mémoires
./scripts/create_agentcore_memories.sh

# Attendre que les mémoires soient ACTIVE (~2 min)
watch -n 10 'agentcore memory list --region eu-west-1'

# Redéployer les agents
./scripts/deploy_agentcore_agents.sh
```

---

#### 3. Webhook Strava ne fonctionne pas

**Symptômes:**
```
❌ Webhook endpoint not responding
HTTP 000 or timeout
```

**Solutions:**
```bash
# Vérifier que l'API Gateway est déployée
aws apigateway get-rest-apis --profile your-aws-profile

# Tester le webhook manuellement
WEBHOOK_URL="https://YOUR_API_ID.execute-api.eu-west-1.amazonaws.com/prod/webhook"
curl -X GET "$WEBHOOK_URL?hub.mode=subscribe&hub.challenge=test&hub.verify_token=strava-ai-boost-verify-token-dev"

# Vérifier les logs Lambda
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler \
  --follow \
  --profile your-aws-profile

# Reconfigurer le webhook
./scripts/cleanup_strava_webhook.sh dev
./scripts/configure_strava_webhook.sh dev
```

---

#### 4. Messages bloqués dans la DLQ

**Symptômes:**
```
⚠️  Found messages in Dead Letter Queue
Activities not processing
```

**Solutions:**
```bash
# Voir les messages en erreur
./scripts/reprocess_dlq.sh dev --dry-run

# Identifier la cause des erreurs
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator \
  --follow \
  --profile your-aws-profile

# Corriger le problème (ex: credentials, permissions)

# Retraiter les messages
./scripts/reprocess_dlq.sh dev --max-messages 10 --delete-after
```

---

#### 5. Validation échoue après déploiement

**Symptômes:**
```
❌ Deployment validation found issues
Checks failed: 3
```

**Solutions:**
```bash
# Consulter le rapport de validation
cat validation-report-dev-*.json | jq '.components_verified'

# Vérifier les composants en échec
./scripts/validate_deployment.sh dev 2>&1 | grep "FAIL"

# Corriger les problèmes identifiés

# Revalider
./scripts/validate_deployment.sh dev
```

---

### Commandes de Diagnostic

```bash
# Vérifier l'état des stacks CloudFormation
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --profile your-aws-profile

# Lister les fonctions Lambda
aws lambda list-functions \
  --profile your-aws-profile \
  --query 'Functions[?contains(FunctionName, `StravaAIBoost`)].FunctionName'

# Vérifier les tables DynamoDB
aws dynamodb list-tables \
  --profile your-aws-profile \
  | jq -r '.TableNames[] | select(contains("strava-ai-boost"))'

# Vérifier les agents AgentCore
agentcore agent list --region eu-west-1

# Vérifier les mémoires AgentCore
agentcore memory list --region eu-west-1

# Consulter les logs CloudWatch
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator \
  --follow \
  --profile your-aws-profile \
  --since 1h
```

---

### Logs et Monitoring

```bash
# Logs Lambda en temps réel
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile

# Logs AgentCore
aws logs tail /aws/bedrock-agentcore/runtimes/content_gen-* --follow --profile your-aws-profile
aws logs tail /aws/bedrock-agentcore/runtimes/campus_coach-* --follow --profile your-aws-profile

# Métriques CloudWatch
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=StravaAIBoost-ContentGenerator \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --profile your-aws-profile
```

---

## Support et Documentation

### Documentation Complète
- **README.md** - Vue d'ensemble du projet
- **docs/getting-started/QUICK-START.md** - Démarrage rapide (5 minutes)
- **docs/getting-started/COMPLETE-SETUP.md** - Guide complet de déploiement
- **docs/reference/ARCHITECTURE.md** - Architecture technique détaillée
- **docs/advanced/AGENTCORE.md** - Documentation AgentCore
- **docs/user-guide/TROUBLESHOOTING.md** - Guide de dépannage

### Ressources Externes
- **AWS CDK:** https://docs.aws.amazon.com/cdk/
- **AgentCore:** https://docs.aws.amazon.com/bedrock/latest/userguide/agents-agentcore.html
- **Strava API:** https://developers.strava.com/docs/

### Contact
- **Issues:** GitHub Issues
- **Discussions:** GitHub Discussions

---

**Version:** 0.1.0  
**Dernière mise à jour:** 2025-01-02  
**Auteur:** Strava AI Boost Team
