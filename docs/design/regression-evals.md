# Spec — Évals de régression des prompts (A3)

> Statut : **spec validée à challenger avec l'utilisateur avant implémentation**.
> Date : 2026-07-16. Contexte : ROADMAP § Chantier agentic, item A3.

## Problème

Les règles de qualité du contenu généré (anti-clichés IA, style Pierre,
`strava_block` orienté tendances, chiffres hebdo réels) vivent dans
`src/agents/embedded_prompts.py` sous forme de prose. Tout changement de prompt
peut les casser **silencieusement** : aucun signal avant de voir passer une
mauvaise description sur Strava. En mono-user (~5 activités/semaine), l'éval
« online » du trafic prod a peu de valeur ; la valeur est dans la **régression
on-demand** : rejouer un jeu de référence à chaque changement de prompt.

## Ce qui est déjà couvert (ne pas dupliquer)

| Règle | Enforcement | Où |
|---|---|---|
| Em/en dash `—` `–` | **Code** (strip post-génération) | `content_generator.py` l.388, `coach_generator.py` l.194 |
| Longueur max, emojis | **Code** (`enforce_preferences`) | `content_generator.py` |
| Clichés bannis (13 expressions) | **Prompt uniquement** ⚠️ | `embedded_prompts.py` l.256+ |
| Style Pierre / orienté tendances | **Prompt uniquement** ⚠️ | `embedded_prompts.py` |

→ Le risque réel de régression est sur les deux dernières lignes : **rien ne
les vérifie**, ni en test ni en prod.

## Décisions de conception (issues du challenge du plan initial)

1. **Pas de mode « offline gratuit » prétendument équivalent.** Sans LLM on ne
   teste que le post-traitement (déjà unit-testé). La valeur du harnais est
   dans les **runs live payants** (~0,15-0,25 $/run pour ~10 fixtures),
   déclenchés manuellement quand `embedded_prompts.py` change — pas en CI.
2. **Signal de tendance, pas gate dur.** Température > 0 → sorties
   non-déterministes. Le rapport compare au baseline et alerte ; il ne bloque
   pas un commit. Un échec ponctuel sur un critère LLM-dépendant se relance.
   Les critères déterministes (cliché présent = fail) restent binaires.
3. **Invocation du runtime déployé `content_gen`** (décision utilisateur
   2026-07-16, remplace l'option « Bedrock direct » du plan initial). On teste
   ainsi la chaîne réellement déployée (prompt + modèle + config runtime +
   guardrail input). La crainte de pollution memory est levée après lecture du
   code : l'agent tourne avec `hooks=[]` (**aucune écriture** memory pendant la
   génération — writes uniquement via le feedback analyzer) et les lectures
   sont namespacées par `user_id` → le harnais invoque avec un
   `user_id="regression_eval"` dédié (lectures vides, isolation totale).
   Contreparties assumées : nécessite le runtime déployé + credentials AWS,
   et un changement de prompt doit être **déployé** avant d'être évaluable.
4. **Pas de refactor du prompt pour partager la liste de clichés.**
   Reconstruire le prompt depuis une constante modifierait son rendu — le
   genre exact de changement qu'on veut détecter, introduit par l'outil censé
   le détecter. À la place : constante `BANNED_CLICHES` dans le harnais + un
   **test de synchronisation** (chaque entrée doit apparaître textuellement
   dans le prompt source ; si on retire un cliché du prompt, le test casse et
   force la mise à jour des deux côtés).
5. **Fixtures anonymisées/synthétiques.** Le repo devient public : pas
   d'export brut de vraies activités (GPS, lieux, données perso). Fixtures
   construites à la main sur le gabarit des payloads réels (mêmes clés que
   `retrieve_activity_data_from_dynamodb`), valeurs synthétiques plausibles.
6. **Périmètre V1 : `content_gen` uniquement.** Le coach demande ~4 semaines
   de contexte par fixture (lourd à synthétiser). Le bug historique « chiffres
   hebdo hallucinés » est déjà mitigé côté code (`format_weekly_breakdown`,
   tally serveur). Coach = V2 si le besoin se confirme.
7. **AgentCore Evaluations managé = V2 (vitrine OSS), pas V1.** Le service
   existe (vérifié doc AWS : custom evaluators LLM-as-a-Judge, on-demand,
   intégration Strands/OTel, CDK `aws_bedrockagentcore`). Mais pour le besoin
   mono-user, un juge LLM sur « voix de Pierre » ajoute du coût et du bruit
   (drift du modèle juge) pour un gain marginal vs les checks déterministes.
   On garde l'architecture du harnais compatible (fixtures + critères →
   transposables en dataset + custom evaluators managés plus tard).

## V1 — Harnais local on-demand

