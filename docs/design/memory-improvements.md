# Spec — Améliorations AgentCore Memory (A4)

> Statut : audit fait le 2026-07-17 (live, compte réel) — implémentation V1 dans la foulée.
> Contexte : ROADMAP § Chantier agentic, item A4. L'objectif initial était la
> « searchQuery dynamique » ; l'audit a révélé que la boucle mémoire est en
> réalité **cassée** à plusieurs endroits — la V1 corrige d'abord ça.

## Audit (vérifié en live sur `content_gen_mem`)

### Comment la mémoire fonctionne réellement

- Les `create_event` (coach observations, feedback diffs, échanges chat)
  alimentent la **short-term memory** ; les **stratégies** extraient ensuite
  des records long-terme dans **leurs** namespaces :
  - SEMANTIC `ComprehensiveLearning` → `/strategies/ComprehensiveLearning-{suffix}/actors/{actorId}/` (✅ 3+ records vérifiés)
  - CUSTOM `StravaContentPreferences` → `/strategy/StravaContentPreferences/actors/{actorId}/` (✅ 3+ records vérifiés — note : `/strategy/` singulier, namespace configuré à la main)
- **Aucune stratégie n'écrit dans `coaching_observations/{user_id}`** — ce
  namespace n'a jamais existé côté records.
- `RetrieveMemoryRecords` : `namespace` est un **prefix match** ;
  `searchCriteria.memoryStrategyId` filtre par stratégie ; `namespacePath`
  (glob type `/actors/{id}`) ne matche pas nos layouts (testé → 0 records).
  La forme robuste et isolée par utilisateur : `namespace="/strategies/"` +
  `memoryStrategyId` + le suffixe actor dans le namespace complet.

### Les 4 lecteurs, état des lieux

| Lecteur | Namespace lu | État |
|---|---|---|
| `coach_agent.retrieve_coaching_observations` | `coaching_observations/{uid}` | ❌ **vide depuis toujours** — le coach ne relit jamais ses observations |
| `weekly_audio_recap` | `user_id` brut | ❌ **triple panne** : namespace invalide + ancienne forme d'API (`semanticSearch`/`memoryRecords` → ValidationException) + **le rôle IAM n'a aucune action bedrock-agentcore** |
| `content_agent.retrieve_user_preferences` | `/strategy/StravaContentPreferences/actors/{uid}/` puis `/actors/{uid}/` | ✅ fonctionne (1er namespace a des records) |
| `coach_chat` | — (ne lit pas les records ; tools + historique frontend) | ➖ par design, piste d'amélioration |

### searchQuery statique (l'objectif A4 initial)

`"recent coaching observations and athlete patterns"` pour toutes les séances.
Test live : une query orientée muscu (« musculation force progression
charges... ») remonte des records **différents et pertinents** (progression
développé couché 4x8@90kg) vs la query générique (records plan Campus). Le
gain de la query dynamique est réel et vérifié.

## V1 — implémentée (2026-07-17)

1. **Fix lecture coach** (`coach_agent.py`) :
   - namespace `"/strategies/"` (prefix) + `memoryStrategyId` **découvert au
     démarrage** via `get_memory` (le rôle runtime a `GetMemory` — vérifié) et
     caché au module ; fallback prefix-seul si la découverte échoue. Pas d'ID
     de stratégie hardcodé (compte-spécifique).
   - **searchQuery dynamique** : construite depuis le type d'activité +
     classification (course easy/intervals/long/tempo, muscu, vélo...) — mots
     clés FR/EN alignés sur le contenu réel des records.
   - Isolation utilisateur conservée : le namespace complet contient
     `/actors/{uid}/` → on passe le prefix stratégie + on filtre côté
     recherche avec le namespace complet par stratégie découverte.
2. **Fix weekly recap** (`weekly_audio_recap.py`) : même mécanique de lecture
   (forme d'API actuelle, `memoryRecordSummaries`) + query orientée « tendances
   hebdo ». **IAM** : ajout `RetrieveMemoryRecords`/`GetMemory` scoped au
   memory ARN dans `voice_debrief_stack.py` (le rôle n'avait rien).
3. **Tests** : unit sur la construction de query dynamique + le fallback ;
   vérification live post-déploiement (records non vides pour le coach).

Non fait en V1 (assumé) : suppression du namespace legacy dans coach_chat
(commentaires seulement, aucun call), migration EPISODIC (voir pistes).

## Pistes suivantes (tracées en ROADMAP)

> Avancement 2026-07-17 après-midi (V2) : pistes 2 et 4 traitées, spike fait
> sur la 3.

1. **Stratégie EPISODIC + reflection** sur les observations coach — confirmé
   dispo dans l'API (`episodicMemoryStrategy` + `reflectionConfiguration`).
   Consolide (réflexions périodiques) au lieu d'accumuler des records
   par-séance. À ~5 activités/semaine, urgence faible ; à faire quand le
   volume de records gêne la pertinence du topK.
2. ✅ **coach_chat lit les observations** (fait 2026-07-17) — 5e tool
   `get_coach_observations(topic)` : prefix `/strategies/` + filtre par
   utilisateur (le rôle SDK du runtime n'a que `RetrieveMemoryRecords`, pas
   `GetMemory` → pas de découverte de stratégie côté chat, le pattern prefix
   suffit). topK 8 → max 5 après filtre utilisateur. Vérifié live : 5
   observations pertinentes par topic. Le chat a maintenant la continuité
   avec le pipeline feedback (« d'habitude », « la dernière fois »).
3. **metadataFilters à l'extraction** — spike fait : `CreateEvent` accepte
   bien `metadata` (schéma botocore), mais les records extraits observés ne
   portent que du metadata système (`x-amz-agentcore-memory-recordType`) —
   la **propagation event→record n'est pas démontrée** (extraction
   asynchrone, vérification coûteuse). À revalider par un test dédié avant
   d'investir.
4. ✅ **Hygiène des events — audité, aucune action** (2026-07-17) :
   `eventExpiryDuration=365j`, 19 sessions / ~43 events pour l'actor
   principal — volume trivial, l'expiry par défaut suffit largement.
   Trouvé au passage : des records d'avril sous l'actor legacy
   `default_user` (pré-multi-user), orphelins inoffensifs (jamais matchés
   par les lectures filtrées par user_id réel).
5. **Unifier `/strategy/` vs `/strategies/`** — le namespace custom de
   `StravaContentPreferences` (singulier, configuré manuellement) diverge de
   la convention du service ; fonctionne mais piège tout futur lecteur.
   Migration = recréer la stratégie (records à re-extraire) → coupler avec la
   piste 1.
