# Allures Campus partout : plages sur la Watch et zones d'allure

Statut : plan validé (revue à deux modèles, 4 tours ; Claude Opus 5.5 READY 9/10, GPT-5.6 Sol
8/10 avec un dernier point intégré ici : la sauvegarde des Préférences). Deux interrupteurs
livrés éteints.

## Décisions de l'athlète (2026-10-17)

1. Campus est la seule source des zones d'allure. Les Préférences les affichent en lecture seule.
2. Chaque étape suit son `pace.kind` Campus : `range` (EF, échauffement et retour au calme EF)
   -> plage ; `single-value` (intervalles : Tempo, Seuil, Semi, course) -> valeur exacte ;
   `abstract` (Lent, récup) -> rien.
3. Le contrôle du match par `racingNote` est abandonné (Campus est validé après notre traitement).

## Données Campus (lues par `probe_schema`, 2026-10-17)

- `exercise.pace` = {name, value (s/km entier), kind, zoneKind, abstract, slug}.
- `week.estimatedPaces` = 21 entrées {slug, value (float), dvalue (float), abstract, competitive}.
- Plage supposée = value ± dvalue (EF 348.8 ± 13.0 -> 5:36..6:02). À confirmer avec l'écran de
  l'app avant d'allumer les interrupteurs.

## A. Sync (`webhooks/campus_coach_sync.py`)

- Par étape : `pace` (chaîne, inchangée) + `pace_kind`, `pace_slug`, `pace_zone`, `pace_value_s`
  (entier fourni par Campus, tel quel).
- Par séance : `estimated_paces` = {slug: {value, dvalue}} en `Decimal(str(round(x, 1)))`.
  Doublon de slug : le premier gagne + métrique ; valeur non finie ou <= 0 : ignorée.
- Zones (seulement si `CAMPUS_ZONES_ENABLED=true` sur CampusCoachSync, contexte CDK, défaut
  éteint) : attributs de premier niveau de l'item user-config du propriétaire (`DEFAULT_USER_ID`,
  jamais un `user_id` d'événement) : `campus_pace_zones` = {zone: {min, max, slug, value_s,
  dvalue_s}}, `campus_pace_zones_week`, `campus_pace_zones_synced_at`. Semaine courante
  seulement, un seul `UpdateItem SET` des trois ; écrit seulement si tous les slugs mappés
  existent, sinon rien + métrique `CampusZonesSkipped`.
  Correspondance : recovery<-slow, ef<-ef, aerobic<-aerobie, tempo<-tempo,
  sweet_spot<-sweet-spot, seuil_60<-seuil60, seuil_30<-seuil30, allure_marathon<-marathon,
  allure_semi<-half-marathon, interval<-vma. min = value - dvalue (rapide), max = value + dvalue
  (lent), format m:ss arrondi au plus proche (une seule fonction `shared/pace_zones.fmt_pace`).
  Pour les slugs `single-value`, la largeur ± dvalue est déduite : commentaire dans le code.
- CDK : `dynamodb:UpdateItem` sur la table user-config pour CampusCoachSync seulement ; test CDK.
- Module coupé ou abonnement fini : les zones restent figées à la dernière semaine (`campus_stale`).
- Retour arrière : interrupteur éteint puis `REMOVE` des 3 attributs (commande documentée).

## B. Lecteurs : une seule source

`shared/pace_zones.effective_pace_zones(config_item) -> (zones, source)` : `campus_pace_zones`
s'il existe (source `campus`, ou `campus_stale` si la semaine source a plus d'une semaine),
sinon `user_preferences.pace_zones` (`manual_legacy`), sinon `none`. Pas d'interrupteur côté
lecteurs : tant que la sync n'écrit rien, rien ne change.
Lecteurs : content_generator (résolu AVANT le retour « pas de user_preferences »),
workout_analysis (via content_generator), weekly_audio_recap, coach (le Lambda pose les zones
effectives dans `user_config` avant l'appel), coach_chat (`get_pace_zones` via un miroir local
dans `src/coach_chat/` + test de parité, comme campus_status).

## C. Watch (`shared/campus_workout.py`)

- Nombres convertis une fois à l'entrée (Decimal/str/int -> float fini) ; invalide -> pas
  d'alerte + métrique, jamais de refus de séance.
- `single-value` : comportement IDENTIQUE à aujourd'hui (familles, liste sans alerte
  aerobie/rapide, garde des étapes de bord, `PACE_ALERT_MODE`, noms) ; la cible vient de
  `pace_value_s` (même entier).
- `range` (seulement si `RANGE_ALERTS_ENABLED=true` sur DashboardAPI, défaut éteint) : alerte
  RANGE sur les étapes WORK >= 180 s ET sur échauffement / retour au calme de type range ;
  `slow = 1000/(value+dvalue)`, `fast = 1000/(value-dvalue)` en float brut, bornes dans
  2:00..15:00, 0 < dvalue <= 60 ; CURRENT (AVERAGE pour les courses) ; nom « EF 5:36-6:02 ».
- `abstract` / récup : rien. Ligne legacy (pas de `pace_kind`) : règles d'aujourd'hui.
- Test de parité : jumeaux structurés de chaque golden existant -> mêmes octets, interrupteur
  éteint. Nouveau golden `ef_range` pour l'interrupteur allumé (refaire Gate 0 2b).

## D. Préférences

- API GET : renvoie `campus_pace_zones`, semaine, date, source.
- API POST : ne remplace plus toute la map (ça efface aujourd'hui `strength_history`,
  `pace_zones`, `personal_records`). Map présente : une mise à jour par chemins enfants, `SET`
  des clés de l'API présentes, `REMOVE` des clés optionnelles absentes (max_hr, body_weight_kg,
  height_cm, strength_program, athlete_profile selon les règles actuelles), sans jamais toucher
  `pace_zones`, `strength_history`, ni les autres clés non possédées. Map absente : création de
  la map complète des clés de l'API avec `attribute_not_exists(user_preferences)` ; si un autre
  écrivain l'a créée entre-temps, refaire la mise à jour par chemins enfants une fois. Test sur
  moto (sémantique DynamoDB réelle), pas un MagicMock.
- Page : zones en lecture seule, « Campus · semaine 43 · synchro HH:MM », badge si `campus_stale`,
  plus de champs d'allure ; la sauvegarde n'envoie jamais `pace_zones`.

## Activation

1. Déployer, interrupteurs éteints : rien ne change, sauf les nouveaux champs bruts stockés et
   la sauvegarde des Préférences qui n'efface plus rien.
2. L'athlète compare la plage EF de l'app Campus à la nôtre.
3. Si elle colle : `CAMPUS_ZONES_ENABLED` puis `RANGE_ALERTS_ENABLED`, re-télécharger une
   séance EF, la courir, juger les vibrations.
