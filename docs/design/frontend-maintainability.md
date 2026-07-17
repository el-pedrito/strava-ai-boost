# Design spec — Chantier frontend : maintenabilité & cohérence UI

**Statut :** 🗺️ **roadmap — non démarré.** Aucun dev/build engagé. Ce doc cadre
les chantiers issus de la review UI/UX du 2026-07-17 pour décision ultérieure.
**Périmètre :** design system custom React + Tailwind v4 (`frontend/src/`).
**Méthode :** review statique du code → constat chiffré → approche proposée par item.

> Contexte : deux quick-wins de la même review ont déjà été livrés le 2026-07-17
> (hors de cette spec) : suppression du CSS legacy mort (`styles/global.css`) et
> correction de la dérive doc « Cloudscape » dans `AGENTS.md`. Les 3 items
> ci-dessous sont des chantiers plus lourds, volontairement mis en attente.

---

## Résumé exécutif

| # | Item | Nature | Effort | Risque | Priorité |
|---|------|--------|--------|--------|----------|
| 3 | Découpage des pages monolithiques | Maintenabilité | M–L | Moyen (régression visuelle/tests) | P2 |
| 4 | Extraction d'un composant `UserMenu` partagé | DRY / cohérence | S | Faible | P2 |
| 5 | Micro-bug suffixe `%` du delta `KPI` | Correctif visuel | XS | Faible | P3 |

Ordre conseillé si on démarre : **5 → 4 → 3** (du moins risqué au plus lourd).

---

## Item 3 — Pages monolithiques

### Constat (tailles mesurées le 2026-07-17)

| Fichier | Taille | Commentaire |
|---------|--------|-------------|
| `pages/Coach/CoachPage.tsx` | ~66 KB | de loin le plus gros — plusieurs onglets/sections dans un seul fichier |
| `pages/Preferences/PreferencesPage.tsx` | ~43 KB | profil athlète, PRs, zones, programme muscu, préférences contenu |
| `pages/Dashboard/DashboardPage.tsx` | ~31 KB | KPIs + liste activités + états santé |
| `pages/Quality/ContentQualityPage.tsx` | ~21 KB | stats qualité + tableau activités |
| `pages/Activity/ActivityDetailPage.tsx` | ~20 KB | détail activité |

Ces tailles nuisent à la lisibilité, aux revues, et rendent le diff bruité. Ce
n'est **pas** un problème visuel pour l'utilisateur — c'est un chantier de
maintenabilité et de vélocité de dev.

### Approche proposée

- Découper chaque grosse page en **sous-composants co-localisés** dans le dossier
  de la page (ex. `pages/Coach/components/`), un composant par section/onglet.
- Extraire la logique de données (fetch, transforms comme `transformActivities`)
  dans des **hooks** (`pages/<X>/use<X>Data.ts`) pour séparer données et rendu.
- Conserver le composant `*Page.tsx` comme **orchestrateur mince** (layout + wiring).
- Réutiliser les primitives existantes (`ui/`) — ne pas réintroduire de styles ad hoc.

### Cible indicative

- Aucun fichier de page > ~15 KB après découpage.
- Priorité au plus gros gain : **`CoachPage.tsx` en premier**.

### Points d'attention

- Faire le découpage **à iso-comportement** (pas de changement visuel/fonctionnel).
- Ajouter/adapter les tests de rendu (Vitest + Testing Library) au fil du découpage.
- PRs par page pour garder des diffs revusables.

---

## Item 4 — Composant `UserMenu` partagé

### Constat

Le menu utilisateur (avatar/initiale, email, action « Sign Out ») est **dupliqué**
entre `components/layout/Sidebar.tsx` (bas de sidebar) et
`components/layout/Topbar.tsx` (variante mobile). Même logique répétée :

- dérivation `userEmail = user?.getUsername()` et `userInitial`
- `DropdownMenu` Radix avec en-tête email + item `signOut`

Toute évolution (ajout d'un lien « Compte », changement d'avatar) doit être faite
à deux endroits → risque d'incohérence.

### Approche proposée

- Créer `components/layout/UserMenu.tsx` encapsulant : dérivation email/initiale,
  `DropdownMenu` Radix, items (Sign Out + extensions futures).
- Props de placement pour couvrir les deux usages : `variant="sidebar" | "topbar"`,
  `collapsed?`, `side`/`align` du contenu.
- `Sidebar` et `Topbar` consomment `UserMenu` — suppression du code dupliqué.

### Bénéfice / risque

- Bénéfice : une seule source de vérité, cohérence garantie, ajout de liens trivial.
- Risque faible (composant présentational) — couvrir par un test de rendu + interaction `signOut`.

---

## Item 5 — Micro-bug : suffixe `%` du delta `KPI`

### Constat

Dans `ui/KPI.tsx`, le rendu du delta :

```tsx
{delta.value > 0 ? '+' : ''}
{delta.value}
{typeof delta.value === 'number' && !Number.isInteger(delta.value) ? '' : '%'}
```

La logique n'ajoute `%` **que si la valeur est entière**. Un delta **décimal**
(ex. `2.5`) s'affiche donc **sans aucune unité** (`+2.5` au lieu de `+2.5%` ou
`+2.5 pts`). Comportement quasi certainement non voulu.

### Décision à trancher (avant dev)

Clarifier la sémantique attendue du delta selon les appels réels :
- **Cas A** — le delta est toujours un **pourcentage** → afficher `%` quel que soit
  entier/décimal. Correctif : retirer la condition, toujours suffixer `%`.
- **Cas B** — le delta peut être une valeur absolue (points, unités) → introduire
  une prop explicite `deltaUnit?: '%' | 'pts' | string` plutôt qu'une heuristique
  sur `Number.isInteger`.

Recommandation : **Cas B** (prop explicite `deltaUnit`, défaut `'%'`) pour lever
l'ambiguïté durablement. Auditer les usages de `<KPI delta=...>` avant de choisir.

### Effort / risque

- XS. Correctif localisé à `KPI.tsx` (+ éventuelle prop). Ajouter un test couvrant
  delta entier **et** décimal.

---

## Ce que ce chantier ne fait PAS

- Aucun redesign visuel ni changement de tokens/thème.
- Aucun ajout de dépendance.
- Aucun dev/build engagé tant que cette spec n'est pas priorisée dans la ROADMAP.
