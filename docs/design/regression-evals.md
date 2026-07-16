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

## V2 — AgentCore Evaluations managé (détaillé)

> Statut : **spec documentaire, non engagée**. Basée sur la doc AWS vérifiée le
> 2026-07-16 (voir références en fin de section). Objectif principal : vitrine
> OSS du repo (pattern « regression evals managées sur un agent Strands
> déployé ») + blog post. La valeur mono-user reste marginale vs le harnais V1.

### Ce que le service fait (vérifié doc AWS)

- **Principe** : les traces OTel de l'agent (spans + events) sont converties en
  format unifié puis notées par des juges LLM (built-in ou custom). Frameworks
  supportés : **Strands** (scope `strands.telemetry.tracer`), LangGraph
  (OTel/OpenInference). Les agents peuvent être hébergés sur AgentCore Runtime
  **ou ailleurs** — mais dans tous les cas il faut des **traces**, pas un
  dataset brut de paires input/output.
- **On-demand evaluation** : on soumet des span/trace IDs existants à l'API
  `Evaluate` (`sessionSpans` = spans + events, les deux requis, sinon
  `ValidationException`). Utile pour investiguer des interactions passées.
- **Dataset evaluation** (⚠️ **public preview**, APIs susceptibles de changer) :
  c'est le mode qui correspond à notre cas régression. Un *dataset runner* du
  SDK (`pip install bedrock-agentcore`) orchestre tout en un appel :
  **invoke l'agent → attend l'ingestion CloudWatch (~180 s, payé une fois) →
  collecte les spans → appelle Evaluate**. Deux runners, même schéma de
  dataset :
  - `OnDemandEvaluationDatasetRunner` — évaluation côté SDK, résultat détaillé
    par scénario/évaluateur immédiatement. **C'est le bon choix ici** (petit
    dataset, itération dev, CI/CD).
  - `BatchEvaluationRunner` — délégué au service, agrégats, gros datasets.
