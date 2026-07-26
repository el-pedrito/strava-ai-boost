# Roadmap

> Strava AI Boost — roadmap consolidée le 2026-07-10.
> **Positionnement tranché : projet perso + publication open-source.**
> Pas de produit fini, pas de SaaS, pas de monétisation — les items
> landing/pricing/Stripe/coach-pro/marketplace sont retirés.
> Deux axes : (1) valeur perso au quotidien, (2) qualité de sample
> open-source (showcase AgentCore/Bedrock/CDK).
> Détail agentic : [design/agentcore-agentic-improvements.md](./design/agentcore-agentic-improvements.md).

## Done

- **Passe qualité repo + release v0.2.0 (2026-07-17 après-midi)** : audit spécialisé des 21 fichiers markdown contre la vérité terrain (8 stacks, 18 Lambdas, 1 memory) — 15 fichiers corrigés (SECURITY.md décrivait l'auth SigV4 décommissionnée, BACKLOG réécrit, MIT→MIT-0…). Nouveau : `docs/architecture.md` (briques AgentCore d'abord, support du post LinkedIn/blog) + **3 diagrammes draw.io** (high-level, détaillé, services AWS avec icônes officielles) exportés en `.drawio.svg` rendus par GitHub ; **garde anti-dérive documentaire** `test_docs_sync.py` (claims des docs vérifiés contre le code) + hook Kiro `stop` (`scripts/check_docs_sync.sh`). Mémoire reliquat `strava_ai_boost_coach_mem` supprimée (vide, non référencée). **v0.2.0 taguée + GitHub Release publiée.** Verdicts : metadataFilters close (pas de propagation event→record) ; stratégie EPISODIC **prouvée en live** (épisode + réflexion générés en ~15 min).

