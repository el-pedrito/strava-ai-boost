# Roadmap

> Strava AI Boost — direction produit après la refonte UI (mai 2026).
> Pour le contexte concurrentiel et la justification des priorités, voir [COMPETITIVE-ANALYSIS.md](./COMPETITIVE-ANALYSIS.md).

## Done

- **Voice debrief audio V1 (Polly)** : stack `StravaAIBoost-VoiceDebrief` déployé. Bedrock Haiku 4.5 → script 60-90s → Polly neural Léa (FR) / Joanna (EN) → MP3 S3 privé → presigned URL 1h → AudioPlayer dans Activity detail. Coût ~$0.018-0.020/debrief. Trigger DynamoDB Stream idempotent.
- **Help tooltips Configuration + Preferences** : aide contextuelle sur Strava, modules, athlete profile, Max HR, records, pace zones, content style, demographics. 19 sections.
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

- [ ] **Catégorisation fine des activités "other"** — aujourd'hui le KPI Sessions affiche "10 courses · 6 autre". Détecter les types Strava et afficher en français les catégories dominantes : musculation (`WeightTraining` / `Workout` / `Crossfit`), vélo (`Ride` / `VirtualRide` / `EBikeRide`), natation (`Swim`), randonnée (`Hike`), marche (`Walk`), yoga (`Yoga`). Affichage : "10 courses · 6 musculation" ou "10 courses · 4 musculation · 2 vélo" selon la répartition. Backend `dashboard_api.py` doit retourner la répartition par type plutôt qu'un compteur agrégé. Strings affichées toujours en FR/EN via i18n.
- [ ] **Recovery state widget Coach Now** — exploiter pleinement les données Intervals.icu déjà fetchées : KPIs HRV (delta vs baseline 7j), VO2max (trend), Resting HR (delta), Sleep (durée + qualité), Form/TSB explicite. Détection d'anomalies (HRV chute -20%, decoupling > 10%). Aujourd'hui ces données sont en DB mais peu visibles côté UI.
- [ ] **Help tooltip systématique sur chaque KPI** — petit `(?)` en haut à droite de chaque card KPI (Dashboard, Coach Now, Quality, Recovery, partout). Au hover/tap : popover Radix avec définition courte (HRV, VO2max, Resting HR, Sleep, Form/TSB, Ramp rate, EF pace, Edit rate, Confidence, Similarity, etc.). i18n FR/EN. Pattern réutilisable via une nouvelle prop `info?: string` sur le composant `KPI`.
- [ ] **Voice debrief audio post-séance V1 (Polly)** — Bedrock génère un script court (200 mots) à partir du `coach_feedback`, Polly TTS neural voice Léa (FR) / Joanna (EN), MP3 stocké S3 avec URL signée, bouton "Listen to debrief" dans Activity detail. Personne ne le fait en mainstream (cf [analyse](./COMPETITIVE-ANALYSIS.md)). V2 future = Nova Sonic conversationnel temps réel.
- [ ] **Map polyline sur Activity detail** — afficher le tracé Strava (Mapbox static ou Leaflet, polyline dispo via Strava API). Aujourd'hui placeholder.
- [ ] **Empty states illustrés** : remplacer les icônes lucide par des illustrations SVG sur les pages "vides"
- [ ] **Map / split par km sur Activity detail** : breakdown allure / FC par kilomètre via streams Strava
- [ ] **Notifications in-app** : "Ton activité X a été enrichie" (toast persistant à la connexion)

### Moyen terme (1-2 mois)

- [ ] **Race time prediction + plan adaptatif minimum viable** — Strava vient de bundler Runna (-60%) précisément pour combler ce trou (cf [analyse](./COMPETITIVE-ANALYSIS.md)). Devient un standard que les users vont attendre.
- [ ] **Recap audio hebdomadaire type podcast** (idée originale, dimanche matin, 1-3 min, Bedrock + Polly + EventBridge cron). Sticky habit, viralité, différenciation.
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