- **Prérequis** (vérifiés) : Python 3.10+, agent avec observabilité AgentCore
  active (✅ `content_gen` l'a déjà, Strands sur Runtime), **Transaction Search
  activé dans CloudWatch** (à vérifier sur le compte), credentials avec
  `bedrock-agentcore`, `bedrock-agentcore-control` et `logs`.

**Réponse à la question clé « faut-il des traces OTel ou peut-on soumettre un
dataset brut ? »** : il faut des traces. L'API Evaluate consomme des
`sessionSpans` ; le dataset runner les produit en invoquant réellement l'agent
et en les relisant depuis CloudWatch (`aws/spans` + le log group du runtime).
On ne peut pas court-circuiter l'agent avec des paires (prompt, réponse)
pré-calculées — sauf à forger soi-même des spans au format attendu, ce qui est
possible en théorie (l'API accepte une liste de spans) mais fragile et hors
pattern documenté.

### Architecture proposée

```
tests/regression/fixtures/*.json  (8 fixtures V1, inchangées)
        │  scripts/build_eval_dataset.py (conversion)
        ▼
dataset.json (schéma AgentCore : scenarios → turns)
        │
        ▼
OnDemandEvaluationDatasetRunner
  ├─ agent_invoker: boto3 bedrock-agentcore.invoke_agent_runtime
  │    → runtime content_gen déployé, payload = agent_input de la fixture,
  │      user_id="regression_eval" (isolation memory, cf. décision V1 #3)
  ├─ CloudWatchAgentSpanCollector
  │    → log groups aws/spans + /aws/bedrock-agentcore/runtimes/<content_gen-id>-DEFAULT
  └─ EvaluatorConfig
       ├─ built-ins : Builtin.GoalSuccessRate, Builtin.InstructionFollowing,
       │              Builtin.Faithfulness
       └─ customs   : VoixAuthentiqueFR, FideliteDonneesActivite,
                      (extension coach) StravaBlockTendances
        │
        ▼
EvaluationResult (par scénario × évaluateur : value, label, explanation,
tokenUsage) → rapport comparé au baseline, même workflow que V1
```

**Mapping fixtures → dataset.** Chaque fixture devient un scénario mono-turn.
Le champ `turns[].input` accepte « String or Object » : on passe l'`agent_input`
complet (dict) tel que construit par la V1, l'invoker le sérialise en payload
pour `invoke_agent_runtime` (exactement l'exemple documenté du agent invoker).
Les critères V1 se transposent en ground truth :

| Fixture (V1) | Dataset (V2) |
|---|---|
| `agent_input` | `turns[0].input` (objet) |
| bloc `eval` (langue, longueur, emojis) | `assertions` en langage naturel (« La réponse est en français », « ≤ 1200 caractères », « 1-2 emojis max ») → `Builtin.GoalSuccessRate` |
| classification attendue | `assertions` (« Le titre/description décrit un footing cool, pas un fractionné ») |
| — | `metadata` : nom de fixture, sévérité |

Les critères **déterministes** V1 (clichés bannis, dashes, parseabilité JSON)
**restent dans `evaluators.py`** côté runner : c'est gratuit, binaire et
fiable ; on ne paie pas un juge LLM pour du regex. Alternative documentée si
on veut tout dans le service : un **custom code-based evaluator** (Lambda
exécutant nos checks déterministes, retour au schéma de réponse du service) —
joli pour la vitrine, redondant fonctionnellement.

### Custom evaluators proposés (LLM-as-a-Judge)

Création via `bedrock-agentcore-control:CreateEvaluator` (config `llmAsAJudge` :
`instructions` avec placeholders, `ratingScale` numérique ou catégorielle,
`modelConfig.bedrockEvaluatorModelConfig`). Placeholders TRACE :
`{context}` (prompt utilisateur + historique), `{assistant_turn}` (réponse à
juger), `{expected_response}` (ground truth). Le service ajoute lui-même le
prompt de standardisation de sortie (reason + score) — **ne pas** inclure de
consigne de format dans l'instruction. Note : les evaluators avec placeholders
ground truth sont interdits en évaluation *online* (OK pour nous, on est
on-demand).

**1. `VoixAuthentiqueFR`** (TRACE, juge `us.anthropic.claude-haiku-4-5`,
temperature 0) — le cœur du sujet : ce que les checks déterministes ne
couvrent pas.

```text
Tu évalues si la description d'activité Strava générée par un assistant sonne
comme un texte écrit par un humain francophone, avec une voix personnelle et
authentique, et non comme un texte générique produit par une IA.

Données de l'activité et consignes fournies à l'assistant :
{context}

Texte généré à évaluer :
{assistant_turn}

Critères (juge chacun, puis donne un verdict global) :
1. Voix personnelle : première personne naturelle, ressenti concret lié aux
   données de la séance, pas de narration désincarnée.
2. Absence de tics d'écriture IA : pas de grandiloquence (« repousser ses
   limites », « chaque foulée », « le corps se réveille », « la machine »),
   pas de listes de qualificatifs creux, pas de conclusion moralisatrice.
3. Français naturel : registre oral maîtrisé, pas de calques de l'anglais,
   pas de tournures pompeuses.
4. Sobriété : le texte parle de CETTE séance avec ses chiffres réels, sans
   emphase artificielle sur une sortie banale.
Un texte factuel et un peu sec est PRÉFÉRABLE à un texte lyrique générique.
```

Échelle catégorielle : `AUTHENTIQUE` / `MITIGE` / `VOIX_IA` (fail si `VOIX_IA`,
warn si `MITIGE` — même sémantique fail/warn que V1).

**2. `FideliteDonneesActivite`** (TRACE, Haiku 4.5, temp 0) — anti-hallucination
de chiffres, complète `Builtin.Faithfulness` avec un focus dur sur les valeurs
numériques.

```text
Tu vérifies que chaque valeur chiffrée du texte généré (distance, allure,
temps, fréquence cardiaque, dénivelé, nombre de répétitions) est traçable aux
données d'activité fournies en entrée, à l'arrondi près.

Données d'entrée : {context}
Texte généré : {assistant_turn}

Relève chaque chiffre du texte, retrouve sa source dans les données, et
signale tout chiffre inventé, déformé ou attribué au mauvais lap. Les calculs
dérivés corrects (allure moyenne déduite de distance/temps) sont acceptés.
```

Échelle numérique : 1.0 (tout traçable) / 0.5 (imprécision mineure) /
0.0 (chiffre inventé) — fail sous 0.5.

**3. `StravaBlockTendances`** (TRACE, Sonnet 4.5 — jugement plus nuancé) —
pour l'extension coach (quand des fixtures coach avec contexte 4 semaines
existeront, cf. piste coach V2) ; posé dès maintenant car c'est LA règle
prompt-only du coach que rien ne vérifie.

```text
Tu évalues le feedback d'un coach de course à pied. La règle : le feedback
doit être orienté TENDANCES et PROGRESSION (comparaison aux semaines
précédentes, évolution de l'efficience, charge, trajectoire vers l'objectif),
et NON un simple récapitulatif de la séance (les données de séance sont déjà
visibles par l'athlète ailleurs).

Contexte fourni au coach (profil, historique 4 semaines, séance) : {context}
Feedback généré : {assistant_turn}

Vérifie : (1) au moins une mise en perspective temporelle explicite appuyée
sur l'historique fourni ; (2) pas de paraphrase des stats de la séance sans
analyse ; (3) les totaux hebdomadaires cités correspondent exactement au
décompte par semaine ISO fourni dans le contexte, sans extrapolation.
```

Échelle catégorielle : `TENDANCES` / `MIXTE` / `RECAP_SEANCE`.

### Built-ins pertinents à activer

| Built-in | Niveau | Usage ici |
|---|---|---|
| `Builtin.GoalSuccessRate` | Session | Consomme les `assertions` par fixture (langue, longueur, type de séance respecté) — le mapping ground truth est automatique via le runner |
| `Builtin.InstructionFollowing` | Trace | Vérifie le respect des consignes explicites du prompt (la `classification_instruction` « ne pas dire fractionné » notamment) |
| `Builtin.Faithfulness` | Trace | Cohérence générale sortie ↔ données d'entrée (filet large, complété par `FideliteDonneesActivite`) |

Non retenus : trajectory matchers (content_gen n'a pas de tool loop),
Harmfulness/Stereotyping (déjà couverts par Guardrails), Conciseness (couvert
par `length_within_pref` déterministe).

### Estimation de coût par run (pricing vérifié, page AgentCore)

Tarifs : built-ins **0,0024 $/1k tokens in + 0,012 $/1k out** (modèle juge
inclus) ; customs **1,50 $/1 000 évaluations + usage modèle facturé à part**
dans le compte.

Hypothèses : 8 fixtures × 1 turn ; contexte injecté au juge ≈ 8-12k tokens
(l'`agent_input` est volumineux : laps, profil, consignes) ; sortie juge
≈ 300 tokens.

| Poste | Calcul | Coût |
|---|---|---|
| Invocation agent (8×, comme V1) | Sonnet 4.5 via runtime | ~0,20 $ |
| Built-ins (3 × 8 = 24 évals) | 24 × 10k in × 0,0024 $/1k + 24 × 0,3k out × 0,012 $/1k | ~0,66 $ |
| Customs (2 × 8 = 16 évals, hors coach) | 16 × 0,0015 $ + Haiku 4.5 (~16 × 10k in) | ~0,20 $ |
| Runtime CPU/mem + CloudWatch | négligeable à cette échelle | ~0,01 $ |
| **Total par run** | | **≈ 1,0-1,3 $** (vs ~0,20 $ V1) |

Soit ~5× le coût V1, dominé par les tokens d'entrée des juges built-in
(le contexte complet de la fixture part dans chaque évaluation). Levier :
réduire les built-ins à `GoalSuccessRate` seul (~0,45 $/run).

### Étapes d'implémentation

1. **Prérequis compte** : vérifier/activer CloudWatch **Transaction Search**
   (requis par les runners) ; l'observabilité GenAI de `content_gen` est déjà
   en place.
2. **Custom evaluators** : configs JSON versionnées dans le repo
   (`tests/regression/evaluators_managed/*.json`), création par script boto3
   `bedrock-agentcore-control.create_evaluator` (idempotent : list → create ou
   update). ⚠️ **CDK non vérifié** : la doc ne montre que CLI/SDK/console pour
   `CreateEvaluator` ; l'existence d'un L1 `aws_bedrockagentcore.CfnEvaluator`
   n'a pas pu être confirmée — partir sur boto3 (cohérent avec les scripts
   AgentCore existants du repo, hors CDK), migrer vers CDK si/quand le L1
   existe.
3. **Conversion fixtures → dataset** : `scripts/build_eval_dataset.py` génère
   `dataset.json` (schéma `scenarios/turns/assertions/metadata`) depuis les 8
   fixtures — les fixtures restent la source de vérité unique (V1 et V2
   partagent le même jeu).
4. **Runner** : `scripts/run_managed_evals.py` — agent invoker boto3 (copie du
   pattern documenté, ARN découvert comme en V1), `CloudWatchAgentSpanCollector`
   sur le log group de `content_gen`, `EvaluationRunConfig` avec les 5
   évaluateurs, `evaluation_delay_seconds=180`. Écrit `results.json`, affiche
   le tableau, compare à un `baseline_managed.json` (même mécanique
   fail/warn/`--update-baseline` que V1).
5. **Vitrine** : section README + éventuel workflow GitHub `workflow_dispatch`
   (jamais sur PR publique, secret AWS requis — cf. piste CI V1).

### Limites & risques

- **Public preview** : dataset evaluation (runners, schéma) peut changer avant
  GA. Épingler la version du SDK `bedrock-agentcore` ; prévoir de revisiter à
  la GA.
- **Drift du juge** : les built-ins utilisent des modèles/prompts gérés par
  AWS, modifiables sans préavis (« we will continue improving ») — un score
  peut bouger sans changement de notre prompt. Les customs épinglent le modèle
  juge, mais un juge LLM sur « voix authentique » reste subjectif : traiter
  les scores custom comme **signal de tendance** (sémantique warn), jamais
  comme gate binaire. Les vrais gates restent les checks déterministes V1.
- **Coût** : ~1 $/run vs ~0,20 $ en V1, pour un gain de détection réel mais
  modeste en mono-user. Le ROI est la vitrine, pas la détection.
- **Latence** : +180 s d'attente d'ingestion CloudWatch par run (~4-5 min
  total vs ~1 min en V1).
- **Couplage CloudWatch** : le runner lit `aws/spans` — toute rétention/config
  de logs agressive côté compte casse la collecte ; Transaction Search est un
  prérequis supplémentaire à documenter pour les forks du repo.
- **Pas de bypass sans agent** : impossible d'évaluer un prompt non déployé
  (même contrainte que V1 décision #3, aggravée : il faut runtime + télémétrie).
- **Point non vérifié** : le passage d'un `agent_input` volumineux (dict
  complet avec laps) comme `turns[].input` est conforme au type documenté
  (« String or Object ») mais les exemples doc ne montrent que des prompts
  courts — à valider par un spike avant d'engager l'implémentation.

### Références (doc AWS vérifiée 2026-07-16)

- Vue d'ensemble : `docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html`
- Dataset evaluation + runners : `.../dataset-evaluations.html`, `.../dataset-evaluations-schema.html`, `.../dataset-evaluations-on-demand.html`
- Custom evaluators : `.../custom-evaluators.html`, `.../create-evaluator.html`
- Built-ins + prompts des juges : `.../built-in-evaluators-overview.html`, `.../prompt-templates-builtin.html`
- On-demand / input spans : `.../on-demand-evaluations.html`, `.../understanding-input-spans.html`
- Pricing : `aws.amazon.com/bedrock/agentcore/pricing/` (section Evaluations)

## Risques & limites assumées

- **Dépend du déploiement** : le harnais évalue le runtime déployé — un
  changement de prompt doit passer par `deploy_agentcore_agents.sh` avant
  d'être évaluable. En contrepartie on teste la vraie chaîne de prod.
- **Non-déterminisme** : un `warn` peut apparaître/disparaître entre runs.
  Les `fail` déterministes sur sortie donnée restent fiables.
- **Coût** : volontairement on-demand manuel ; pas de scheduling.
- **Fixtures synthétiques** : moins riches que la prod (pas d'Intervals.icu
  complet, pas d'Enduraw). Extensible fixture par fixture si besoin.
