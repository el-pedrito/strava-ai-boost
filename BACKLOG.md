# Backlog

> Document de travail interne (en français). Pour l'état à jour du projet et la
> liste consolidée des chantiers réalisés, la **source de vérité est
> [docs/ROADMAP.md](docs/ROADMAP.md)**. Ce fichier ne garde que la dette
> technique et les idées encore ouvertes.

## Etat du projet

Le projet est fonctionnel et en production (dev). Toute la chaine fonctionne end-to-end :
- Webhook Strava → Step Functions → AI content generation → update Strava activity
- Campus Coach sync REST direct (daily 05:00 UTC via EventBridge, session status sync on match)
- Frontend React (CloudFront + Cognito) avec configuration modules, profil utilisateur, feedback loop
- 396 tests (302 backend unit + 41 régression + 53 frontend) + 73 tests d'intégration
- Observability (X-Ray + CloudWatch), cost allocation tags, DLQ error handling
- Security : Secrets Manager, HMAC-SHA1 webhook verification, Cognito auth (API Gateway + coach chat customJWT), DynamoDB encryption, no public endpoints

**Stack :** CDK (Python) / Lambda / Step Functions / DynamoDB / API Gateway / Bedrock (Claude) / AgentCore (3 Runtimes + Memory) / React + TypeScript

## Done

Voir [docs/ROADMAP.md](docs/ROADMAP.md) pour la liste complète et datée. Rappels notables issus de ce backlog :

