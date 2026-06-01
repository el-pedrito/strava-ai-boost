# Roadmap

> Strava AI Boost — direction produit après la refonte UI (mai 2026).
> Pour le contexte concurrentiel et la justification des priorités, voir [COMPETITIVE-ANALYSIS.md](./COMPETITIVE-ANALYSIS.md).

## Done

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

### Court terme (1-2 semaines)

- [x] **Catégorisation fine des activités "other"** — KPI affiche top 2 catégories (musculation, vélo, etc.)
- [x] **Recovery state widget Coach Now** — Form/TSB, VO2max, FC repos, Sommeil avec deltas 7j depuis Intervals.icu
- [x] **Help tooltip systématique sur chaque KPI** — `(?)` Radix Popover sur tous les KPIs (Dashboard, Coach, Quality, Recovery). i18n FR/EN.
- [x] **Map polyline sur Activity detail** — tracé GPS Leaflet (lazy-loaded, dark mode, auto-fit bounds)
- [x] **Campus Coach : migration Browser Tool → API REST directe**
  - `POST api.campus.coach/account/login` + `GET /smart-training?from=...&to=...` retourne toutes les semaines accessibles en JSON structuré
  - Lambda `campus_coach_sync.py` : login → fetch → store DynamoDB (9 semaines, 39 sessions, structured intervals)
  - EventBridge daily 05:00 UTC + on-demand
  - All future weeks injected into coach context
  - Athlete context (goal, assiduity, sport profile) persisted
  - Module activation check : ne sync que si campus_coach module activé
  - Agent Browser Tool conservé comme fallback (non supprimé)
  - 26 tests unitaires (14 sync + 12 consumers)
- [ ] **Strava FIT sets data ingestion** — Depuis le 21 mai 2026, Strava ingère les sets structurés (exercice, reps, poids, durée) depuis les fichiers FIT. Lire ces données via l'API pour alimenter `strength_history` automatiquement (plus besoin de parser la description). Rend le tracking muscu 100% automatique et précis.
- [ ] **Coach Trends : graphiques progression muscu** — Ajouter des charts dans la page Coach Trends pour visualiser les progressions de charges (DC, tractions, etc.) au fil du temps. Données depuis `strength_history`. Même pattern que les charts pace/volume existants.
- [ ] **Deauthorization endpoint** — Implémenter le nouveau endpoint Strava (1er juin 2026) pour un disconnect propre dans le flow OAuth.

### Moyen terme (1-2 mois)

- [ ] **Race time prediction + plan adaptatif minimum viable** — Strava vient de bundler Runna (-60%) précisément pour combler ce trou (cf [analyse](./COMPETITIVE-ANALYSIS.md)). Devient un standard que les users vont attendre.
- [x] **Recap audio hebdomadaire type podcast** — déployé 20 mai 2026. Dimanche 20h UTC + on-demand (label date range). Bedrock Sonnet + Polly Generative Ambre. Paginé dans Coach page.
- [ ] **Mémoire long terme + multi-tour soignée pour le Coach IA** — déjà partiellement câblée (AgentCore Memory). Strava Athlete Intelligence est mono-tour. Si l'UX est soignée, vraie différenciation.
- [ ] **Strava MCP integration** — Strava a lancé un serveur MCP remote (`https://mcp.strava.com/mcp`) le 1er juin 2026. Read-only, OAuth, accès aux streams per-second, fitness trends, readiness. Réservé aux abonnés Strava. Potentiel pour enrichir le coach conversationnel avec des données qu'on n'a pas aujourd'hui (streams HR per-second, fitness trends natives). Limité : read-only donc on garde l'API pour le write (update title/description).
- [ ] **API fees mitigation** — Strava introduit un "Subscription required" pour le Standard Tier développeur (1er juin 2026). Pas clair si c'est l'abo athlete classique (~$12/mois), un dev fee séparé ($11.99/mois), ou si les apps single-player existantes sont grandfathered. À surveiller : si l'accès API est coupé, il faudra payer. Actuellement l'app fonctionne sans abo (tier gratuit 1 athlète, 100 reads/15min).
- [ ] **Landing page publique** (`/`) avant login : value prop, démo, screenshots, FAQ
- [ ] **Pricing page** Free / Pro / Coach avec Stripe Checkout
- [ ] **Stripe customer portal** pour gérer abonnement
- [ ] **Notifications push** quand une activité est enrichie (PWA push API)

### Long terme (3-6 mois)

- [ ] **Coach conversationnel vocal en live (Nova Sonic)** — speech-to-speech bidirectionnel temps réel via Amazon Nova Sonic. L'user parle au coach pendant/après sa séance, le coach répond en voix naturelle avec interruptions possibles. Différenciation forte (aucun concurrent ne le propose en mainstream). Latence ~600ms first-token, plus cher que Polly mais imbattable pour l'expérience conversation. Évolution de la V1 audio Polly : V1 = MP3 statique post-séance / dimanche, V2 = dialogue live.
- [ ] **Multi-language au-delà de FR/EN** : ES, DE, IT
- [ ] **Mode "Coach pro"** : un coach humain peut gérer plusieurs athlètes via la même UI
- [ ] **Intégrations supplémentaires** : Garmin Connect, Polar Flow, Suunto
- [ ] **API publique** : webhook pour développeurs tiers
- [ ] **App mobile native** (React Native ou Capacitor)

## Tech debt à surveiller

- Chunks > 500kb (CoachPage, index)
- ATXDocumentation supprimée — si re-générée par Kiro, rester strict
- `@cloudscape-design` package toujours en `package.json` (pas utilisé) — à retirer au prochain `npm prune`
- Vitest setup utilise i18n EN forcé : si on ajoute des tests qui dépendent de FR, à ajuster
