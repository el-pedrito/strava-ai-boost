# Worked example: one real activity, end to end

> The August 15, 2026 long run, exactly as the pipeline processed it. Every JSON below is the real data as stored in DynamoDB. See also the [functional process flow](architecture/process-flow.png).

Rather than a theoretical diagram, a real recent activity. Long run, heat wave. My raw description, typed from the phone in my two minutes (in French, my running language, rough translation below):

> Sortie « longue » de la semaine en intégrant bloc actif. Impossible de me lever tôt pour courir à la fraîche. Du coup, run sous le cagnard. En me mouillant à toutes les fontaines sur le chemin.

("Long run of the week with an active block. Could not get up early to run in the cool. So, run under the blazing sun. Soaking myself at every fountain on the way.")

During the same window, Enduraw appends its report right after: heat 25°C = 0'09"/km lost, wind = 0'06"/km, sweat rate 0.9L/h.

Now, under the hood, step by step:

**1. The webhook.** Strava pushes a tiny POST, just a pointer:

```json
{"object_type": "activity", "object_id": 19749386787,
 "aspect_type": "create", "owner_id": "...", "subscription_id": "..."}
```

Signature validated, answer in under 5 seconds, and the message goes to SQS with `DelaySeconds=120`. Those 120 seconds are my two minutes.

**2. The fetch.** The delay expires, Step Functions starts, the `activity_fetcher` Lambda calls `GET /activities/{id}` and `GET /activities/{id}/laps` on Strava, plus the Intervals.icu API. Everything lands in DynamoDB. The raw laps, as stored:

```json
{"name": "Lap 2", "distance": "919.96", "moving_time": 299, "average_speed": "3.08"}
{"name": "Lap 3", "distance": "178.51", "moving_time": 120, "average_speed": "1.49"}
```

And the Intervals.icu fitness context:

```json
{"fitness": {"ctl": "16.61", "atl": "19.88", "form": "-3.3"},
 "trends": {"vo2max": {"current": "53.45", "avg_30d": "51.3", "delta_7d": "1.1"}}}
```

**3. The computing, in code, before any LLM.** The `content_generator` Lambda classifies the session from the laps: `1000 / 3.08 = 325 s`, that is 5:25/km. The relative contrast between laps separates work (3.06 to 3.09 m/s) from recovery (1.49 to 1.92 m/s): warmup + 4x(5min work + 2min recovery) + cooldown. The Campus matching queries the DynamoDB partition of the activity's ISO week and scores each planned session (type, duration, count and duration of intervals): the "Long Run with active block 4x5min Tempo" passes the 0.5 threshold, gets bound to the activity and marked done.

**4. The prompt.** The content agent receives pre-chewed sections: the activity, the laps formatted with computed paces, the matched Campus session, the Intervals.icu context, my profile (records, max HR, goal), my learned preferences read back from the Memory, and my raw description to preserve. The model has not one single computation left to do. Only the storytelling.

**5. The verifier.** The output is compared to the computed facts (paces, interval counts, week scope). Contradiction: regenerate once with the diagnosis. Still wrong: the sentence gets removed.

**6. The assembly.** The assembly Lambda merges the content and the coach feedback, then `PUT /activities/19749386787` on Strava. End of the trip, about one minute after the delay expires.

What each source brings to the agent's context:

- 🟠 **Strava (laps)**: 11 raw laps, each with its speed AND its average heart rate. The code reads a 3.9km warmup at 6:29/km, 4 fractions of 5min at 5:23-5:26/km (HR 158-162 bpm), 2min recoveries, a cooldown. Paces are computed in code from the speeds, never by the model.
- 🟣 **Campus Coach**: the session planned that day, "Long Run with active block 4x5min Tempo", target 5:26/km. The deterministic matching binds it to the activity: the agent knows this was THE session of the plan, not an improvised run.
- 🔴 **Intervals.icu**: VO2max at 53.45 (+1.1 vs 30-day average), resting HR 51, form -3.3. The trend, not just the day.
- 🔵 **Enduraw**: how much the day's conditions cost me, in numbers (heat 0'09"/km, wind 0'06"/km). It is a free integration: you connect your Strava account once, and the report pastes itself into the description of every activity, probably triggered by the same Strava webhook as my app. It lands during the two-minute window, and the pipeline reads it at fetch time like the rest.
- 🟡 **My two minutes**: the blazing sun, the fountains. The only ingredient nobody else can provide.
- ⚫ **The profile and the memory**: the Boulogne half marathon goal in November, my tone.

And the agent's output, published as-is on Strava. Excerpts (translated), with the source of each sentence:

> Could not get up early to run in the cool. So, run under the blazing sun at 25°C. Survival strategy: every fountain of the route became my best ally. *(🟡 my words, kept)*
>
> 📋 Campus Coach session: Long Run with active block 4x5min Tempo + 2min recovery *(🟣 the plan)*
> • Tempo 1-4: 920-926m in 5:00 at 5:23-5:26/km, HR 158-162bpm (5:26/km target validated!) *(🟠 the laps, figures computed in code)*
>
> My VO2max climbs to 53.45ml/kg/min (+1.1 vs 30-day average), the progression is there. *(🔴 Intervals.icu)*
>
> 🌡️ Enduraw analyzes the conditions: heat cost me 0'09"/km, wind 0'06"/km [...] *(🔵 Enduraw)*
>
> This capacity to hold the pace despite the heat is an asset for the Boulogne half in November. *(⚫ the profile)*
>
> Fun fact: at 25°C, my sweat rate reaches 0.9L/h according to Enduraw. Good thing I emptied all those fountains, otherwise I was finishing as a dried grape 💧 *(🟡 + 🔵, blended)*

Four silos plus my feelings, melted into one text that sounds like me. That is what "bringing the sources into one place" means concretely.

A word about Enduraw on the way, because the tool deserves its shout-out. Enduraw, contraction of endurance and raw (the raw data), is the performance laboratory of [Joseph Mestrallet](https://www2.u-trail.com/joseph-mestrallet-le-specialiste-des-data-analystes-de-lentrainement-trail/), an engineer based in Chamonix: he is the one who built the race strategies of Tom Evans and Ruth Croft, winners of the UTMB 2025, and his lab also serves amateurs like me. I am exactly his target, the tech guy with a passion for sport. I stay humble about what the data brings me at my ridiculously small scale: I play more than I optimize. But I am convinced, like him, that it has real value, that it is spreading across many sports, and that it will become a real level differentiator. And he has a line that resonates hard with this project: "Data can tell you anything if you do not know how to tell what is relevant." He says that about his sensors and his lactates. Me, I spent eight months learning it with LLMs.

