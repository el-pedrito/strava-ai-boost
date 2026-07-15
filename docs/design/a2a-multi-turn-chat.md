# A2a — Multi-tour sur le chat coach streamé

> Plan d'implémentation validé le 2026-07-15. Étude doc-first (doc AWS Converse,
> skill bedrock, MCP AgentCore Memory) + vérification code + challenge multi-agents
> (design-critic : GO-AVEC-CORRECTIONS, code-verifier : 1 bloquant corrigé).
> Réf. roadmap : [ROADMAP.md](../ROADMAP.md) § Chantier agentic, item A2a.

## Problème

Le chat coach streamé (`coach_stream/app.py`) traite chaque question isolément :
`converse_stream` reçoit un unique message user. Les follow-ups («&nbsp;et pour un 10K ?&nbsp;»)
perdent tout contexte. Le chemin buffered (`coach_ask_api.py`) est déjà multi-tour
(session AgentCore Runtime + `history` pour le fallback Bedrock) — seul le chemin
streaming, pourtant nominal, a ce trou.

## Décision clé : historique fourni par le client, pas par AgentCore Memory

La roadmap proposait `get_last_k_turns` (AgentCore Memory). **Rejeté après étude** :

- `write_chat_to_memory` (`shared/coach_context.py` l.388-411) **filtre volontairement**
  les écritures : question < 20 chars ou réponse < 100 chars → non écrites ; réponse
  tronquée à 500 chars. L'historique en Memory est donc **lossy** — il manque
  précisément les tours courts dont le multi-tour a besoin. Retirer ces filtres
  polluerait l'extraction LTM (leur raison d'être).
- Le frontend (`CoachChat.tsx` l.95-98) construit déjà `history` (10 derniers
  messages) — source complète et fidèle.
- Lecture Memory = +1 appel réseau avant le premier token, + IAM `ListEvents`,
  pour un résultat inférieur.

`write_chat_to_memory` reste inchangé : il alimente la LTM (observations), pas le
fil de conversation. Le chemin streaming l'appelle déjà après `TEXT_MESSAGE_END`.

## Bloquant trouvé au challenge : le frontend n'envoie PAS `history` au stream

`CoachChat.tsx` n'envoie `history` **qu'au chemin buffered**. `coachStream.ts`
(interface `CoachStreamRequest` l.33-37) ne transporte que
`question`/`user_id`/`session_id`. → ~3 lignes de frontend sont indispensables.

## Plan d'implémentation

| # | Changement | Fichier |
|---|-----------|---------|
| 1 | Helper `build_converse_messages(history, current_question)` — voir contrat ci-dessous | `lambda_functions/shared/coach_context.py` |
| 2 | Consommer `body.get("history", [])` ; contexte athlète déplacé dans le paramètre `system` de Converse ; `messages[]` multi-tour via le helper | `lambda_functions/coach_stream/app.py` |
| 3 | Refactorer `_fallback_bedrock` sur le même helper (aujourd'hui : aucune validation, KeyError possible, alternance non garantie — bug latent) | `lambda_functions/api/coach_ask_api.py` |
| 4 | Ajouter `history` à `CoachStreamRequest` + à l'appel `streamCoachAnswer` | `frontend/src/api/coachStream.ts`, `frontend/src/pages/Coach/CoachChat.tsx` |
| 5 | Tests unitaires du helper + non-régression des 3 tests AG-UI existants | `tests/unit/test_coach_stream.py` (+ nouveau fichier ou section) |

**Zéro changement CDK / IAM / session_id** (le `session_id` existant reste utilisé
par le chemin buffered/Runtime).

## Contrat du helper `build_converse_messages`

Contraintes API Converse (Claude) : premier message = `user`, rôles strictement alternés.

- **Whitelist stricte des rôles** `{user, assistant}` — tout autre rôle (dont
  `system` smuggglé par le client) est ignoré
- Cap : **10 messages max** (les plus récents) ; troncature **asymétrique**
  500 chars/user, 2500 chars/assistant (les réponses coach dépassent couramment
  1000 chars ; les mutiler crée des auto-contradictions)
- **Drop du leading assistant**, **merge des rôles consécutifs**
- Tout historique invalide (null, non-liste, entrées malformées) → **dégradation
  silencieuse en single-turn**, jamais d'erreur 400
- Fonction pure, sans I/O → tests unitaires exhaustifs (alternance, merge, drop,
  troncature, rôles invalides, historique vide)

## Sécurité

- Historique client = entrée non fiable : whitelist rôles + caps côté serveur
- Contexte athlète dans `system` (données serveur) séparé des `messages`
  (données client) — meilleure isolation anti-injection
- Risque résiduel accepté (mono-user, SigV4) : cohérent avec T4 du
  [threat model](THREAT-MODEL.md)

## Hors périmètre (assumé)

- Stratégie EPISODIC / searchQuery dynamique → A4
- Tools Strands / Strava MCP → A1
- Refonte streaming via AgentCore Runtime → A2b (seulement si A1 rend
  `converse_stream` direct intenable)
