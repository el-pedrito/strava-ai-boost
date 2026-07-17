# Competitive analysis & feature ideas

> 🗄️ **Document d'archive (analyse d'avril 2026).** Le positionnement retenu est
> open-source personnel — les pistes produit/monétisation ci-dessous ne sont
> **PAS** poursuivies. Voir [docs/ROADMAP.md](./ROADMAP.md).

> Mai 2026 — analyse concurrentielle pour orienter la roadmap. Tarifs collectés depuis les sites publics, "as of May 2026" sauf indication contraire. Focus running, mais lecture multi-sport pour repérer les angles morts.

## Concurrents inspectés

### Coachs IA / plans adaptatifs

- **Runna** — <https://www.runna.com/> — Plans personnalisés 5K à ultra, sync Garmin/Apple Watch, strength + mobility, "Runna Engine" pour adapter selon performance. **19,99 EUR / mois ou 119,99 EUR / an**, 1 semaine d'essai. Acquis / partenaire Strava début 2026 (visible dans la page Strava Subscription : "add Runna to meet your running goals and save up to 60%").
- **RunDot / TriDot** — <https://rundot.com/> — Plans adaptatifs basés sur "Training Stress" propriétaire, ajustement météo (chaleur, humidité, élévation), réduction du risque de blessure. App mobile, modèle freemium, pricing à l'inscription.
- **Stryd** — <https://www.stryd.com/eu/en/pages/training-with-power> — Capteur de puissance running + plateforme. Critical Power, plans adaptés à la fitness, intégrations TrainingPeaks / Final Surge. Hardware : capteur ~219 EUR, plateforme incluse.
- **TrainingPeaks** — <https://www.trainingpeaks.com/> — Plateforme reine du coaching multi-sport. ATL/CTL/TSB ("Performance Management Chart"), workout builder, marketplace de coachs et plans, Virtual (indoor cycling), strength avec 1000+ vidéos. Tarif athlète Premium environ 19,99 USD / mois, coach environ 25 USD / mois (2025). Adopté par 87 % des équipes WorldTour cyclistes selon leur site.

### Analytics & journaux

- **Intervals.icu** — <https://intervals.icu/> — Plateforme **gratuite** (déjà module dans Strava AI Boost). 160k+ athlètes, 193M activités. Performance Management Chart, workout builder, Power Curve, eFTP auto, decoupling cardiaque, multisport. Modèle de référence pour la profondeur analytique.
- **Final Surge** — <https://www.finalsurge.com/> — Journal d'entraînement gratuit pour athlète + offre coach payante (essai 14 jours). Sync Garmin / Strava / TrainerRoad / Zwift. Communication athlète-coach.
- **Smashrun** — <https://smashrun.com/> — Stats running avec gamification (badges, médailles, classements démographiques). Pro environ 60 USD / an. Positionnement émotionnel : "addictif".

### Native players (watch / wearable)

- **Garmin Connect** — <https://www.garmin.com/en-US/garmin-technology/running-science/physiological-measurements/> — Fonctionnalités IA-adjacentes massives : Training Status, VO2 Max, Recovery Time, Training Load, Heat & Altitude Acclimation, Daily Suggested Workouts, Training Effect, Lactate Threshold, Race Time Prediction, Real-Time Stamina, Endurance Score, **Running Economy**, **Running Tolerance**, Training Readiness. Inclus avec la montre.
- **Coros Training Hub** — site indisponible au moment du test. Connue pour EvoLab (analyse charge), running fitness score, base / threshold / anaerobic capacity. Inclus avec la montre.
- **Whoop** — <https://www.whoop.com/> — Recovery, Strain, Sleep, Stress, HRV. Coaching personnalisé, Healthspan / Pace of Aging, Health Monitor. Abonnement 199 EUR / 264 EUR / 399 EUR par an selon le tier (One / Peak / Life). Hardware fourni avec l'abo.

### Le concurrent direct : Strava lui-même

- **Strava Subscription** — <https://www.strava.com/subscribe> — 59,99 EUR / an individuel, 99,99 EUR / an famille (4), 29,99 EUR / an étudiant. Intègre **Athlete Intelligence** (GenAI) sortie de bêta en février 2025, qui résume les workouts et agrège les tendances 30 jours. Source : <https://press.strava.com/articles/stravas-athlete-intelligence-translates-workout-data-into-simple-and>. Ajout en 2025 : insights de puissance, segment analysis, données indoor/virtual.

### Open source et indie (concurrents indirects)

- **AG3NTSN0W/strava-ai** (Rust, GitHub) — self-hosted, génère titres + descriptions IA pour Strava.
- **RamonGarciaGomez/strava-description-updater** — JS, fun facts via Claude.
- **mlamberts78/strava-openai-coach** — Python, analyse perso via OpenAI.
- **tinspham209/rundecode** — TS, analyse FIT/Strava avec contexte route, sync description en un tap.

