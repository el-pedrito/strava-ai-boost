# Roadmap

> Strava AI Boost — direction produit après la refonte UI (mai 2026).
> Pour le contexte concurrentiel et la justification des priorités, voir [COMPETITIVE-ANALYSIS.md](./COMPETITIVE-ANALYSIS.md).

## Done

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

- [ ] **Recovery state widget Coach Now** — exploiter pleinement les données Intervals.icu déjà fetchées : KPIs HRV (delta vs baseline 7j), VO2max (trend), Resting HR (delta), Sleep (durée + qualité), Form/TSB explicite. Détection d'anomalies (HRV chute -20%, decoupling > 10%). Aujourd'hui ces données sont en DB mais peu visibles côté UI.
- [ ] **Help tooltip systématique sur chaque KPI** — petit `(?)` en haut à droite de chaque card KPI (Dashboard, Coach Now, Quality, Recovery, partout). Au hover/tap : popover Radix avec définition courte (HRV, VO2max, Resting HR, Sleep, Form/TSB, Ramp rate, EF pace, Edit rate, Confidence, Similarity, etc.). i18n FR/EN. Pattern réutilisable via une nouvelle prop `info?: string` sur le composant `KPI`.
- [ ] **Voice debrief audio post-séance** — quick win Bedrock + Polly. Personne ne le fait sur le marché aujourd'hui (cf [analyse](./COMPETITIVE-ANALYSIS.md)). 100% AWS-native, différenciation immédiate.
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