- **Court terme muscu + santé + deauth (2026-07-16)** : (1) **extraction LLM des séances muscu** (Haiku/Converse) → `parsed_sets` dans DynamoDB ; (2) **charts progression muscu** dans Coach Trends (charge/volume par exercice) ; (3) **détection d'anomalie santé** déterministe (alertes onglet Coach Now) ; (4) **tests de déautorisation Strava** (flow déjà implémenté). Tout déployé (Content + API + frontend). **Correction factuelle** : l'app Strava est **active** (premium, scope complet vérifié en live) — le « 403 Inactive » précédent était un simple token expiré.
- **Décommission `campus_coach` (2026-07-16)** : agent Browser Tool + Lambda fallback `campus_coach_invoker` supprimés (runtime AgentCore + mémoire détruits dans AWS, code/CDK/scripts/tests nettoyés). Le sync REST `campus_coach_sync` reste la source unique. Reste 3 runtimes AgentCore (`content_gen`, `strava_ai_boost_coach`, `coach_chat`).
- **Campus Coach : migration Browser Tool → API REST directe** : Lambda `campus_coach_sync.py` (`POST /account/login` + `GET /smart-training` → DynamoDB, 9 semaines / 39 sessions avec intervalles structurés). EventBridge daily 05:00 UTC + on-demand. Futures semaines + athlete context (goal, assiduity, sport profile) injectés dans le contexte coach. Module activation check. Agent Browser Tool conservé en fallback *(superseded : décommissionné le 2026-07-16, cf. item ci-dessus)*. 26 tests unitaires.
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
- **Tests** : 396 (302 backend unit + 41 régression + 53 frontend, au 2026-07-26).
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
> historique git nettoyé, tag v0.1.0, screenshots/GIF README)~~ ✅ (2026-07-15) →
> ~~A2a (multi-tour chat)~~ ✅ → ~~A1 (tools) + A2b (runtime AGUI)~~ ✅ (2026-07-16) →
> ~~court terme muscu/santé/deauth~~ ✅ (2026-07-16) →
> ~~A3 (evals régression V1 + V2 managée)~~ ✅ → ~~A4 (mémoire : fixes + EPISODIC + unification)~~ ✅ →
> ~~passe qualité docs + architecture (3 draw.io) + garde anti-dérive + release v0.2.0~~ ✅ (2026-07-17) →
> **maintenant : (1) rendre le repo public (aucun bloquant technique restant, v0.2.0 taguée + GitHub Release prête), (2) post LinkedIn (s'appuyer sur docs/architecture.md), (3) peupler les charts muscu via reprocessing d'une vraie séance, (4) backfill PRs Strava (si envie).**
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
- [x] **A3. Évals de régression des prompts** — ✅ **V1 + V2 faits** (2026-07-16/17), spec : [design/regression-evals.md](./design/regression-evals.md). **V1** : harnais local déterministe (8 fixtures synthétiques, 8 critères, `scripts/run_prompt_regression.py` sur le runtime déployé, ~0,20 $/run, baseline 0 fail/1 warn). Dès ses premiers runs il a attrapé **2 crashes réels de l'agent** (max_cadence jamais renvoyé par Strava, average_speed string) et **4 exemples auto-contradictoires du prompt** (clichés bannis utilisés comme modèles positifs). **V2 managée** : AgentCore Evaluations sur les mêmes fixtures (`build_eval_dataset.py` → dataset `PredefinedScenario`, `run_managed_evals.py` avec `OnDemandEvaluationDatasetRunner`, 3 built-ins + 2 custom evaluators LLM-as-a-Judge `VoixAuthentiqueFR`/`FideliteDonneesActivite`, ~1,2 $/run, baseline **0 fail/8 warn** — 11 warn avant l'ajout des exemples few-shot au prompt, 8 après). Confirmé en live : les juges LLM font des erreurs d'arithmétique (faux « chiffre inventé » sur un lap de 1100 m) → customs = **signal warn**, les gates restent les checks déterministes V1. `StravaBlockTendances` attend des fixtures coach (V3 éventuelle).
- [x] **A4. Mémoire coach — audit + fixes** — ✅ 2026-07-17, spec : [design/memory-improvements.md](./design/memory-improvements.md). L'audit live a révélé **bien pire que le sujet initial** : la boucle mémoire était **cassée**. (1) Le coach lisait `coaching_observations/{uid}` — un namespace qu'**aucune stratégie n'alimente** → 0 observation relue depuis toujours ; les records réels vivent dans `/strategies/{strategyId}/actors/{uid}/` (extraits par la stratégie SEMANTIC). (2) `weekly_audio_recap` : triple panne silencieuse (namespace invalide + ancienne forme d'API + **rôle IAM sans aucune action bedrock-agentcore**). Fixes : lecture par découverte du strategyId (`get_memory`, caché, pas d'ID hardcodé, fallback prefix), **searchQuery dynamique par type de séance** (muscu → progression charges ; fractionné/longue/tempo/EF différenciés — pertinence vérifiée live : 5 observations ciblées vs 0 avant), recap réparé + IAM ajouté. +11 tests. Déployé (runtime coach + stack VoiceDebrief). **Suites faites le jour même (V2/V3)** : 5e tool chat `get_coach_observations` (continuité chat↔pipeline), stratégie **EPISODIC** `CoachingEpisodes` (épisodes + réflexions niveau actor), **namespaces unifiés** `/strategies/{strategyId}/actors/{actorId}/` avec migration sans perte des 28 records de préférences (modif in-place, pas de recréation), hygiène events auditée (365j/43 events : rien à faire). Seule piste ouverte : metadataFilters par sport (spike fait, propagation event→record non démontrée).
- [ ] **A5. Migration toolchain (réactif, pas proactif)** — AWS a lancé le CLI `agentcore` (npm, avril 2026, déploiement CDK) qui remplace à terme `bedrock-agentcore-starter-toolkit` (pip) + `.bedrock_agentcore.yaml`. ⚠️ La « dépréciation » du toolkit pip vient des guides MCP, **pas d'une annonce AWS officielle** — vérifiée le 2026-07-10, pas de notice de dépréciation publique. Le déploiement actuel fonctionne : **ne migrer que si** le toolkit pip casse, ou à l'occasion d'un gros changement d'agent (A2 est le bon moment). Le SDK runtime ne change pas. Occasion d'adopter AgentCore Identity (token vault) au passage.
- Gateway + Policy (Cedar) : **plus tard**, seulement si multi-tenant ou mutualisation des tools entre agents.

### Court terme (1-2 semaines) — spec détaillée : [design/short-term-improvements.md](./design/short-term-improvements.md)

- [x] **Parser muscu structuré** *(ex-« Strava FIT sets »)* — ✅ 2026-07-16. Rappel : l'API Strava **n'expose pas** les sets en lecture (`DetailedActivity` n'a aucun champ) et ne permet pas de les écrire sur une activité existante → pivot assumé : l'athlète écrit ses séances en commentaire. Implémenté via **extraction LLM** (Haiku/Converse, JSON, temp 0) plutôt qu'un regex déterministe — gère mieux le texte libre (`DC 4x8 @80kg` → `{exercise, sets, reps, weight_kg}`). Best-effort → `[]` sur toute erreur, stocké dans `strength_history.entries[].parsed_sets` **à côté** de la description brute (jamais à la place). +7 tests. Déployé.
- [x] **Coach Trends : graphiques progression muscu** — ✅ 2026-07-16. `/coach/summary` agrège `parsed_sets` par exercice (`_build_strength_progression` : charge max + volume total par jour, trié par nb de séances). Composant `StrengthProgression` (recharts LineChart, pattern pace/EF) avec sélecteur d'exercice + toggle charge/volume ; liste brute conservée en fallback si < 3 points structurés. +4 tests. Déployé. ⚠️ Se remplira avec de vraies séances (aucune donnée `parsed_sets` historique pour l'instant — voir « à faire après »).
- [x] **Détection d'anomalie santé** *(déterministe, additif)* — ✅ 2026-07-16. `_detect_health_anomalies` (fonction pure, `dashboard_api`) sur la recovery Intervals.icu déjà calculée : FC repos +5 bpm/7j & TSB < -20 (warning), sommeil ≤ -45 min/7j & VO2max ≤ -1/7j (info). Exposé en `trends.health_anomalies`, affiché en **alertes dans l'onglet Coach « Now »**. Garde-fous sur champs manquants → aucun faux positif sur données partielles. +7 tests. Déployé. **Écarts vs spec initiale (suivi éventuel)** : surfacé côté Coach et *pas* en banner Dashboard ; *pas encore* injecté dans le contexte coach ; le delta HRV n'est pas dans le payload recovery → règle sous-récup basée sur la seule FC repos (pas HRV -10%).
- [x] **Endpoint de déautorisation Strava** — **confirmé** (changelog 1 juin 2026). Flow « Déconnecter Strava » : bouton + dialog confirmation → `DELETE /config/oauth` (Cognito) → `POST /oauth/deauthorize` Strava + effacement tokens Secrets Manager. ⚠️ **destructif** (tokens) : idempotent, ne supprime **pas** les données d'activités, réversible via re-OAuth. Déjà implémenté (`revoke_oauth_tokens` + `OAuthConnection.tsx`) ; tests unitaires mockés ajoutés le 2026-07-16 (l'app est active mais tester en live déconnecterait le vrai compte).