Lecture clé : la primitive "IA enrichit la description Strava" est **commoditisée** côté hobbyiste. La défense de Strava AI Boost ne peut pas être seulement "on génère des titres".

---

## Features identifiées

### Quick wins (S, 1 à 7 jours dev)

1. **Race time prediction calibrée par profil** (valeur forte / effort S / commodité — Garmin et Runna le font).
   - Calculer une prédiction 5K / 10K / semi / marathon depuis les records perso et la VO2 Max estimée. UI : carte sur Dashboard.
   - Stack OK : tout est déjà côté Lambda + DynamoDB.
2. **Badges et streaks de cohérence** (valeur moyenne / effort S / commodité — Smashrun, Strava).
   - "5 semaines régulières", "3 séances qualité ce mois", "100 km sur 30 j". Encourage le retour.
3. **Score de cohérence hebdo simple** (valeur moyenne / effort S / réel avantage si bien narrativé).
   - Un pourcentage 0 à 100 calculé depuis le respect du plan recommandé (volume cible, ratio EF/qualité). Coach IA rédige un commentaire en français adapté au ton de l'athlète.
4. **Export PDF de cycle d'entraînement** (valeur faible mais sticky / effort S / commodité — TrainingPeaks le fait).
   - Récapitulatif 4 / 8 / 12 semaines avec graphes et résumé Coach. Vendable en upsell.
5. **Lien partage public d'une activité enrichie** (valeur moyenne / effort S / différenciation virale).
   - URL signée CloudFront `/share/{activityId}` qui affiche le titre IA + description + map. SEO secondaire = acquisition gratuite.

### Mid-term (M, 2 à 6 semaines)

1. **Voice debrief audio post-séance** (valeur forte / effort M / **réel avantage** — personne ne le fait au moment du test).
   - Bedrock Polly Neural ou Sonic-style : à la fin d'une activité, l'app génère un debrief audio de 60 à 90 s lu en français ou anglais avec la voix choisie par l'athlète. Stocké en S3, accessible en stream.
   - Risque : aucun. Stack 100 % AWS-native.
2. **Plan d'entraînement adaptatif** (valeur forte / effort M-L / commodité — Runna, RunDot, Garmin).
   - Générer un plan 4 à 16 semaines via Bedrock + Coach IA, recalculer chaque semaine selon performance réelle (CTL/ATL via intervals.icu) et météo (Enduraw). UI : calendrier avec drag-and-drop.
   - Risque : médical léger ("entraînez-vous à votre risque"), prévoir disclaimers.
3. **Detection d'anomalies santé via streams Strava** (valeur forte / effort M / réel avantage).
   - Drift cardiaque anormal, baisse soudaine d'allure à FC stable, variabilité d'allure suspecte. Coach IA propose : "Tu sembles fatigué — repos ou EF léger demain ?" Notifications push.
   - Stack : streams API Strava + DynamoDB + Bedrock. Pas de pivot.
4. **Mode "Race week"** (valeur forte / effort M / différenciation).
   - À T-7 j d'un objectif, l'UI passe en mode tapering : check-list (sommeil, hydratation, nutrition), prédiction de chrono actualisée, méteo course (Enduraw), conseils stratégie (Coach IA).
5. **Comparaison vs cohorte anonymisée** (valeur moyenne / effort M / commodité — Smashrun).
   - "Tu es dans le top 30 % des H35-40 sur 5 km à FC similaire." Cohort calculée depuis la base d'utilisateurs anonymisés. Privacy : opt-in obligatoire.

### Ambitions (L / XL, 1 à 3 mois)

1. **Voice coach temps-réel pendant la sortie** (valeur très forte / effort XL / **gros avantage compétitif**).
   - App mobile (PWA + Web Speech API ou React Native) qui lit en streaming des cues IA pendant la course : "Tu accélères, ralentis 10 s / km, FC zone 4." Bedrock Sonic ou Polly streaming.
   - Risque : médical (fatigue, blessure). Disclaimers, pas de prescription santé.
   - Pivot stack léger : il faut un endpoint streaming WebSocket (API Gateway WebSocket ou AppSync).
2. **Marketplace de plans humains** (valeur forte / effort L / commodité — TrainingPeaks, Final Surge).
   - Coachs créent des plans, les vendent via Stripe Connect, l'IA les personnalise en remplissant les paramètres (allures, FC, dispo). Strava AI Boost prend une commission.
3. **Mode "Club / Team"** (valeur forte / effort L / différenciation B2B).
   - Un coach humain gère 5 à 50 athlètes via la même UI, voit dashboards agrégés, envoie des feedbacks groupés. Pricing par siège.
