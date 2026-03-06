# Backlog

## Etat du projet

Le projet est fonctionnel et en production (dev). Toute la chaine fonctionne end-to-end :
- Webhook Strava → Step Functions → AI content generation → update Strava activity
- Campus Coach scraping automatique (daily via EventBridge)
- Frontend React avec configuration modules, profil utilisateur, feedback loop
- 163 unit tests (Lambda + frontend)
- Observability (X-Ray + CloudWatch), cost allocation tags, DLQ error handling
- Security : Secrets Manager, HMAC-SHA1 webhook verification, API Gateway auth, DynamoDB encryption, no public endpoints

**Stack :** CDK (Python) / Lambda / Step Functions / DynamoDB / API Gateway / Bedrock (Claude) / AgentCore (Browser Tool + LTM) / React + TypeScript

## Done

- Fichiers sensibles dans Git history — `git rm --cached` + `.gitignore`
- Erreur exposee au client — Message generique dans `content_agent.py`
- Webhook API sans auth — Documente (exigence Strava, HMAC-SHA1)
- Logger inconsistant — Harmonise sur `shared.logger.get_logger()`
- Cost allocation tags — CDK + AgentCore resources

---

## P1 — High

### Deploy Frontend CloudFront + S3 + Cognito
Le plus gros chantier restant. Debloque l'acces mobile et supprime la dependance localhost.
- Host React app sur S3 avec CloudFront (OAC, pas OAI)
- Cognito User Pool avec `selfSignUpEnabled: false`
- Remplacer API Key auth par Cognito tokens (SigV4)
- HTTPS everywhere, security headers (HSTS, CSP, X-Frame-Options)
- WAF sur CloudFront pour OWASP protection
- Prerequis : fix OAuth redirect URI hardcode (`StravaAppSetup.tsx:32`, `OAuthConnection.tsx:45` — `localhost:3000` → `import.meta.env.VITE_OAUTH_REDIRECT_URI`)

### IAM trop large
- `content_generation_stack.py:131` — Bedrock `foundation-model/*` au lieu du modele specifique
- `security_stack.py:288-296` — X-Ray `resources=["*"]` (acceptable, API globale)

### Exception handling generique
20+ `except Exception` avec return None silencieux. Critiques :
- `campus_coach_invoker.py:75` — variable `client` potentiellement non definie
- `stepfunctions_error_handler.py:90,129,165`
- `webhook_handler.py:234,357,413`

## P2 — Medium

### RemovalPolicy.DESTROY sur DynamoDB
`core_infrastructure_stack.py:78,109,129` — 3 tables + 4 secrets en DESTROY. Acceptable en dev, a passer en RETAIN avant prod.
- **Fix :** Conditionner sur `environment` context

### Lambda ARM64 (Graviton)
- Switch toutes les Lambda en ARM64 pour ~20% reduction cout
- CDK : `architecture: lambda.Architecture.ARM_64`
- Verifier compatibilite Lambda Layer (rebuild `--platform linux/arm64` si needed)

### Code duplique — Token refresh
Duplique dans 4 fichiers : `strava_updater.py`, `feedback_analyzer.py`, `activity_fetcher.py`, `webhook_handler.py`
- **Fix :** Extraire dans `shared/strava_token_manager.py`

### Strava Rate Limiting & Retry
`strava_updater.py` catch le 429 mais ne retry pas. Ajouter exponential backoff ou re-queue dans Step Functions.

### Credentials dans le prompt Campus Coach
`campus_coach_agent.py` — username/password injectes dans le prompt f-string. Finissent dans logs CloudWatch et memoire AgentCore. Pas genant dans le contexte actuel (single user, projet perso, credentials d'une app de coaching). A traiter si multi-users.
- **Note :** Cet agent est fragile — sensible a la casse et au format de la page Campus Coach. Un changement cote Campus Coach peut casser l'extraction.
- **Fix leger :** Desactiver `on_message_added` dans le memory hook, supprimer log du username et du resultat brut.
- **Fix complet (multi-users/prod) :** Browser Profiles AWS pour auth persistante via cookies.

### CI/CD Pipeline
Pas de pipeline — `cdk deploy` manuel. GitHub Actions avec `cdk diff` sur PR + deploy on merge.

### Budget Alert
Tags cost allocation en place mais pas d'alerte. Ajouter `aws budgets` avec seuil + notification SNS.

### DLQ Monitoring
Le DLQ existe mais personne ne le lit. Alarme CloudWatch sur `ApproximateNumberOfMessagesVisible > 0`.

## P3 — Low

### Campus Coach API
Pas d'API disponible a date. Surveiller si Campus Coach expose une API — remplacerait le scraping browser (plus rapide, fiable, moins cher).

### Catch vides frontend
`ModuleConfiguration.tsx:56-58` — `catch {}` sans feedback utilisateur.

### Type hints manquants
~40 fonctions sans type hints sur Lambda handlers et fonctions publiques.

### Verify Observability Stack
- Checker traces dans CloudWatch GenAI Observability dashboard
- Verifier X-Ray custom resources et CloudWatch Logs resource policy
- Si pas de traces : checker OpenTelemetry enabled dans AgentCore runtime
