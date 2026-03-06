# Code Review - March 2026

## Critical

### 1. Fichiers sensibles dans Git history
`.bedrock_agentcore.yaml`, `.env.agentcore`, `cdk.context.json` contiennent account ID, profil AWS, paths locaux, agent/guardrail IDs. Deja dans `.gitignore` mais trackes dans l'historique.
- **Fix:** `git rm --cached` + nettoyer historique avant merge sur `main`
- **Status:** DONE

### 2. Credentials dans le prompt Campus Coach
`campus_coach_agent.py:223-263` — username/password injectes dans le prompt f-string. Finissent dans logs, memoire AgentCore, CloudWatch.
- **Fix:** Passer via tool call ou env var, pas dans le prompt texte
- **Status:** TODO

### 3. RemovalPolicy.DESTROY sur DynamoDB
`core_infrastructure_stack.py:78,109,129` — Les 3 tables + 4 secrets. Acceptable en dev, passer en RETAIN pour prod.
- **Fix:** Conditionner sur environment context
- **Status:** TODO (acceptable en dev)

## High

### 4. IAM trop large
- `security_stack.py:288-296` — X-Ray `resources=["*"]` (acceptable, API globale)
- `content_generation_stack.py:131` — Bedrock `foundation-model/*` au lieu du modele specifique
- **Status:** TODO

### 5. Exception handling generique
20+ `except Exception` avec return None silencieux. Critiques:
- `campus_coach_invoker.py:75` — variable `client` potentiellement non definie
- `stepfunctions_error_handler.py:90,129,165`
- `webhook_handler.py:234,357,413`
- **Status:** TODO

### 6. Erreur exposee au client
`content_agent.py:1054` — `"error": str(e)` retourne l'exception brute.
- **Fix:** Retourner message generique
- **Status:** DONE

### 7. Webhook API sans auth
`webhook_processing_stack.py:322-340` — Endpoints publics. Normal (exigence Strava), mais documenter.
- **Fix:** Ajouter commentaire explicatif
- **Status:** DONE

## Medium

### 8. Code duplique — Token refresh
Duplique dans 4 fichiers: `strava_updater.py`, `feedback_analyzer.py`, `activity_fetcher.py`, `webhook_handler.py`
- **Fix:** Extraire dans `shared/strava_token_manager.py`
- **Status:** TODO

### 9. Logger inconsistant
5 fichiers utilisent `logging.getLogger()` au lieu de `get_logger()`:
`strava_updater.py`, `streams_analysis.py`, `webhook_handler.py`, `stepfunctions_error_handler.py`, `campus_coach_invoker.py`
- **Status:** DONE

### 10. Type hints manquants
~40 fonctions sans type hints sur Lambda handlers et fonctions publiques.
- **Status:** TODO

### 11. OAuth redirect URI hardcode
`StravaAppSetup.tsx:32`, `OAuthConnection.tsx:45` — `localhost:3000` hardcode. Bloquant pour deploy CloudFront.
- **Fix:** `import.meta.env.VITE_OAUTH_REDIRECT_URI`
- **Status:** TODO

### 12. Catch vides frontend
`ModuleConfiguration.tsx:56-58` — `catch {}` sans feedback utilisateur.
- **Status:** TODO

## Passed

- DynamoDB encryption (AWS_MANAGED) 3/3
- Point-in-time recovery 3/3
- Secrets Manager (pas de secrets hardcodes)
- API Gateway auth (API Key) 15/15 endpoints
- No Lambda Function URLs
- No S3 buckets publics
- HMAC-SHA1 webhook verification
- Cost allocation tags sur toutes les ressources
- Frontend TypeScript (pas de `any`)
- Frontend accessibility (ARIA)
- No `print()` (logger partout)
- Bash scripts `set -e`
- requirements.txt a jour
- Context window ~5K/200K tokens
