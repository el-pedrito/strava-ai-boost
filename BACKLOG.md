# Backlog

## Etat du projet

Le projet est fonctionnel et en production (dev). Toute la chaine fonctionne end-to-end :
- Webhook Strava → Step Functions → AI content generation → update Strava activity
- Campus Coach scraping automatique (weekly via EventBridge, session status sync on match)
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
- Cost allocation tags — CDK + AgentCore resources + IAM execution roles (per-agent Bedrock cost via CUR 2.0)
- **Cost optimization pass (April 2026)** — $513/mo -> ~$26/mo. See [docs/OPTIMIZATION-PLAN.md](docs/OPTIMIZATION-PLAN.md).
  - Campus Coach cron weekly (was daily) + mark session done on match
  - Campus Coach + Memory Strategy -> Haiku 4.5 (was Sonnet)
  - Bedrock prompt caching on content_gen system prompt
  - `MaxToolCountsHook` prevents infinite loops on Campus Coach
  - `MonitoringStack` removed — rely on AgentCore Observability + default AWS namespaces
- **Credentials leak in AgentCore logs** — CloudWatch Data Protection Policy masks `Password:`, `EmailAddress`, `AwsSecretKey`, `Authorization:` in all AgentCore runtime log groups. Applied by `scripts/tag_agentcore_resources.py`.
- **Campus Coach scraping reliability** — Diagnosed Axeptio cookies popup blocking Playwright `networkidle` (upstream bug microsoft/playwright#19835). Fixed via prompt-level instruction.

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

### Credentials dans le prompt Campus Coach — partiellement résolu
`campus_coach_agent.py` — username/password sont toujours injectes dans le prompt f-string, mais la fuite dans CloudWatch Logs est maintenant bloquee par CloudWatch Data Protection Policy.
- **Reste pour multi-users/prod :** Browser Profiles AWS pour auth persistante via cookies (évite de passer les credentials à chaque invocation).
- **Note :** Cet agent est fragile — sensible a la casse et au format de la page Campus Coach. Un changement cote Campus Coach peut casser l'extraction.

### CI/CD Pipeline
Pas de pipeline — `cdk deploy` manuel. GitHub Actions avec `cdk diff` sur PR + deploy on merge.

### Budget Alert
Tags cost allocation en place mais pas d'alerte. Ajouter `aws budgets` avec seuil + notification SNS.

### DLQ Monitoring
Le DLQ existe mais personne ne le lit. Alarme CloudWatch sur `ApproximateNumberOfMessagesVisible > 0`.

## P3 — Low

### Campus Coach API
Pas d'API disponible a date. Surveiller si Campus Coach expose une API — remplacerait le scraping browser (plus rapide, fiable, moins cher).

---

## Vision — Coach bienveillant & onboarding riche

Projet open-source, **pas de SaaS multi-users**. Chacun déploie sur son compte.
Le but de cette évolution : sortir du simple "enhance title/description"
pour aller vers un **coach personnel numérique** qui connaît l'utilisateur
et lui parle comme un pote attentionné — sans jamais sonner "AI generated".

### Phase 1 — Onboarding riche au 1er déploiement

Aujourd'hui le profil utilisateur est basique (age_range, sport_approach,
content_length, etc.). L'idée est de **capturer beaucoup plus de contexte**
dès la 1ère configuration, pour avoir une personnalisation correcte
**avant** que le feedback loop ait eu le temps d'apprendre (~10 activités).

Profil à capturer (page Configuration > Profile, peut être fait en plusieurs écrans) :

- **Identité & niveau**
  - Âge exact (pas juste tranche) pour calculer FC max théorique (220-âge)
  - Sexe (pour affiner les zones FC/VMA si besoin)
  - Taille / poids (optionnel, utile pour calories/watts)
  - Niveau auto-évalué (débutant / loisir / régulier / compétiteur / élite)
  - Années de pratique par sport principal
- **Activités pratiquées**
  - Sports principaux (course, vélo, trail, triathlon, nage, muscu, yoga, etc.)
  - Fréquence hebdo moyenne
  - Volume hebdo moyen par sport (km ou heures)
