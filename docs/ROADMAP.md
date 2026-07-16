# Roadmap

> Strava AI Boost — roadmap consolidée le 2026-07-10.
> **Positionnement tranché : projet perso + publication open-source.**
> Pas de produit fini, pas de SaaS, pas de monétisation — les items
> landing/pricing/Stripe/coach-pro/marketplace sont retirés.
> Deux axes : (1) valeur perso au quotidien, (2) qualité de sample
> open-source (showcase AgentCore/Bedrock/CDK).
> Détail agentic : [design/agentcore-agentic-improvements.md](./design/agentcore-agentic-improvements.md).

## Done

- **Campus Coach : migration Browser Tool → API REST directe** : Lambda `campus_coach_sync.py` (`POST /account/login` + `GET /smart-training` → DynamoDB, 9 semaines / 39 sessions avec intervalles structurés). EventBridge daily 05:00 UTC + on-demand. Futures semaines + athlete context (goal, assiduity, sport profile) injectés dans le contexte coach. Module activation check. Agent Browser Tool conservé en fallback. 26 tests unitaires.
- **Weekly Audio Recap V1** : Lambda `StravaAIBoost-WeeklyAudioRecap` (Bedrock Sonnet script 200-300 mots → Polly Generative Ambre → MP3 S3 privé). DynamoDB `strava-ai-boost-weekly-recaps` (PK user_id, SK week). EventBridge dimanche 20h UTC + on-demand via POST `/coach/recaps`. Frontend : section "Récaps hebdo" dans Coach page avec AudioPlayer, pagination, bouton "Générer", refresh button + polling (remplace setTimeout). On-demand utilise label date range (17_05-21_05), scheduler utilise ISO week Mon-Sun. AgentCore Memory + user prefs/PRs/pace zones + Campus goal context injectés dans le prompt. Coût estimé ~$0.05/recap.
- **Recovery State Widget** : card Coach page avec Form/TSB (color-coded frais/neutre/fatigué), VO2max (+delta 7j), FC repos (+delta 7j), Sommeil (moyenne 30j + delta 7j). Données Intervals.icu. InfoTooltip individuel sur chaque métrique + insight narratif contextuel.
- **Catégorisation fine des activités** : KPI "Séances" affiche les top 2 catégories non-Run (musculation, vélo, nage, rando, marche, yoga) au lieu de "X autre". Backend `other_sessions_breakdown` + frontend groupement par label traduit FR/EN.
- **Fix Coach LTM Memory** : `coach_agent.py` corrigé pour utiliser `searchCriteria` (API AgentCore Memory changée). `memoryRecordSummaries` au lieu de `memoryRecords`. Coach récupère maintenant les observations passées.
- **Voice debrief audio V1 (Polly Generative)** : stack `StravaAIBoost-VoiceDebrief` déployé. Bedrock Haiku 4.5 → script 60-90s → Polly Generative Ambre (FR) / Joanna (EN) → MP3 S3 privé → presigned URL 1h → AudioPlayer dans Activity detail. Coût ~$0.03/debrief. Trigger DynamoDB Stream idempotent.
- **Help tooltips Configuration + Preferences** : aide contextuelle sur Strava, modules, athlete profile, Max HR, records, pace zones, content style, demographics. 19 sections.
- **Help tooltips systématique sur tous les KPIs** : `(?)` Radix Popover sur chaque KPI (Dashboard 4, Coach 4 + Recovery 4, Quality 4). i18n FR/EN. Pattern via prop `info` sur composant KPI.
- **Map polyline Activity detail** : tracé GPS Leaflet (lazy-loaded 154kb, OpenStreetMap light / CartoDB dark, auto-fit bounds, 300px, rounded-xl). Polyline décodée inline (pas de dépendance externe). Fetch API automatique si données manquantes dans location.state.
- **Calories sur Activity detail** : tile 🔥 Calories (kcal) dans les stats. Backend extrait depuis `activity_data_json`.
- **Fix fun fact tronqué** : détection et suppression des fun facts incomplets (LLM coupe mid-sentence). Limite `enforce_preferences` augmentée (detailed: 1500→2500). Content agent `max_tokens` 2000→4096.
- **Polly Generative + voix Ambre** : engine `neural`→`generative` + voix FR `Lea`→`Ambre` sur voice debrief et weekly recap. Qualité vocale nettement supérieure.
- **Fix deploy script AgentCore** : parsing memory_id dupliqué (head -1), profil AWS manquant.
- **Empty states illustrés** : composant `EmptyState` + 6 SVG inline (activity, feedback, records, search, connect, celebrate). Migré 5 empty states.
- **Compliance Coach Now** : fix bug "5/5 = 100%" qui comptait toutes les activités au lieu des séances Campus complétées.
- **Content agent enrichi** : `personal_records` + `max_hr` injectés dans `user_profile`. `campus_coach_context` (semaines futures + athlete context) injecté dans le prompt.
- **Code review fixes** : `get_cached_or_compute` return, `useMemo`→`useEffect`, global `user_id` removed, `activity_id` endpoint, polling, audio duration.
- **All values configurable via env vars** : plus aucune valeur hardcodée (URLs, IDs, limites).
- **Backward compatibility** : Campus Coach sync backward-compatible with existing DynamoDB schema and consumer Lambdas (content_generator, coach_generator, coach_ask_api).
- **202 tests** : 162 backend + 40 frontend.
- **Plan Campus injection coach** : fix indentation `coach_generator.py` qui faisait que le plan n'était jamais injecté dans le contexte coach (sauf fallback WeekNumberIndex).
- **Coach chat sees Campus weekly plan** : `coach_ask_api.py` fetch maintenant les séances de la semaine + IAM index access via Core stack.
- **Quality > Memory column** : pastille icône color-coded + tooltip Radix au hover (mobile texte préservé).
- **Trends chart fixes** : axe Y allure intervalles snap multiples 10s + span min 30s + helper `computePaceAxis`. Fix bug critique : `interval_paces` agrège maintenant les fast laps en **1 point par séance** au lieu d'1 point par lap (causait points superposés et axe absurde). `slow_laps` défini explicitement (le `ef_paces` était cassé par NameError).
- **Trends "Semaine de récupération"** : wording reformulé pour être auto-explicatif.
- **Tooltips Coach Now** : `(?)` sur "Suivi du plan" et "Prochaine séance".
- Migration Cloudscape → Tailwind v4 + composants custom
- Dark / light avec toggle utilisateur
- Mobile-first (sidebar resizable + bottom nav)
- 6 pages refaites avec parité fonctionnelle 100% (Login, Dashboard, Coach, Quality, Configuration, Preferences)
- i18n FR/EN sur toute l'app (321 keys)
- Pagination Coach feedback avec choix de taille de page
- Sidebar collapsible + drag-resize avec persistance localStorage
- Hamburger menu visible jusqu'à 1024px (tablet + mobile) ouvrant le drawer de navigation
- Vite proxy dev pour bypass CORS
- Activity detail page (`/activities/:id`) avec drill-down depuis Dashboard
- Onboarding stepper (`/onboarding`, 4 étapes Welcome / Connect Strava / Modules / Preferences) + OnboardingHint sur Dashboard
- Animations subtiles : count-up KPIs, stagger sur les grilles, page transitions, prefers-reduced-motion respecté
- Coach Trends — insights narratifs calculés client-side sous chaque chart (volume, pace, ramp rate, EF, intervals)
- PWA installable (manifest, icons, theme-color, apple-touch, OG/Twitter)
- Code splitting (chunks < 500kb, index 578 → 92kb, suppression `@cloudscape-design/*`)
- Coach chat backend : injection des 12 dernières séances détaillées dans le contexte (DynamoDB) + AgentCore Memory pour les observations sémantiques
- **Deterministic Campus Coach matching** : pre-match sessions against laps in code (duration, interval count, pace analysis) instead of relying on LLM. Only best match sent to LLM. Sessions marked "Fait" in DynamoDB with correct keys. Already-done sessions filtered from future matching. Fixes wrong session matching bug.
- **Strength program tracking** : programme muscu structuré stocké dans `user_preferences.strength_program` (Upper A, Upper B, Rappel). Auto-tracking des charges via `strength_history` (description Strava parsée à chaque WeightTraining). Coach injecté avec programme + historique pour vision globale (total hebdo muscu+course, progressions charges, espacement recommandé).