### Composants

```
tests/regression/
├── fixtures/               # ~8-10 activités synthétiques (JSON)
│   ├── run_easy.json       # footing cool
│   ├── run_intervals.json  # fractionné avec laps
│   ├── run_long.json       # sortie longue + décrochage cardiaque
│   ├── weight_training.json# muscu avec description exercices
│   ├── ride.json           # vélo
│   ├── manual_indoor.json  # activité manuelle sans laps (cas du crash 07/15)
│   └── ...
├── evaluators.py           # critères déterministes purs (unit-testés)
└── conftest.py
scripts/run_prompt_regression.py   # runner live (Bedrock converse)
docs/design/regression-evals.md    # cette spec
.regression/baseline.json          # dernier rapport accepté (committé)
```

### Critères V1 (déterministes, code pur)

| ID | Critère | Sévérité |
|---|---|---|
| `no_banned_cliche` | Aucune des 13 expressions bannies (casse/accents normalisés) | fail |
| `no_forbidden_dashes` | Pas de `—`/`–` **dans la sortie brute LLM** (le strip code est un filet, le prompt doit déjà l'éviter) | warn |
| `no_spaced_hyphen` | Pas de ` - ` séparateur de clauses | warn |
| `length_within_pref` | Longueur ≤ cible du profil fixture | fail |
| `emoji_policy` | Nb d'emojis conforme à la préférence fixture | warn |
| `json_parseable` | Sortie parseable par `_parse_agent_response` | fail |
| `title_not_generic` | Titre ≠ patterns génériques (« Course à pied », « Morning Run ») | warn |
| `language_is_french` | Heuristique simple (stopwords FR) sur les fixtures FR | fail |

`fail` = régression bloquante à investiguer ; `warn` = signal, toléré
ponctuellement (non-déterminisme).

### Runner

`./venv/bin/python scripts/run_prompt_regression.py [--fixtures run_easy,...] [--model <id>]`

1. Pour chaque fixture : construire l'`agent_input` (même forme que
   `content_generator.py`, `user_id="regression_eval"`), invoquer le runtime
   déployé via `bedrock-agentcore.invoke_agent_runtime`
   (`CONTENT_GENERATION_AGENT_ARN` découvert via l'env généré par
   `configure_agentcore_integration.sh` ou passé en `--agent-arn`), parser via
   `_process_agent_response`/`_parse_agent_response` (fonctions de prod).
2. Évaluer tous les critères → rapport JSON + tableau console.
3. Comparer au `baseline.json` committé : nouveaux `fail` → exit 1 ;
   `--update-baseline` pour accepter un nouvel état après revue humaine.
4. Coût affiché en fin de run (tokens in/out). Ordre de grandeur attendu :
   ~10 fixtures × 1 appel Sonnet ≈ 0,15-0,25 $.

### Tests unitaires (gratuits, en CI)

- `evaluators.py` testé exhaustivement (chaque critère, cas limites).
- **Test de synchronisation** `BANNED_CLICHES` ↔ texte de
  `embedded_prompts.py` (voir décision 4).
- Le rendu de prompt sur chaque fixture ne lève pas et contient les sections
  attendues (smoke test du gabarit, sans LLM).

### Workflow d'usage

1. Modifier `embedded_prompts.py` (ou changer de modèle).
2. `python scripts/run_prompt_regression.py` (~1 min, ~0,20 $).
3. Comparer au baseline ; si les `fail` sont propres et les `warn` compris,
   `--update-baseline`, committer rapport + changement de prompt ensemble.

## V2 — pistes (non engagées)

- **Coach feedback** : fixtures avec contexte 4 semaines synthétique ;
  critères « orienté tendances vs recap » (nécessite juge LLM).
- **AgentCore Evaluations managé** : transposer fixtures → dataset,
  critères sémantiques → custom evaluators (LLM-as-a-Judge), on-demand via
  SDK/CDK. Intérêt principal : vitrine du sample OSS + blog post.
- **CI hebdo opt-in** : GitHub Action manuelle (workflow_dispatch) avec
  secret AWS, jamais sur PR publique.

## Risques & limites assumées

- **Dépend du déploiement** : le harnais évalue le runtime déployé — un
  changement de prompt doit passer par `deploy_agentcore_agents.sh` avant
  d'être évaluable. En contrepartie on teste la vraie chaîne de prod.
- **Non-déterminisme** : un `warn` peut apparaître/disparaître entre runs.
  Les `fail` déterministes sur sortie donnée restent fiables.
- **Coût** : volontairement on-demand manuel ; pas de scheduling.
- **Fixtures synthétiques** : moins riches que la prod (pas d'Intervals.icu
  complet, pas d'Enduraw). Extensible fixture par fixture si besoin.
