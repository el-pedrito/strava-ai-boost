# Roadmap

> Strava AI Boost — direction produit après la refonte UI (mai 2026).

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

## Next

### Court terme (1-2 semaines)

- [ ] **Onboarding stepper** Strava → modules → préférences pour les nouveaux users (aujourd'hui Configuration est linéaire et technique)
- [ ] **Charts custom Coach** : annotations narratives ("Ton allure EF baisse de 12s/km à FC stable"), animations de tracé au mount
- [ ] **Activity detail page** : drill-down depuis le Dashboard vers une vue détaillée d'une activité (titre IA, description, modules utilisés, map polyline si dispo)
- [ ] **Empty states illustrés** : remplacer les icônes lucide par des illustrations SVG sur les pages "vides"
- [ ] **Count-up animations** sur les KPIs (Framer Motion déjà installé)

### Moyen terme (1-2 mois)

- [ ] **Landing page publique** (`/`) avant login : value prop, démo, screenshots, FAQ
- [ ] **Pricing page** Free / Pro / Coach avec Stripe Checkout
- [ ] **Stripe customer portal** pour gérer abonnement
- [ ] **Code splitting** : le bundle CoachPage fait 394kb (Recharts), à split par route
- [ ] **PWA** : manifest, service worker, installable mobile
- [ ] **Notifications push** quand une activité est enrichie

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