4. **App mobile native** (valeur très forte / effort XL).
   - Déjà au roadmap. Capacitor ou React Native pour profiter du widget watchOS / WearOS et des notifications natives.
5. **Modèle ML maison de prédiction de blessure** (valeur très forte / effort XL / différenciation).
   - À partir des streams Strava (cadence, GAP, asymétrie d'allure, ramp rate), un modèle SageMaker estime un risque de blessure 7 à 14 jours en avance. Garmin Running Tolerance fait quelque chose de similaire mais cantonné à la montre.

---

## Idées originales (peu ou pas faites sur le marché)

1. **GenAI image d'achievement partageable** (différenciation virale).
   - Après un PB ou un objectif atteint, Bedrock Image (Nova Canvas / Stable Diffusion) génère une image d'illustration personnalisée — l'athlète + sa ville + son chrono — pour partager sur Instagram. Strava ne le fait pas, c'est gratuit pour l'utilisateur, viral pour l'acquisition.
2. **Coach IA conversationnel multi-tour avec mémoire longue (AgentCore Memory)**.
   - L'athlète pose des questions par texte ou voix : "Pourquoi mes intervalles sont moins bons cette semaine ?" Le coach se rappelle des séances précédentes, des plans en cours, des blessures déclarées. Stack déjà là : AgentCore Memory + Bedrock. Ce serait un vrai différenciateur si l'UX est soignée — Athlete Intelligence de Strava est mono-tour.
3. **"Strava AI Boost Battles" — défis IA générés sur mesure**.
   - L'IA propose chaque dimanche un défi adapté : "Cette semaine, fais 3 séances dont une au seuil. Si tu réussis, tu débloques le prochain niveau." Gamification qui combine plan adaptatif + badges + virality.
4. **Recap audio hebdo type podcast** (1 à 3 min).
   - Chaque dimanche, un fichier audio généré avec Bedrock Polly + script Claude résume ta semaine, identifie un point fort, un point d'amélioration et propose le focus de la semaine suivante. Spotify-like dans l'écoute matinale.
5. **Carte de chaleur "stress racial" depuis les streams + Enduraw**.
   - Croiser cadence + GAP + vent + température pour produire une vue type "Où ta course a souffert ?" sur la map. Visuel premium, partageable. Aucune appli mainstream ne croise ces signaux à la granularité segment.
6. **Pacer virtuel TTS pendant un fractionné**.
   - L'app TTS-call ton split en temps réel : "400e mètre, 92 secondes, parfait, repose 60 s." Comme un coach humain à l'oreille. Combine voice coach + structured workouts.

---

## Recommandations top 5

Priorité = (valeur user) x (différenciation possible) / (effort).

1. **Race time prediction + plan d'entraînement adaptatif minimum viable** (mid-term, M).
   Strava bundle Runna pour cette raison ; ne pas l'avoir creuse un trou. Commencer par la prédiction (S, 1-2 j) puis dérouler sur le plan adaptatif basique.

2. **Voice debrief audio post-séance** (mid-term, M).
   Quick win différenciant. Personne ne le fait. Stack 100 % AWS, aucun risque produit. Démontre la valeur Bedrock vs un simple texte.

3. **Coach IA conversationnel avec mémoire longue, mode chat soigné** (mid-term, M).
   Athlete Intelligence de Strava est mono-tour. Différenciation immédiate si l'UX chat est meilleure (latence < 2 s, citations des séances passées, mémoire personnalisée).

4. **Detection d'anomalies santé proactives via streams** (mid-term, M).
   Sticky : un athlète qui reçoit une alerte fatigue pertinente revient. Prévention de blessure = très haute valeur perçue.

5. **Onboarding stepper** (court terme, S — déjà au roadmap).
   Pré-requis pour tout le reste. Sans onboarding fluide Strava OAuth + préférences en 60 s, les features ci-dessus se font perdre par friction.

---

## Notes de risque transverses

- **Privacy** : la base utilisateur a des données santé (FC, sommeil potentiel via wearable). Tout feature de cohorte ou de partage doit être opt-in explicite, RGPD-compliant.
- **Médical** : ne jamais prescrire de la santé. Disclaimer "à vocation informative, consultez un professionnel" sur chaque feature à connotation blessure / fatigue.
- **Coût Bedrock** : un debrief audio ou une image génère facile 0,01 à 0,05 USD par activité. À 1 000 utilisateurs actifs avec 4 activités / semaine, prévoir 200 à 800 USD / mois. Cache les sorties par activityId, hash sur (athlete profile + activity hash).
- **Strava ToS** : la description sur l'activité Strava est OK ; les clones full-feature de Strava (segments, kudos) seraient en violation. Rester sur la couche "intelligence" au-dessus.
