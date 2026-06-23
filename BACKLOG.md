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
- **Cost optimization pass (April 2026)** — $513/mo -> ~$26/mo (Campus Coach weekly cron + Haiku, Bedrock prompt caching, MaxToolCountsHook, MonitoringStack supprimé).
  - Campus Coach cron weekly (was daily) + mark session done on match
  - Campus Coach + Memory Strategy -> Haiku 4.5 (was Sonnet)
  - Bedrock prompt caching on content_gen system prompt
  - `MaxToolCountsHook` prevents infinite loops on Campus Coach
  - `MonitoringStack` removed — rely on AgentCore Observability + default AWS namespaces
- **Credentials leak in AgentCore logs** — CloudWatch Data Protection Policy masks `Password:`, `EmailAddress`, `AwsSecretKey`, `Authorization:` in all AgentCore runtime log groups. Applied by `scripts/tag_agentcore_resources.py`.
- **Campus Coach scraping reliability** — Diagnosed Axeptio cookies popup blocking Playwright `networkidle` (upstream bug microsoft/playwright#19835). Fixed via prompt-level instruction.
- **Campus Coach fire-and-forget fix (2026-04-27)** — Lambda invoker timeout 120s systematique : `asyncio.create_task` dans `@app.entrypoint` gardait la coroutine attachee au worker loop AgentCore, bloquant la reponse HTTP. Fix : `threading.Thread` + `asyncio.run()` dans le handler. Lambda retourne maintenant en <15s. Commit `69486ef`.

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

### Programme Muscu structuré (Coach vision globale)
Le coach n'a pas de visibilité structurée sur les séances muscu — il lit le profil athlète (texte libre) mais ne peut pas matcher/tracker les progressions.

**Objectif :** Stocker le programme muscu de référence, matcher les activités WeightTraining, tracker les progressions de charges.

**Spec :**
- Nouveau champ `user_preferences.strength_program` dans DynamoDB :
  ```json
  {
    "sessions": [
      {"id": "upper_a", "name": "Upper A — Dos dominant", "frequency": "1x/semaine",
       "exercises": [
         {"name": "Tractions", "sets": "4×8-10", "load": "BW (+5kg s1)", "rest": "2min"},
         {"name": "Low row machine convergente", "sets": "4×10", "load": "80-82.5kg", "rest": "2min"},
         ...
       ]},
      {"id": "upper_b", "name": "Upper B — Pec dominant", ...},
      {"id": "rappel_upper", "name": "Rappel upper (post renfo Campus)", ...}
    ]
  }
  ```
- Page frontend "Programme Muscu" (CRUD, éditable)
- Injection dans le prompt coach : programme de référence + total semaine (course + muscu)
- Matching activité WeightTraining : le coach lit la description Strava pour identifier Upper A/B/Rappel. Si description vide → fallback sur le programme de référence.
- Tracking progressions : comparer charges/volumes d'une semaine à l'autre (ex: "DC passé de 80kg 4x8 à 85kg 4x8 en 3 semaines")
- `recommendation_next` intègre la charge globale : "Cette semaine : 5 séances course Campus + 2 Upper + 1 Rappel = 8 séances total"

**Note :** La description Strava prime toujours sur le programme de référence (l'athlète adapte en fonction des machines dispo, de l'envie, etc.)

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

### Lambda Layer build automation
Dette technique #1+#4 : hash `LAYER_ASSET_HASH` et build du layer sont manuels. Oubli = deps stales ou cross-stack export cassé. Makefile ou `scripts/build_layer.sh` qui rebuild + update le hash automatiquement.

### CDK Feature Flags manquants
Dette technique #2 : ~35/58 flags configurés dans `cdk.json` — warnings a chaque `cdk synth/deploy`. Bruit log + risque comportement par defaut legacy sur upgrade CDK. Passer `cdk flags` puis aligner.

### Hallucination résumé hebdo hors-chat (bloc "Prochaine séance")
Le composant frontend affichant "Prochaine séance / Total semaine en cours : X séances" hallucine les chiffres (ex: "5 séances cette semaine" alors que 0 activité réelle cette semaine). Bug distinct du chat coach — le chat a été corrigé via `format_weekly_breakdown` (découpage hebdo explicite dans le contexte) le 2026-06-23. Appliquer le même type de fix au composant/endpoint qui génère ce bloc (probablement /coach/summary ou /coach/trends, ou le coach_feedback généré à l'enhancement). Localiser le composant frontend puis injecter les vrais chiffres hebdo au lieu de laisser le LLM extrapoler.

### cdk-nag absent (chantier dédié)
Aucune intégration cdk-nag dans le projet (`Aspects.of(app).add(AwsSolutionsChecks())` absent de `app.py`). Le skill `check-cdk-security` le flagge comme requis pour les projets CDK. À traiter dans un chantier dédié car l'activation app-wide fera remonter des findings sur les 7 stacks existants (à trier + supprimer avec justification). Détecté le 2026-06-23 lors de l'ajout du coach streaming (AG-UI). Le nouveau code (Function URL AWS_IAM + RESPONSE_STREAM, Identity Pool sans accès non-authentifié, rôle scopé) passe l'audit manuel — c'est l'outillage automatisé qui manque, pas la conformité.

## P3 — Low

### Campus Coach API
Pas d'API disponible a date. Surveiller si Campus Coach expose une API — remplacerait le scraping browser (plus rapide, fiable, moins cher).

### Migration config dead code
Dette technique #7 : `activity_fetcher.py` fait une migration old→new format de config a chaque fetch. Tous les users sont migrés depuis longtemps. Retirer le code.

### Embedded prompts externalization
Dette technique #6 : `embedded_prompts.py` = ~20k chars, difficile a reviewer/A-B tester. Externaliser (S3 + version) pour decoupler du cycle de deploy de l'agent. Low priority car fonctionne.

---

## Open-Source Release Readiness

Audit (2026-04-25) : projet prêt à **~80%**. À traiter avant publication GitHub + blog post.

### P0 — Bloquants pour un sample OSS "propre"

#### Disclaimer non-production dans README
Le README présente le projet comme production-ready à plusieurs endroits,
mais il a des known issues (AgentCore Browser cold starts, Lambda timeout
120s, pas de CI/CD). Ajouter un bloc "Non-Production Sample" en tête :

> This is a demo/personal-use sample. Not meant to be deployed to production
> as-is. Known issues: ... (liste courte).

#### Fichiers OSS standards absents
- `CONTRIBUTING.md` — comment contribuer, format PR, tests requis
- `CODE_OF_CONDUCT.md` — Contributor Covenant standard
- `SECURITY.md` — comment reporter une vuln
- `.github/ISSUE_TEMPLATE.md` + `.github/pull_request_template.md`

#### Dépendances avec CVE connues
`pip-audit` (2026-04-25) liste 9 CVE mineures :
- cryptography 46.0.5 → 46.0.7 (CVE-2026-34073, CVE-2026-39892)
- urllib3, requests, pytest, pygments, lxml, pillow, pip
Aucune critique mais visible pour les contributeurs. Bump via `requirements.txt`
+ `lambda_layer/requirements.txt` + rebuild du layer.

### P1 — Nice to have pour lancement propre

#### Licence MIT → MIT-0 (si alignement aws-samples)
AWS samples publics utilisent MIT-0 (MIT No Attribution). À décider selon
stratégie de publication.

#### Screenshots + GIF démo dans README
Un GIF du frontend (dashboard + configuration) + 1 exemple avant/après
de description Strava enrichie. Beaucoup plus parlant qu'un texte seul.

#### Threat model simple
`docs/THREAT-MODEL.md` : 1 page listant les 5-10 menaces principales
(prompt injection sur credentials, webhook spoofing, secrets leak,
fork-based attack, etc.) avec les mitigations en place.

#### Scan ASH (Automated Security Helper)
`ash --mode local --source-dir .` — passe Bandit, Semgrep, Checkov,
cfn-nag, detect-secrets, cdk-nag, npm-audit en un seul shot. Publier
le rapport summary pour transparence.

### P2 — Pour plus tard

#### Tag v0.1.0 + CHANGELOG.md
Créer une première release avec tag Git et CHANGELOG listant les
milestones (v0 = fonctionnalité initiale, v0.1 = optimisation cost).

#### Architecture diagram officiel
Le mermaid du README est bien. Un PNG haute résolution généré via
`aws-diagram-mcp-server` serait plus "professionnel" pour le blog post.

#### Blog post
Structure proposée :
- **Problème** : enrichir ses activités Strava de façon personnalisée et authentique
- **Approche** : serverless + AgentCore + Strands + feedback loop
- **Cost story** : $513/mo → $26/mo, leçons apprises sur AgentCore Browser
- **Open questions** : cold starts, personnalisation progressive, multi-tenant

### Non-goals (décidés le 2026-04-25)

- **Pas de soumission PCSR** (Public Code Security Review Amazon) — ce n'est
  pas un sample AWS officiel mais un projet perso open-source. MIT + bonnes
  pratiques + disclaimer suffisent.
- **Pas de CI/CD pipeline** à la publication initiale — cdk deploy manuel
  documenté. GitHub Actions peut venir après les premiers retours utilisateurs.

---

## Vision — Coach bienveillant & onboarding riche

Projet open-source, **pas de SaaS multi-users**. Chacun déploie sur son compte.
Le but de cette évolution : sortir du simple "enhance title/description"
pour aller vers un **coach personnel numérique** qui connaît l'utilisateur
et lui parle comme un pote attentionné — sans jamais sonner "AI generated".

**⚠️ Ce n'est pas un nouveau module activable.** C'est une **évolution
du `content_gen` actuel** : les commentaires enrichis aujourd'hui
incluront en plus des signaux de coaching bienveillant quand c'est pertinent.
Ça reste la même chaîne (webhook → Step Functions → content_gen → Strava update),
juste un prompt plus riche et un payload enrichi.

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

### Phase 2 — Signaux coaching intégrés dans chaque description

**Intégré directement dans le flux content_gen actuel**, pas un module séparé.
À chaque activité enrichie, détecter **automatiquement des signaux positifs**
à mentionner dans la description, avec le ton du user :

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

**Implémentation (tout dans le flux existant)** :
- Étendre `activity_fetcher` pour récupérer **l'historique court** (30 derniers
  jours d'activités) depuis DynamoDB
- Calculer côté Python des stats simples (volume hebdo, cadence moyenne,
  streak de régularité) — pas de LLM pour le math
- Les injecter dans le payload du content_gen qui choisit **1 ou 2 signaux**
  à mentionner (pas tous, sinon ça devient un tableau de bord)
- Règles dans le prompt :
  - "intègre au max 1-2 signaux de progression quand c'est pertinent et vrai"
  - "au style du user, pas en mode rapport de coach"
  - "jamais à tout prix : si rien de remarquable, reste sur la narration de la sortie"

### Non-goals explicites

- **Pas de multi-tenant / SaaS** — le projet reste une instance par utilisateur.
  Les optimisations récentes (per-agent cost tags, Data Protection Policy)
  couvrent déjà le risque de fuite de données dans le contexte single-user.
- **Pas de "AI Generated by X"** dans la signature — ça casse l'illusion
  d'authenticité. (La signature `@Generated by Strava AI Boost` actuelle
  pourrait même être retirée à terme, c'est à débattre.)
- **Pas de notifications proactives** — l'agent n'écrit que sur la
  description de l'activité que l'utilisateur a lui-même publiée.
- **Pas un nouveau module activable** — le coaching est une extension
  naturelle du `content_gen` existant, pas une case à cocher de plus.

---

### Catch vides frontend
`ModuleConfiguration.tsx:56-58` — `catch {}` sans feedback utilisateur.

### Type hints manquants
~40 fonctions sans type hints sur Lambda handlers et fonctions publiques.

### Verify Observability Stack
- Checker traces dans CloudWatch GenAI Observability dashboard
- Verifier X-Ray custom resources et CloudWatch Logs resource policy

### A2UI — generative UI pour le coach (évolution future)
Le coach streame aujourd'hui du texte via AG-UI (SSE : Function URL `RESPONSE_STREAM`/`AWS_IAM` + SigV4 Identity Pool, `coach_stream/app.py` Starlette + Lambda Web Adapter). A2UI (`a2ui-project`, Google/ADK, preview v0.9.1) est **complémentaire** : il définit un format JSON déclaratif d'UI que l'agent génère, et utilise **AG-UI comme transport** — le socle SSE déjà en place. Pertinent SI on veut des artefacts riches générés à la volée (graphe de charge interactif, formulaire d'objectifs dynamique) plutôt que du texte. Pas prioritaire : (1) le coach renvoie du texte conversationnel, pas d'UI dynamique ; (2) A2UI pas encore v1.0 (policy §10) ; (3) rendu couplé à CopilotKit/Lit, alors qu'on a un design system maison. À reconsidérer quand un besoin de generative UI concret apparaît. Détecté 2026-06-23.
- Si pas de traces : checker OpenTelemetry enabled dans AgentCore runtime
