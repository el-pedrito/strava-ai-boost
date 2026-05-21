# Roadmap

> Strava AI Boost — direction produit après la refonte UI (mai 2026).
> Pour le contexte concurrentiel et la justification des priorités, voir [COMPETITIVE-ANALYSIS.md](./COMPETITIVE-ANALYSIS.md).

## Done

- **Weekly Audio Recap V1** : Lambda `StravaAIBoost-WeeklyAudioRecap` (Bedrock Sonnet script 200-300 mots → Polly Generative Ambre → MP3 S3 privé). DynamoDB `strava-ai-boost-weekly-recaps` (PK user_id, SK week). EventBridge dimanche 20h UTC + on-demand via POST `/coach/recaps`. Frontend : section "Récaps hebdo" dans Coach page avec AudioPlayer, pagination, bouton "Générer". On-demand utilise label date range (17_05-21_05), scheduler utilise ISO week. Coût estimé ~$0.05/recap.
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

## Next

### Court terme (1-2 semaines)

- [x] **Catégorisation fine des activités "other"** — KPI affiche top 2 catégories (musculation, vélo, etc.)
- [x] **Recovery state widget Coach Now** — Form/TSB, VO2max, FC repos, Sommeil avec deltas 7j depuis Intervals.icu
- [x] **Help tooltip systématique sur chaque KPI** — `(?)` Radix Popover sur tous les KPIs (Dashboard, Coach, Quality, Recovery). i18n FR/EN.
- [x] **Map polyline sur Activity detail** — tracé GPS Leaflet (lazy-loaded, dark mode, auto-fit bounds)
- [ ] **Notifications in-app** : "Ton activité X a été enrichie" (toast persistant à la connexion)

### Moyen terme (1-2 mois)

- [ ] **Race time prediction + plan adaptatif minimum viable** — Strava vient de bundler Runna (-60%) précisément pour combler ce trou (cf [analyse](./COMPETITIVE-ANALYSIS.md)). Devient un standard que les users vont attendre.
- [x] **Recap audio hebdomadaire type podcast** — déployé 20 mai 2026. Dimanche 20h UTC + on-demand (label date range). Bedrock Sonnet + Polly Generative Ambre. Paginé dans Coach page.
- [ ] **Mémoire long terme + multi-tour soignée pour le Coach IA** — déjà partiellement câblée (AgentCore Memory). Strava Athlete Intelligence est mono-tour. Si l'UX est soignée, vraie différenciation.
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
