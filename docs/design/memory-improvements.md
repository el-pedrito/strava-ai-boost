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

1. ✅ **Stratégie EPISODIC + reflection** (fait 2026-07-17) — stratégie
   `CoachingEpisodes` ajoutée (ACTIVE) : épisodes par session + **réflexions
   au niveau actor** (pas cross-actor — avertissement privacy de la doc AWS).
   Namespaces sur la convention unifiée → les 3 lecteurs prefix-based
   (coach, recap, tool chat) verront épisodes et réflexions **sans changement
   de code**. Note : n'extrait que les **nouveaux** events ; les records
   SEMANTIC existants restent la source principale au début.
2. ✅ **coach_chat lit les observations** (fait 2026-07-17) — 5e tool
   `get_coach_observations(topic)` : prefix `/strategies/` + filtre par
   utilisateur (le rôle SDK du runtime n'a que `RetrieveMemoryRecords`, pas
   `GetMemory` → pas de découverte de stratégie côté chat, le pattern prefix
   suffit). topK 8 → max 5 après filtre utilisateur. Vérifié live : 5
   observations pertinentes par topic. Le chat a maintenant la continuité
   avec le pipeline feedback (« d'habitude », « la dernière fois »).
3. **metadataFilters à l'extraction** — test de propagation **lancé le
   2026-07-17** : event taggé (`metadata={activity_type, test_marker}`) créé
   sous l'actor `metadata_test` (event `0000001784281833937#afb42380`,
   session `metadata-propagation-test`). L'extraction étant asynchrone
   (déclenchée à l'idle de session), vérifier plus tard si le record extrait
   porte le metadata custom :
   `list_memory_records(namespace='/strategies/')` filtré sur
   `/actors/metadata_test/` → champ `metadata`. Si oui → investir dans le
   tagging par sport ; sinon → clore la piste. Nettoyage : supprimer les
   records/events de l'actor de test après verdict.
4. ✅ **Hygiène des events — audité, aucune action** (2026-07-17) :
   `eventExpiryDuration=365j`, 19 sessions / ~43 events pour l'actor
   principal — volume trivial, l'expiry par défaut suffit largement.
   Les records orphelins de l'actor legacy `default_user` (19 préférences
   pré-multi-user, mai 2026) ont été **migrés vers l'actor réel** le
   2026-07-17 (ils contenaient des préférences apprises uniques : suppression
   des tournures grandiloquentes, style des fun facts, abréviation des noms
   d'exercices) puis supprimés — copy-then-delete vérifié, 19/19.
5. ✅ **Unifier `/strategy/` vs `/strategies/`** (fait 2026-07-17) — pas
   besoin de recréer la stratégie : `modifyMemoryStrategies` change les
   `namespaceTemplates` **in-place** (ID préservé). Exécuté :
   `StravaContentPreferences` → `/strategies/{memoryStrategyId}/actors/{actorId}/`
   + **migration des 28 records existants** (copy-then-delete via
   `batch_create_memory_records`, vérif `failedRecords` in-band avant
   suppression, idempotent par `requestIdentifier`). Vérifié : 0 record
   restant en legacy, 28 dans le nouveau namespace (9 user réel + 19 actor
   legacy `default_user`), lecteurs OK (5 prefs récupérées, coach 4 obs,
   smoke régression 0 fail). Piège rencontré : `list_memory_records` juste
   après migration montre des comptes partiels (**cohérence éventuelle** de
   l'index) — recompter avec pagination complète avant de conclure.
   Lecteurs alignés sur un pattern unique « prefix `/strategies/` + filtre
   `/actors/{uid}/` » (coach simplifié, content_agent garde le namespace
   legacy en 2e essai pour les forks non migrés). Toute la config est
   rejouable via `scripts/configure_memory_strategy.py` (idempotent).
