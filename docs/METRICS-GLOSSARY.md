# Metrics glossary

> Source-backed definitions for the KPIs surfaced in Strava AI Boost.
> Used to populate the help tooltip on every KPI card (FR + EN).

---

## CTL — Chronic Training Load

**EN — Definition**: A rolling estimate of long-term fitness, representing how much training load you have absorbed over the past several weeks. Often labelled "Fitness".
**EN — How**: Exponentially-weighted moving average of daily training load (typically TSS) with a 42-day time constant.
**FR — Définition**: Estimation de la forme de fond ("fitness"), reflétant la charge d'entraînement absorbée sur plusieurs semaines.
**FR — Calcul**: Moyenne mobile exponentielle de la charge journalière (TSS) avec une constante de temps de 42 jours.
**Source**: https://www.trainingpeaks.com/learn/articles/the-science-of-the-performance-manager/

---

## ATL — Acute Training Load

**EN — Definition**: A rolling estimate of short-term fatigue, representing the training load accumulated in the last week or so. Often labelled "Fatigue".
**EN — How**: Exponentially-weighted moving average of daily training load (typically TSS) with a 7-day time constant.
**FR — Définition**: Estimation de la fatigue récente liée à la charge d'entraînement de la dernière semaine.
**FR — Calcul**: Moyenne mobile exponentielle de la charge journalière (TSS) avec une constante de temps de 7 jours.
**Source**: https://www.trainingpeaks.com/learn/articles/the-science-of-the-performance-manager/

---

## TSB — Training Stress Balance (Form)

**EN — Definition**: The balance between fitness and fatigue, used as a proxy for race-day freshness. Positive values mean fresh, negative values mean fatigued.
**EN — How**: Computed as `CTL - ATL` (fitness minus fatigue), usually using yesterday's values.
**FR — Définition**: Écart entre la forme et la fatigue, utilisé comme indicateur de fraîcheur. Positif = frais, négatif = fatigué.
**FR — Calcul**: Différence `CTL - ATL` (forme moins fatigue), généralement calculée avec les valeurs de la veille.
**Source**: https://www.trainingpeaks.com/learn/articles/the-science-of-the-performance-manager/

---

## Ramp Rate — CTL increase per week

**EN — Definition**: How fast your fitness (CTL) is rising week over week. A practical guard-rail against overtraining.
**EN — How**: Difference between current CTL and CTL 7 days ago; sustainable values are typically 3–7 TSS/week.
**FR — Définition**: Vitesse à laquelle ta forme (CTL) progresse chaque semaine. Garde-fou simple contre le surentraînement.
**FR — Calcul**: Écart entre le CTL actuel et le CTL d'il y a 7 jours ; une progression saine se situe en général entre 3 et 7 TSS/semaine.
**Source**: https://www.trainingpeaks.com/learn/articles/the-optimal-ctl-ramp-rate/

---

## TSS — Training Stress Score

**EN — Definition**: A single number quantifying the overall stress of one workout, normalised so that 1 hour at functional threshold equals 100.
**EN — How**: Computed from intensity factor and duration: `TSS = (sec × NP × IF) / (FTP × 3600) × 100`.
**FR — Définition**: Score unique résumant la charge d'une séance, calibré pour qu'une heure au seuil vaille 100.
**FR — Calcul**: Calculé à partir de l'intensité et de la durée : `TSS = (sec × NP × IF) / (FTP × 3600) × 100`.
**Source**: https://www.trainingpeaks.com/learn/articles/what-is-tss/

---

## Decoupling — Aerobic Decoupling / Cardiac Drift

**EN — Definition**: How much your heart rate drifts upward for the same pace/power during a steady aerobic effort. A low value indicates strong aerobic fitness.
**EN — How**: Compare the pace-to-HR (or power-to-HR) ratio of the first half versus the second half of the run; under 5% is considered coupled.
**FR — Définition**: Dérive cardiaque pendant un effort stable : à allure constante, la FC s'élève si l'endurance aérobie est faible.
**FR — Calcul**: Ratio allure/FC (ou puissance/FC) comparé entre la première et la seconde moitié de la séance ; <5% = découplage maîtrisé.
**Source**: https://www.trainingpeaks.com/learn/articles/aerobic-endurance-and-decoupling/

---

## HRV — Heart Rate Variability