**Séquencement** : ~~anomalie santé → parser muscu → charts muscu → déautorisation~~ ✅ **les 4 items faits + déployés le 2026-07-16.** Reste optionnel en suivi : injection des anomalies santé dans le contexte coach + banner Dashboard ; peupler les charts muscu via reprocessing d'une vraie séance `WeightTraining`.

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

- [ ] **Backfill des PRs depuis l'historique Strava** *(idée 2026-07-16)* — les `best_efforts_prs` sont déjà auto-accumulés à chaque activité traitée (`coach_generator._extract_best_efforts`), mais seulement **depuis l'installation** : l'historique d'avant est invisible, d'où la saisie manuelle. L'API publique n'a **pas** d'endpoint global « athlete best efforts », mais chaque `DetailedActivity` expose les siens → script one-shot `scripts/backfill_best_efforts.py` : lister les runs historiques (`GET /athlete/activities` paginé) + `GET /activities/{id}` chacun, throttlé sous le rate limit (100 req/15min ; ~300 runs ≈ 45-60 min), merge dans `best_efforts_prs` existant (même règle « meilleur temps gagne »). Les PRs **manuels** restent utiles pour les chronos de course officiels (l'API ne connaît que les best efforts GPS).
- [ ] **Strava MCP integration** — serveur MCP remote Strava (`https://mcp.strava.com/mcp`, 1er juin 2026). Read-only, OAuth, streams per-second, fitness trends, readiness. À faire **dans le même chantier que A1** (Strands branche les serveurs MCP comme des tools). ⚠️ Deux réserves : réservé aux **abonnés Strava** (l'abonnement est déjà actif sur le compte — pas de coût nouveau ici, mais la contrainte reste vraie pour les forks du sample) et redondance partielle avec Intervals.icu déjà intégré (fitness trends, readiness). La valeur unique réelle : streams per-second. Vérifier le rapport valeur/abo avant de s'engager. Bonus : très bon sujet de blog post.
- [ ] **Notifications push PWA** — infra générique (activité enrichie, briefing matinal, alerte anomalie). Prérequis des deux suivants.
- [ ] **Pre-run briefing contextuel** — Form/TSB + séance Campus du jour + météo → push le matin (« Seuil 3×10 min prévu, TSB -15, vise le bas de la fourchette »). Données déjà en DynamoDB.
- [ ] **Bilan de cycle Campus** — fin de bloc : compliance, progression EF, charges muscu, verdict vs objectif. Même pattern que le weekly recap, une échelle au-dessus.
- [ ] **Race readiness simple** — prédiction 5K/10K/semi depuis les PRs auto-accumulés + goal Campus (date d'objectif déjà syncée). Version 1-2 jours, carte sur Dashboard. Pas de plan adaptatif maison : Campus fournit déjà le plan.
- [ ] **Veille Strava API fees** — "Subscription required" Standard Tier (06/2026). L'abonnement Strava est **actif** sur le compte (premium) — l'accès API est acquis ; surveiller les évolutions de pricing/quotas. C'est surtout une contrainte à documenter pour les users du sample OSS : un fork dont le compte Strava n'est pas abonné voit son app passer `Inactive` (403).

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

- **CI/CD absent** — `cdk deploy` manuel. GitHub Actions minimal : tests + `cdk diff` sur PR. Quasi indispensable pour un repo public (BACKLOG P2). En bonus : workflow `workflow_dispatch` manuel pour les évals de régression live (secret AWS requis, jamais sur PR publique — cf. spec regression-evals).
- **cdk-nag absent** — `Aspects.of(app).add(AwsSolutionsChecks())` à activer + trier les findings sur les 8 stacks. Chantier dédié (BACKLOG P2), mais fort signal qualité pour un sample AWS.
- **Token refresh dupliqué dans 4 Lambdas** — extraire dans `shared/strava_token_manager.py` (BACKLOG P2). Un contributeur le verra tout de suite.
- **Lambda Layer build manuel** (`LAYER_ASSET_HASH`) — oubli = deps stales. Automatiser dans un script (BACKLOG P2).
- **`except Exception` génériques** (20+) avec return None silencieux — au minimum les 3 critiques du BACKLOG.
- **Frontend — pages monolithiques + dédup UI + micro-bug KPI** — chantier de maintenabilité cadré en spec : [design/frontend-maintainability.md](./design/frontend-maintainability.md). ✅ **Items 4 & 5 livrés le 2026-07-21** (`UserMenu` partagé Sidebar/Topbar + prop `deltaUnit` sur `KPI`, 9 tests ajoutés). En passant : `frontend/src/lib/` était avalé par la règle `lib/` du `.gitignore` racine — `cn.ts`/`motion.ts` recréés et dé-ignorés (un clone frais ne buildait pas). Reste : **item 3** (découpage des grosses pages — `CoachPage.tsx` ~66 KB en tête) + `eslint.config.js` jamais commité. Quick-wins de la même review (2026-07-17) **déjà livrés** hors spec : CSS legacy mort supprimé (`styles/global.css`, ~150 lignes non utilisées + couleurs hardcodées cassant le dark mode) + dérive doc « Cloudscape » corrigée dans `AGENTS.md`.

Confort / plus tard :

- [x] ~~Vérifier weekly_synthesis en live~~ — ✅ **confirmé le 2026-07-21** (logs CloudWatch) : le run pré-fix du 2026-07-12 échouait bien en `AccessDeniedException` sur `bedrock:InvokeModel` (inference profile) — la Lambda était silencieusement cassée comme suspecté. Le run post-fix du **2026-07-19 20:00 UTC a réussi** : « Weekly synthesis generated: 6 sessions, 14.4km », 9 s, aucune erreur. La centralisation LLM du 2026-07-17 a bien réparé le rôle IAM.
- [x] ~~Nettoyer la plomberie campus inerte de `configure_agentcore_integration.sh`~~ — ✅ 2026-07-17 : dé-threading complet (détection, IAM, env vars Lambda, cdk context, env file, résumé), retrait du grant secret campus des rôles agents (plus aucun agent ne le lit) et des références aux Lambdas décommissionnées (CampusCoachInvoker, CoachAskAPI). Conservé : les grants de la table `campus-coaching-sessions` (lue par le tool `get_campus_plan` de coach_chat).
- [x] ~~Purger les records orphelins `default_user`~~ — ✅ 2026-07-17 : **migrés plutôt que purgés** — inspection préalable : ils contenaient des préférences apprises uniques (mai 2026, pré-multi-user) → 19/19 copiés vers l'actor réel puis supprimés. Le contenu appris est préservé et de nouveau servi par les lectures.

- Lambda ARM64 (Graviton) — ~20 % de coût en moins, rebuild layer requis
- Chunks > 500kb (CoachPage, index)
- CDK feature flags (~35/58) — bruit de warnings à chaque synth
- Migration config dead code dans `activity_fetcher.py`
- `@cloudscape-design` toujours en `package.json` (inutilisé) — `npm prune`
- Vitest setup i18n EN forcé : à ajuster si tests dépendant du FR
- ATXDocumentation supprimée — si re-générée par Kiro, rester strict