- Fichiers sensibles dans Git history — `git rm --cached` + `.gitignore`
- Erreur exposee au client — Message generique dans `content_agent.py`
- Webhook API sans auth — Documente (exigence Strava, HMAC-SHA1)
- Logger inconsistant — Harmonise sur `shared.logger.get_logger()`
- Cost allocation tags — CDK + AgentCore resources + IAM execution roles (per-agent Bedrock cost via CUR 2.0)
- **Cost optimization pass (April 2026)** — $513/mo -> ~$26/mo (Campus Coach cron + Haiku, Bedrock prompt caching, MaxToolCountsHook, MonitoringStack supprimé).
- **Credentials leak in AgentCore logs** — CloudWatch Data Protection Policy masks `Password:`, `EmailAddress`, `AwsSecretKey`, `Authorization:` in all AgentCore runtime log groups. Applied by `scripts/tag_agentcore_resources.py`.
- **Campus Coach fire-and-forget fix (2026-04-27)** — `threading.Thread` + `asyncio.run()` dans le handler de la Lambda invoker (timeout 120s systematique). Commit `69486ef`. *(Composant depuis décommissionné.)*
- **Deploy Frontend CloudFront + S3 + Cognito** — fait : S3 + CloudFront (OAC), Cognito User Pool (`selfSignUpEnabled: false`), auth JWT Cognito (l'API key a été remplacée), HTTPS everywhere.
- **Campus Coach API REST** — fait : `campus_coach_sync.py` (login + `GET /smart-training`) remplace le scraping Browser Tool. Agent Browser Tool + Lambda invoker **décommissionnés le 2026-07-16**.
- **Programme Muscu structuré** — fait : `user_preferences.strength_program` (Upper A/B, Rappel), extraction LLM des séances (`parsed_sets`), charts progression dans Coach Trends, injection coach (vision globale hebdo + progressions charges).
- **Budget Alert + DLQ Monitoring** — fait : alarme CloudWatch DLQ → SNS + monthly budget alert (cf. CHANGELOG v0.1.0).
- **Open-Source Release Readiness (audit 2026-04-25)** — fait : disclaimer non-production, CONTRIBUTING/CODE_OF_CONDUCT/SECURITY/`.github/ISSUE_TEMPLATE`, licence **MIT-0** appliquée, GIF démo dans le README, `docs/THREAT-MODEL.md`, scan ASH (`docs/SECURITY-SCAN.md`), bump des dépendances CVE, tag **v0.1.0 + CHANGELOG** (release publiée le 2026-07-15). Non-goals confirmés : pas de PCSR, pas de CI/CD à la publication initiale.

---

## P1 — High

### IAM trop large
- `content_generation_stack.py:131` — Bedrock `foundation-model/*` au lieu du modele specifique
- `security_stack.py:288-296` — X-Ray `resources=["*"]` (acceptable, API globale)

### Exception handling generique
20+ `except Exception` avec return None silencieux. Critiques :
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

### CI/CD Pipeline
Pas de pipeline — `cdk deploy` manuel. GitHub Actions avec `cdk diff` sur PR + deploy on merge.

### Lambda Layer build automation
Dette technique : hash `LAYER_ASSET_HASH` et build du layer sont manuels. Oubli = deps stales ou cross-stack export cassé. Makefile ou wrapper autour de `lambda_layer/build_layer.sh` qui rebuild + update le hash automatiquement.

### CDK Feature Flags manquants
~35/58 flags configurés dans `cdk.json` — warnings a chaque `cdk synth/deploy`. Bruit log + risque comportement par defaut legacy sur upgrade CDK. Passer `cdk flags` puis aligner.

### Hallucination résumé hebdo hors-chat (bloc "Prochaine séance")
Le composant frontend affichant "Prochaine séance / Total semaine en cours : X séances" hallucine les chiffres (ex: "5 séances cette semaine" alors que 0 activité réelle cette semaine). Bug distinct du chat coach — le chat a été corrigé via `format_weekly_breakdown` (découpage hebdo explicite dans le contexte) le 2026-06-23. Appliquer le même type de fix au composant/endpoint qui génère ce bloc (probablement /coach/summary ou /coach/trends, ou le coach_feedback généré à l'enhancement). Localiser le composant frontend puis injecter les vrais chiffres hebdo au lieu de laisser le LLM extrapoler.

### cdk-nag absent (chantier dédié)
Aucune intégration cdk-nag dans le projet (`Aspects.of(app).add(AwsSolutionsChecks())` absent de `app.py`). Le skill `check-cdk-security` le flagge comme requis pour les projets CDK. À traiter dans un chantier dédié car l'activation app-wide fera remonter des findings sur les 8 stacks existants (à trier + supprimer avec justification). Détecté le 2026-06-23. Le code du coach chat (runtime AgentCore customJWT, rôle scopé) passe l'audit manuel — c'est l'outillage automatisé qui manque, pas la conformité.

## P3 — Low

### Migration config dead code
Dette technique : `activity_fetcher.py` fait une migration old→new format de config a chaque fetch. Tous les users sont migrés depuis longtemps. Retirer le code.

### Embedded prompts externalization
Dette technique : `embedded_prompts.py` = ~20k chars, difficile a reviewer/A-B tester. Externaliser (S3 + version) pour decoupler du cycle de deploy de l'agent. Low priority car fonctionne.

### Catch vides frontend
`ModuleConfiguration.tsx:56-58` — `catch {}` sans feedback utilisateur.

### Type hints manquants
~40 fonctions sans type hints sur Lambda handlers et fonctions publiques.

### Verify Observability Stack
- Checker traces dans CloudWatch GenAI Observability dashboard
- Verifier X-Ray custom resources et CloudWatch Logs resource policy
- Si pas de traces : checker OpenTelemetry enabled dans AgentCore runtime

### A2UI — generative UI pour le coach (évolution future)
Le coach streame aujourd'hui du texte via AG-UI (SSE : runtime AgentCore `coach_chat`, POST direct du navigateur vers le data plane, auth customJWT). A2UI (`a2ui-project`, Google/ADK, preview v0.9.1) est **complémentaire** : il définit un format JSON déclaratif d'UI que l'agent génère, et utilise **AG-UI comme transport** — le socle SSE déjà en place. Pertinent SI on veut des artefacts riches générés à la volée (graphe de charge interactif, formulaire d'objectifs dynamique) plutôt que du texte. Pas prioritaire : (1) le coach renvoie du texte conversationnel, pas d'UI dynamique ; (2) A2UI pas encore v1.0 (policy §10) ; (3) rendu couplé à CopilotKit/Lit, alors qu'on a un design system maison. À reconsidérer quand un besoin de generative UI concret apparaît. Détecté 2026-06-23.

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