**EN — Definition**: The natural variation in time between consecutive heartbeats, used as a marker of recovery and autonomic nervous system balance.
**EN — How**: Measured (typically at rest, on waking) as RMSSD or SDNN in milliseconds from R-R intervals on an ECG or optical sensor.
**FR — Définition**: Variation naturelle du temps entre deux battements cardiaques, indicateur de récupération et d'équilibre du système nerveux.
**FR — Calcul**: Mesurée au repos (souvent au réveil) en RMSSD ou SDNN, en millisecondes, à partir des intervalles R-R.
**Source**: https://www.ahajournals.org/doi/10.1161/01.CIR.93.5.1043

---

## VO2max — Maximal Oxygen Uptake

**EN — Definition**: The maximum amount of oxygen your body can use per minute during all-out exercise. The reference marker of aerobic capacity.
**EN — How**: Measured directly in a lab via gas exchange, or estimated from running pace and heart rate by wearables (Firstbeat, Garmin, Apple).
**FR — Définition**: Quantité maximale d'oxygène que ton corps peut utiliser à l'effort maximal, référence de la capacité aérobie.
**FR — Calcul**: Mesurée en laboratoire via les échanges gazeux, ou estimée par les montres connectées à partir de l'allure et de la FC.
**Source**: https://www.cooperinstitute.org/vault/2440/web/files/661.pdf

---

## Resting HR — Resting Heart Rate

**EN — Definition**: Your heart rate measured at complete rest, typically just after waking up. A trending downward value reflects improving cardiovascular fitness.
**EN — How**: Lowest sustained HR over a few minutes at rest (lying down), measured with a chest strap, optical wearable, or by manual pulse count.
**FR — Définition**: Fréquence cardiaque mesurée au repos complet, idéalement juste après le réveil. Une baisse traduit une meilleure forme cardiovasculaire.
**FR — Calcul**: FC la plus basse maintenue quelques minutes au repos (allongé), mesurée à la ceinture, à la montre ou en prise manuelle.
**Source**: https://www.heart.org/en/healthy-living/fitness/fitness-basics/target-heart-rates

---

## Sleep — Duration & Quality

**EN — Definition**: Total sleep time and its restorative quality, the single biggest lever for adaptation and recovery between sessions.
**EN — How**: Tracked by wearables combining accelerometer, HR and HRV signals to estimate stages (deep, REM, light) and duration; adults need 7–9 h.
**FR — Définition**: Durée et qualité du sommeil, principal levier de récupération et d'adaptation entre les séances.
**FR — Calcul**: Estimée par les montres via accéléromètre, FC et VFC (stades profond, REM, léger) ; la cible adulte est 7 à 9 h.
**Source**: https://www.cdc.gov/sleep/about_sleep/how_much_sleep.html

---

## EF — Efficiency Factor (Easy Pace / Aerobic Endurance)

**EN — Definition**: The ratio of running pace to heart rate during steady aerobic work. Rising EF over time means you go faster at the same heart rate — pure aerobic gains.
**EN — How**: Computed as normalised pace divided by average HR for the working portion of the session; tracked across easy/long runs to spot trends.
**FR — Définition**: Rapport entre l'allure et la FC sur un effort aérobie stable. Un EF qui monte = même FC, allure plus rapide = progrès aérobie pur.
**FR — Calcul**: Allure normalisée divisée par la FC moyenne de la portion utile ; suivi sur sorties faciles ou longues pour détecter la tendance.
**Source**: https://www.trainingpeaks.com/learn/articles/aerobic-endurance-and-decoupling/

---

## Confidence — AI Coach confidence score

**EN — Definition**: A 0–1 score returned by Strava AI Boost on every generated description, reflecting how strongly the model trusts its workout interpretation.
**EN — How**: Computed in `workout_analysis.py` from pace consistency (`min(0.95, 0.6 + (1 - pace_std) × 0.3)`), then carried through `content_generator.py` and stored on the activity record.
**FR — Définition**: Score (0 à 1) renvoyé par Strava AI Boost à chaque description générée, indiquant la confiance du modèle dans son interprétation de la séance.
**FR — Calcul**: Calculé dans `workout_analysis.py` à partir de la régularité de l'allure (`min(0,95 ; 0,6 + (1 − pace_std) × 0,3)`), puis transmis via `content_generator.py` et stocké sur l'activité.
**Source**: Interne — `lambda_functions/processing/workout_analysis.py`, `lambda_functions/processing/content_generator.py`