- **Palmarès & records**
  - PR actuels sur distances classiques (5K, 10K, semi, marathon, FTP vélo)
  - Meilleure année, meilleure course mémorable
- **Objectifs**
  - Courses visées dans les 12 prochains mois (date, distance, objectif chrono)
  - Objectifs qualitatifs (perdre du poids, finir un marathon, rester régulier, etc.)
  - Zone d'entraînement favorite (EF, seuil, VMA, fractionné, etc.)
- **Style éditorial**
  - Comment il décrit habituellement ses sorties (champs libres avec exemples)
  - Expressions qu'il emploie / évite
  - Niveau d'humour / sérieux / technique / émotionnel souhaité
  - Préférence d'ouverture / fermeture de description (ex: toujours finir par une phrase motivante)

Injection dans le prompt : étendre `build_profile_context()` pour exposer
ces nouveaux champs à l'agent content_gen. Tout reste optionnel — profil
vide = comportement actuel.

### Phase 2 — Feedback bienveillant / coaching dans les descriptions

Au-delà d'enrichir la description d'une activité, détecter **automatiquement
des signaux positifs** à mentionner avec le ton du user :

- **Progression** : "cette foulée à 180 spm, c'est ton meilleur score du mois",
  "+15% de volume vs la même semaine l'an dernier", "3e sortie >10K d'affilée".
- **Records** : "nouveau PR sur le kilomètre #3 à 4:02/km", tirer des best_efforts
  Strava existants.
- **Consistance** : "4 sorties cette semaine, tu tiens la cadence", "3 mois
  sans interruption".
- **Adaptation** : "tu as bien ralenti quand la chaleur a frappé à 14h",
  "cadence stable malgré 400m D+".
- **Encouragements ciblés** : si la personne a renseigné un objectif "semi en mai",
  commenter la pertinence de la sortie vis-à-vis de l'objectif.

**Implémentation (tout en prompt, pas de nouveau Lambda)** :
- Étendre `activity_fetcher` pour récupérer **l'historique court** (30 derniers
  jours d'activités) depuis DynamoDB
- Calculer côté Python des stats simples (volume hebdo, cadence moyenne,
  streak de régularité) — pas de LLM pour le math
- Les injecter dans le payload du content_gen qui choisit **1 ou 2 signaux**
  à mentionner (pas tous, sinon ça devient un tableau de bord)
- Règle dans le prompt : "ne célèbre que si c'est vrai, ne force pas, et
  mentionne-le dans le style du user"

### Phase 3 — Module "Coach" activable

Packaging : créer un module `coach` (au même niveau que Campus Coach,
Enduraw, Intervals.icu) activable/désactivable depuis le frontend.
Module désactivé = on reste sur le comportement actuel (enhance simple).

Cohérent avec la philosophie "tout est optionnel, chacun compose
sa stack selon ses besoins".

### Non-goals explicites

- **Pas de multi-tenant / SaaS** — le projet reste une instance par utilisateur.
  Les optimisations récentes (per-agent cost tags, Data Protection Policy)
  couvrent déjà le risque de fuite de données dans le contexte single-user.
- **Pas de "AI Generated by X"** dans la signature — ça casse l'illusion
  d'authenticité. (La signature `@Generated by Strava AI Boost` actuelle
  pourrait même être retirée à terme, c'est à débattre.)
- **Pas de notifications proactives** — l'agent n'écrit que sur la
  description de l'activité que l'utilisateur a lui-même publiée.

---

### Catch vides frontend
`ModuleConfiguration.tsx:56-58` — `catch {}` sans feedback utilisateur.

### Type hints manquants
~40 fonctions sans type hints sur Lambda handlers et fonctions publiques.

### Verify Observability Stack
- Checker traces dans CloudWatch GenAI Observability dashboard
- Verifier X-Ray custom resources et CloudWatch Logs resource policy
- Si pas de traces : checker OpenTelemetry enabled dans AgentCore runtime