## Next

> **Par où commencer (ordre suggéré)** : ~~quick wins ops~~ ✅ →
> ~~prérequis release OSS (disclaimer, fichiers standards, threat model, scan ASH,
> historique git nettoyé, tag v0.1.0)~~ ✅ (2026-07-15) →
> **reste avant public : screenshots/GIF README + purge cache GitHub** →
> ~~A2a (multi-tour chat)~~ ✅ (2026-07-16) → ~~A1 (tools) + A2b (runtime AGUI)~~ ✅ (2026-07-16) →
> **A3 (evals régression)** → le reste selon l'envie.
> Scan sensibilité + CVE + licence déjà faits.

### Quick wins ops — ✅ DONE (2026-07-10)

- [x] **DLQ monitoring + Lambda/queue alarmes** → topic SNS `strava-ai-boost-ops-alerts` (email). Les 3 alarmes existantes y sont branchées.
- [x] **Budget alert** — budget mensuel $35 (80% actual + 100% forecasted). ⚠️ Confirmer la subscription email SNS pour activer les notifications.
- [x] **Bug hallucination "Prochaine séance"** — vérifié : déjà résolu (tally `current_week` calculé serveur-side dans `dashboard_api.py`). Aucun code à écrire.
- [x] **Rule EventBridge legacy supprimée** — `StravaAIBoost-CampusCoach-DailyExtraction` retirée + toggle IAM nettoyé (le sync REST vérifie l'activation module en DynamoDB).
- [x] **Guardrail publié en v1** — au passage, corrigé un fail-open silencieux : le runtime `content_gen` pointait sur un guardrail ID inexistant.
- [x] **Fix crash activités manuelles/indoor** (2026-07-15) — `workout_classification=None` sans laps faisait planter le content agent (`NoneType.get()`). Guard `or {}` + `float()` sur champs numériques string. Testé sur activité 19305772266.

### Chantier agentic AgentCore (détail : [design/agentcore-agentic-improvements.md](./design/agentcore-agentic-improvements.md))

Validé contre la doc officielle AgentCore + Strands (2026-07-10). Numérotation =
regroupement thématique, pas ordre d'exécution — l'ordre est celui du « Par où
commencer » en tête (A2a avant A1 : 1 jour vs 1 semaine) :

- [x] **A1. Tools Strands pour le coach conversationnel** — ✅ fait le 2026-07-16. Runtime dédié `coach_chat` avec 4 `@tool` (`query_activities`, `get_campus_plan`, `get_pace_zones`, `get_intervals_metrics`) : l'agent va chercher la donnée au lieu du context stuffing figé. Débloque « compare mes 3 dernières séances de course ». Vérifié en réel (tool call visible + réponse token-par-token). **Strava MCP écarté** : allowlist Claude uniquement (DCR fermé, PKCE obligatoire). **Périmètre : mode conversation uniquement** — le mode feedback du pipeline (coach_generator) reste en context stuffing déterministe. Détail : [design/agentcore-agentic-improvements.md](./design/agentcore-agentic-improvements.md) §A1+A2b.
- [x] **A2a. Multi-tour sur le chat streamé** — ✅ fait le 2026-07-16. L'étude a amendé l'approche : `get_last_k_turns` rejeté (historique memory lossy par design), l'historique est fourni par le frontend et normalisé serveur-side (`build_converse_messages` dans `shared/coach_context.py`, whitelist rôles + alternance Converse). Contexte athlète déplacé dans le param `system`. Chemins stream + buffered unifiés sur le même helper. 19 tests. Détail : [design/agentcore-agentic-improvements.md](./design/agentcore-agentic-improvements.md) §2.
- [x] **A2b. Streaming unifié via AgentCore Runtime** — ✅ fait le 2026-07-16. Runtime dédié `coach_chat` (protocole AGUI natif, entrypoint FastAPI `/invocations`, `StrandsAgent.run` en `stream_async`), auth **customJWT** (ID token Cognito, claim `custom:strava_id` → `user_id`). ⚠️ **L'hypothèse initiale « garder un proxy Lambda » était fausse** : l'étude a montré que le data plane AgentCore renvoie `access-control-allow-origin: *` → le navigateur POST directement le SSE sur `bedrock-agentcore.{region}.amazonaws.com`, **sans proxy**. Le chemin Starlette (`coach_stream`) est donc supprimé, pas remplacé. Sessions runtime + observabilité GenAI actives. Fix rendu token-par-token (yield entre événements SSE bufferisés par AgentCore). Détail : [design/agentcore-agentic-improvements.md](./design/agentcore-agentic-improvements.md) §A1+A2b.
- [x] **A2b bis. Décommission legacy + finitions coach chat** — ✅ fait le 2026-07-16. Phase B : suppression des chemins superseded (Lambda `coach_stream` + Function URL + LWA, Cognito Identity Pool + SigV4, `coach_ask_api` + route `/coach/ask`, deps npm SigV4). Le runtime `coach_chat` est le **seul** transport (pas de fallback ; erreur UI explicite). Accès descriptions ajouté au tool `query_activities` (note originale de l'athlète + description IA, 500 car.) → le coach lit les exercices/ressenti, plus seulement les métriques. Fixes annexes : alias FR de type (`muscu`→WeightTraining), date du jour injectée dans le prompt (le modèle envoyait `2025` vs data `2026`), rendu markdown du chat (gras/listes). Docs (README/AGENTS/threat-model) alignées.
- [ ] **A3. AgentCore Evaluations** (GA mars 2026) — commencer par l'**on-demand en régression** (jeu de ~10 activités de référence, rejoué à chaque changement de `embedded_prompts.py` / `COACH_AGENT_SYSTEM_PROMPT`) : c'est là qu'est la valeur en mono-user. Custom evaluators pour nos règles maison (anti-em-dash, anti-clichés IA, strava_block orienté tendances, chiffres hebdo réels). L'online eval du trafic prod est secondaire à ~5 activités/semaine — l'activer surtout comme vitrine pour le sample OSS. Rend l'A/B de prompts possible → tire l'externalisation d'`embedded_prompts.py` (BACKLOG P3).
- [ ] **A4. Stratégie memory sur `coaching_observations`** — EPISODIC (episodes/{sessionId} + reflectionNamespaces) pour consolider au lieu d'accumuler ; searchQuery dynamique selon le type de séance. Nuance : à ~5 activités/semaine, l'accumulation brute ne sature pas avant des mois — l'urgence est faible ; le vrai gain court-terme est la **searchQuery dynamique** (1 h de travail), la stratégie EPISODIC peut attendre A2b.
- [ ] **A5. Migration toolchain (réactif, pas proactif)** — AWS a lancé le CLI `agentcore` (npm, avril 2026, déploiement CDK) qui remplace à terme `bedrock-agentcore-starter-toolkit` (pip) + `.bedrock_agentcore.yaml`. ⚠️ La « dépréciation » du toolkit pip vient des guides MCP, **pas d'une annonce AWS officielle** — vérifiée le 2026-07-10, pas de notice de dépréciation publique. Le déploiement actuel fonctionne : **ne migrer que si** le toolkit pip casse, ou à l'occasion d'un gros changement d'agent (A2 est le bon moment). Le SDK runtime ne change pas. Occasion d'adopter AgentCore Identity (token vault) au passage.
- Gateway + Policy (Cedar) : **plus tard**, seulement si multi-tenant ou mutualisation des tools entre agents.

### Court terme (1-2 semaines)

- [ ] **Strava FIT sets data ingestion** — Depuis le 21 mai 2026, Strava ingère les sets structurés (exercice, reps, poids, durée) depuis les fichiers FIT. Lire ces données via l'API pour alimenter `strength_history` automatiquement (plus besoin de parser la description). Rend le tracking muscu 100% automatique et précis.
- [ ] **Coach Trends : graphiques progression muscu** — Ajouter des charts dans la page Coach Trends pour visualiser les progressions de charges (DC, tractions, etc.) au fil du temps. Données depuis `strength_history`. Même pattern que les charts pace/volume existants.
- [ ] **Deauthorization endpoint** — Implémenter le nouveau endpoint Strava (1er juin 2026) pour un disconnect propre dans le flow OAuth.
- [ ] **Détection d'anomalie santé** *(nouveau)* — check déterministe (pas de LLM) sur les données déjà stockées : « FC repos +8 bpm et HRV -20% sur 3 jours → alerte repos ». Haute valeur perso, coût quasi nul. **V1 sans push** : banner/card sur le Dashboard + injection dans le contexte coach (ne pas attendre l'infra notifications du moyen terme).

### Release open-source (track dédié — c'est le « produit »)

Prérequis **faits** (2026-07-10) :

- [x] **Scan sensibilité** (skill `scan-opensource`) — `config.json` untracké + `.example`, `default_user_id`/`alert_email` déplacés dans `cdk.context.json`, proxy Vite via env var, URLs réelles → placeholders dans README/AGENTS/index.html, ref interne (domaine a2z) retirée. Re-scan des fichiers trackés : propre.
- [x] **Bump CVE** — Python : 0 vuln (pip-audit sur les 2 requirements). Frontend : 9 → 0 (vite/vitest bumpés).
- [x] **Licence** — MIT-0 déjà en place.

Reste avant publication GitHub :

- [x] **Disclaimer non-production** en tête de README (« demo/personal-use sample », known issues listées) — 2026-07-15
- [x] **Fichiers OSS standards** — CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, templates issue/PR (`.github/`) — 2026-07-15
- [x] **README** : GIF démo (parcours frontend complet, accéléré, `docs/demo.gif`) + MP4 pleine longueur en asset de la release v0.1.0 — 2026-07-15
- [x] **Threat model 1 page** (`docs/THREAT-MODEL.md`) — STRIDE, 13 menaces T1-T13 + threats de release publique — 2026-07-15
- [x] **Scan ASH** (Bandit, Semgrep, Checkov, detect-secrets, npm-audit) — 0 finding réel sur code first-party (tout en artefacts build/tests/deps vendorées/faux positifs i18n). Summary : `docs/SECURITY-SCAN.md` — 2026-07-15
- [x] **Historique git nettoyé (même repo, pas repo neuf)** — `git filter-repo` + mailmap : scrubbé user_id, 3 account IDs (dont 2 hors mapping initial), API key/ID, profils AWS, email interne ; auteur git unifié sous l'identité GitHub publique. Backup bundle local. Force-push `dev` (seule branche remote). Vérif : 0 chaîne sensible. (repo privé → anciens SHA GC automatiquement par GitHub, non bloquant). — 2026-07-15
- [x] **Tag v0.1.0 + CHANGELOG.md** — CHANGELOG (Keep a Changelog) + tag annoté poussés — 2026-07-15
- [ ] **Blog post** (structure déjà esquissée dans BACKLOG.md)

> **Reste avant de rendre le repo public** : (aucun bloquant technique). Le repo étant privé, les anciens SHA pré-réécriture seront GC par GitHub automatiquement — non bloquant. Le blog post peut suivre la publication.

**Séquencement (tranché, repris dans l'ordre en tête) : release d'abord.**
Publier v0.1.0 avec l'état actuel — qui est déjà un bon sample : pipeline
event-driven, memory, guardrails, streaming AG-UI. Les chantiers A1-A3
deviennent du contenu de suivi (v0.2, blog post #2). Rationale : la release ne
doit pas glisser derrière des chantiers de plusieurs semaines — le piège
classique du « encore une feature avant de publier ».

**Prérequis incompressibles** avant tout push public : scan sensibilité,
bump CVE, disclaimer, licence. Le reste (threat model, GIF, blog) peut suivre
la publication.

### Moyen terme — features perso (si l'envie et l'usage le justifient)

- [ ] **Strava MCP integration** — serveur MCP remote Strava (`https://mcp.strava.com/mcp`, 1er juin 2026). Read-only, OAuth, streams per-second, fitness trends, readiness. À faire **dans le même chantier que A1** (Strands branche les serveurs MCP comme des tools). ⚠️ Deux réserves : réservé aux **abonnés Strava** (l'app tourne aujourd'hui sans abo — c'est une dépendance payante nouvelle) et redondance partielle avec Intervals.icu déjà intégré (fitness trends, readiness). La valeur unique réelle : streams per-second. Vérifier le rapport valeur/abo avant de s'engager. Bonus : très bon sujet de blog post.
- [ ] **Notifications push PWA** — infra générique (activité enrichie, briefing matinal, alerte anomalie). Prérequis des deux suivants.
- [ ] **Pre-run briefing contextuel** — Form/TSB + séance Campus du jour + météo → push le matin (« Seuil 3×10 min prévu, TSB -15, vise le bas de la fourchette »). Données déjà en DynamoDB.
- [ ] **Bilan de cycle Campus** — fin de bloc : compliance, progression EF, charges muscu, verdict vs objectif. Même pattern que le weekly recap, une échelle au-dessus.
- [ ] **Race readiness simple** — prédiction 5K/10K/semi depuis les PRs auto-accumulés + goal Campus (date d'objectif déjà syncée). Version 1-2 jours, carte sur Dashboard. Pas de plan adaptatif maison : Campus fournit déjà le plan.
- [ ] **Veille Strava API fees** — "Subscription required" Standard Tier (06/2026). L'app tourne en free tier (1 athlète, 100 reads/15min) — surveiller que ça reste vrai ; c'est aussi une contrainte à documenter pour les users du sample OSS.

### Long terme — exploratoire

- [ ] **Coach vocal live (Nova Sonic)** — speech-to-speech temps réel. Prérequis technique : A2b (architecture de session streamée via Runtime). Excellent sujet de démo/blog, à faire pour l'exploration plus que pour le besoin.
- [ ] **App mobile** — la PWA + push couvre l'essentiel ; natif seulement si le besoin watchOS/WearOS devient réel.

> Retirés de la roadmap (positionnement open-source, pas produit) : landing page,
> pricing/Stripe, mode coach pro, API publique, multi-langue ES/DE/IT,
> intégrations Garmin/Polar/Suunto, et les idées growth de l'analyse
> concurrentielle (badges, partage viral, cohortes, marketplace).
> [COMPETITIVE-ANALYSIS.md](./COMPETITIVE-ANALYSIS.md) reste comme archive.

## Tech debt à surveiller

Pertinente pour la crédibilité du sample OSS (un lecteur va juger le repo là-dessus) :

- **CI/CD absent** — `cdk deploy` manuel. GitHub Actions minimal : tests + `cdk diff` sur PR. Quasi indispensable pour un repo public (BACKLOG P2).
- **cdk-nag absent** — `Aspects.of(app).add(AwsSolutionsChecks())` à activer + trier les findings sur les 8 stacks. Chantier dédié (BACKLOG P2), mais fort signal qualité pour un sample AWS.
- **Token refresh dupliqué dans 4 Lambdas** — extraire dans `shared/strava_token_manager.py` (BACKLOG P2). Un contributeur le verra tout de suite.
- **Lambda Layer build manuel** (`LAYER_ASSET_HASH`) — oubli = deps stales. Automatiser dans un script (BACKLOG P2).
- **`except Exception` génériques** (20+) avec return None silencieux — au minimum les 3 critiques du BACKLOG.

Confort / plus tard :

- Lambda ARM64 (Graviton) — ~20 % de coût en moins, rebuild layer requis
- Chunks > 500kb (CoachPage, index)
- CDK feature flags (~35/58) — bruit de warnings à chaque synth
- Migration config dead code dans `activity_fetcher.py`
- `@cloudscape-design` toujours en `package.json` (inutilisé) — `npm prune`
- Vitest setup i18n EN forcé : à ajuster si tests dépendant du FR
- ATXDocumentation supprimée — si re-générée par Kiro, rester strict