---

## Edit rate — User modification rate

**EN — Definition**: The share of AI-generated descriptions that the user edits before saving on Strava. Lower is better — a falling rate means the AI is converging on the user's voice.
**EN — How**: A nightly job (`feedback_analyzer.py`) compares enhanced vs final Strava description with `difflib.SequenceMatcher`; below 99.5% similarity counts as modified, then `modified / total` is reported.
**FR — Définition**: Part des descriptions IA que l'utilisateur retouche avant publication sur Strava. Plus elle baisse, plus l'IA imite ton style.
**FR — Calcul**: Un job nocturne (`feedback_analyzer.py`) compare la description IA et la version finale via `difflib.SequenceMatcher` ; en-dessous de 99,5% de similarité, l'activité compte comme modifiée, puis `modifiées / total`.
**Source**: Interne — `lambda_functions/support/feedback_analyzer.py`

---

## Similarity — IA / final cosine similarity

**EN — Definition**: Closeness between the AI-generated description and the user's final version on Strava, on a 0–1 scale. 1.0 means untouched.
**EN — How**: `difflib.SequenceMatcher.ratio()` on the lowercased, stripped strings; ≥ 0.995 is considered untouched and the activity is not flagged as modified.
**FR — Définition**: Proximité entre la description générée par l'IA et la version finale sur Strava, sur une échelle 0–1. 1,0 = non modifiée.
**FR — Calcul**: `difflib.SequenceMatcher.ratio()` sur les chaînes en minuscules ; ≥ 0,995 = activité non modifiée.
**Source**: Interne — `lambda_functions/support/feedback_analyzer.py` (fonction `detect_modification`)

---

## i18n keys — copy-paste block

The block below contains all keys for the 14 metrics. Drop the `en` block into `frontend/src/i18n/en.json` and the `fr` block into `frontend/src/i18n/fr.json` (merge with existing keys).

```json
{
  "en": {
    "metrics.ctl.label": "CTL",
    "metrics.ctl.title": "Chronic Training Load",
    "metrics.ctl.definition": "A rolling estimate of long-term fitness, representing how much training load you have absorbed over the past several weeks.",
    "metrics.ctl.calculation": "Exponentially-weighted moving average of daily training load (typically TSS) with a 42-day time constant.",

    "metrics.atl.label": "ATL",
    "metrics.atl.title": "Acute Training Load",
    "metrics.atl.definition": "A rolling estimate of short-term fatigue, representing the training load accumulated in the last week or so.",
    "metrics.atl.calculation": "Exponentially-weighted moving average of daily training load (typically TSS) with a 7-day time constant.",

    "metrics.tsb.label": "Form",
    "metrics.tsb.title": "Training Stress Balance",
    "metrics.tsb.definition": "The balance between fitness and fatigue, used as a proxy for race-day freshness. Positive = fresh, negative = fatigued.",
    "metrics.tsb.calculation": "Computed as CTL minus ATL, usually using yesterday's values.",

    "metrics.ramp.label": "Ramp",
    "metrics.ramp.title": "CTL Ramp Rate",
    "metrics.ramp.definition": "How fast your fitness (CTL) is rising week over week. A guard-rail against overtraining.",
    "metrics.ramp.calculation": "Difference between current CTL and CTL 7 days ago; sustainable range is 3-7 TSS/week.",

    "metrics.tss.label": "TSS",
    "metrics.tss.title": "Training Stress Score",
    "metrics.tss.definition": "A single number quantifying the overall stress of one workout, calibrated so 1 hour at threshold equals 100.",
    "metrics.tss.calculation": "Computed from intensity factor and duration: TSS = (sec * NP * IF) / (FTP * 3600) * 100.",

    "metrics.decoupling.label": "Decoupling",
    "metrics.decoupling.title": "Aerobic Decoupling",
    "metrics.decoupling.definition": "How much your heart rate drifts upward at the same pace during a steady aerobic effort. Lower = better aerobic fitness.",
    "metrics.decoupling.calculation": "Compare pace-to-HR ratio of the first vs. second half of the run; under 5% is considered coupled.",

    "metrics.hrv.label": "HRV",
    "metrics.hrv.title": "Heart Rate Variability",
    "metrics.hrv.definition": "The natural variation in time between heartbeats, used as a marker of recovery and nervous system balance.",
    "metrics.hrv.calculation": "Measured at rest as RMSSD or SDNN in milliseconds from R-R intervals.",

    "metrics.vo2max.label": "VO2max",
    "metrics.vo2max.title": "Maximal Oxygen Uptake",
    "metrics.vo2max.definition": "The maximum amount of oxygen your body can use per minute. The reference marker of aerobic capacity.",
    "metrics.vo2max.calculation": "Measured in a lab via gas exchange, or estimated by wearables from running pace and heart rate.",

    "metrics.restinghr.label": "Resting HR",
    "metrics.restinghr.title": "Resting Heart Rate",
    "metrics.restinghr.definition": "Your heart rate measured at complete rest. A trending downward value reflects improving cardiovascular fitness.",
    "metrics.restinghr.calculation": "Lowest sustained HR over a few minutes at rest, measured with a chest strap, watch, or manual pulse count.",

    "metrics.sleep.label": "Sleep",
    "metrics.sleep.title": "Sleep Duration & Quality",
    "metrics.sleep.definition": "Total sleep time and its restorative quality, the single biggest lever for adaptation and recovery.",
    "metrics.sleep.calculation": "Tracked by wearables combining accelerometer, HR and HRV; adults need 7-9 hours.",

    "metrics.ef.label": "EF",
    "metrics.ef.title": "Efficiency Factor",
    "metrics.ef.definition": "Ratio of pace to heart rate during steady aerobic work. Rising EF means same HR but faster pace - pure aerobic gains.",
    "metrics.ef.calculation": "Normalised pace divided by average HR; tracked across easy and long runs to spot trends.",

    "metrics.confidence.label": "Confidence",
    "metrics.confidence.title": "AI Coach Confidence",
    "metrics.confidence.definition": "A 0-1 score on every generated description reflecting how strongly the model trusts its workout interpretation.",
    "metrics.confidence.calculation": "Computed from pace consistency: min(0.95, 0.6 + (1 - pace_std) * 0.3), then carried through content generation.",

    "metrics.editrate.label": "Edit rate",
    "metrics.editrate.title": "User Modification Rate",
    "metrics.editrate.definition": "Share of AI-generated descriptions that the user edits before saving. Lower is better - the AI is converging on your voice.",
    "metrics.editrate.calculation": "Nightly job compares enhanced vs final description with SequenceMatcher; below 99.5% similarity counts as modified.",

    "metrics.similarity.label": "Similarity",
    "metrics.similarity.title": "AI / Final Similarity",
    "metrics.similarity.definition": "Closeness between the AI-generated description and your final version on Strava, on a 0-1 scale. 1.0 means untouched.",
    "metrics.similarity.calculation": "difflib SequenceMatcher ratio on lowercased strings; >= 0.995 means activity not flagged as modified."
  },
  "fr": {
    "metrics.ctl.label": "CTL",
    "metrics.ctl.title": "Charge chronique d'entraînement",
    "metrics.ctl.definition": "Estimation de la forme de fond, reflétant la charge d'entraînement absorbée sur plusieurs semaines.",
    "metrics.ctl.calculation": "Moyenne mobile exponentielle de la charge journalière (TSS) avec une constante de temps de 42 jours.",

    "metrics.atl.label": "ATL",
    "metrics.atl.title": "Charge aiguë d'entraînement",
    "metrics.atl.definition": "Estimation de la fatigue récente liée à la charge d'entraînement de la dernière semaine.",
    "metrics.atl.calculation": "Moyenne mobile exponentielle de la charge journalière (TSS) avec une constante de temps de 7 jours.",

    "metrics.tsb.label": "Forme",
    "metrics.tsb.title": "Équilibre de stress d'entraînement",
    "metrics.tsb.definition": "Écart entre la forme et la fatigue, indicateur de fraîcheur. Positif = frais, négatif = fatigué.",
    "metrics.tsb.calculation": "Différence CTL moins ATL, généralement calculée avec les valeurs de la veille.",

    "metrics.ramp.label": "Ramp",
    "metrics.ramp.title": "Vitesse de progression du CTL",
    "metrics.ramp.definition": "Vitesse à laquelle ta forme progresse chaque semaine. Garde-fou contre le surentraînement.",
    "metrics.ramp.calculation": "Écart entre le CTL actuel et celui d'il y a 7 jours ; cible saine entre 3 et 7 TSS par semaine.",

    "metrics.tss.label": "TSS",
    "metrics.tss.title": "Score de stress d'entraînement",
    "metrics.tss.definition": "Score résumant la charge d'une séance, calibré pour qu'une heure au seuil vaille 100.",
    "metrics.tss.calculation": "Calculé à partir de l'intensité et de la durée : TSS = (sec * NP * IF) / (FTP * 3600) * 100.",

    "metrics.decoupling.label": "Découplage",
    "metrics.decoupling.title": "Découplage aérobie",
    "metrics.decoupling.definition": "Dérive de la FC à allure constante sur un effort aérobie. Plus c'est bas, meilleure est l'endurance.",
    "metrics.decoupling.calculation": "Ratio allure/FC comparé entre la première et la seconde moitié de la séance ; <5% = bon découplage.",

    "metrics.hrv.label": "VFC",
    "metrics.hrv.title": "Variabilité cardiaque",
    "metrics.hrv.definition": "Variation naturelle du temps entre deux battements, indicateur de récupération et d'équilibre nerveux.",
    "metrics.hrv.calculation": "Mesurée au repos en RMSSD ou SDNN, en millisecondes, à partir des intervalles R-R.",

    "metrics.vo2max.label": "VO2max",
    "metrics.vo2max.title": "Consommation maximale d'oxygène",
    "metrics.vo2max.definition": "Quantité maximale d'oxygène utilisable à l'effort maximal, référence de la capacité aérobie.",
    "metrics.vo2max.calculation": "Mesurée en laboratoire ou estimée par les montres à partir de l'allure et de la FC.",

    "metrics.restinghr.label": "FC repos",
    "metrics.restinghr.title": "Fréquence cardiaque au repos",
    "metrics.restinghr.definition": "FC mesurée au repos complet, idéalement au réveil. Une baisse traduit une meilleure forme cardiovasculaire.",
    "metrics.restinghr.calculation": "FC la plus basse maintenue quelques minutes au repos (allongé), à la ceinture, montre ou prise manuelle.",

    "metrics.sleep.label": "Sommeil",
    "metrics.sleep.title": "Durée et qualité du sommeil",
    "metrics.sleep.definition": "Durée et qualité du sommeil, principal levier de récupération et d'adaptation entre les séances.",
    "metrics.sleep.calculation": "Estimée par les montres via accéléromètre, FC et VFC ; cible adulte de 7 à 9 heures.",

    "metrics.ef.label": "EF",
    "metrics.ef.title": "Facteur d'efficacité",
    "metrics.ef.definition": "Rapport allure / FC sur effort aérobie stable. Un EF qui monte = même FC mais plus rapide = progrès aérobie.",
    "metrics.ef.calculation": "Allure normalisée divisée par la FC moyenne ; suivi sur les sorties faciles et longues.",

    "metrics.confidence.label": "Confiance",
    "metrics.confidence.title": "Confiance du coach IA",
    "metrics.confidence.definition": "Score de 0 à 1 sur chaque description générée, indiquant la confiance du modèle dans son interprétation.",
    "metrics.confidence.calculation": "Calculé sur la régularité d'allure : min(0,95 ; 0,6 + (1 - pace_std) * 0,3), puis transmis à la génération.",

    "metrics.editrate.label": "Taux d'édition",
    "metrics.editrate.title": "Taux de modification utilisateur",
    "metrics.editrate.definition": "Part des descriptions IA retouchées avant publication. Plus c'est bas, mieux l'IA imite ton style.",
    "metrics.editrate.calculation": "Job nocturne comparant IA vs version finale avec SequenceMatcher ; <99,5% = modifiée.",

    "metrics.similarity.label": "Similarité",
    "metrics.similarity.title": "Similarité IA / version finale",
    "metrics.similarity.definition": "Proximité entre description IA et version finale sur Strava, échelle 0-1. 1,0 = non modifiée.",
    "metrics.similarity.calculation": "Ratio difflib SequenceMatcher sur chaînes en minuscules ; >= 0,995 = activité non modifiée."
  }
}
```
