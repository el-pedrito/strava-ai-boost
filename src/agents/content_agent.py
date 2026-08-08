"""
Content Generation Agent for AgentCore Runtime

AgentCore-compatible agent with ALL prompts and tools embedded directly.
Uses embedded_prompts.py for complete prompt definitions.
Includes AgentCore Memory (LTM) integration for personalization.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import boto3

# Required AgentCore imports
from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from strands import Agent, tool
from strands.hooks import HookProvider, MessageAddedEvent

# Import embedded prompts
from embedded_prompts import CONTENT_GENERATION_PROMPT

# Initialize AgentCore app
app = BedrockAgentCoreApp()

# Configure logging level
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Also set root logger to INFO for more visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Environment variables
REGION = os.getenv("AWS_REGION", "eu-west-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")

# AgentCore Memory configuration
MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")

# Guardrail configuration (for input validation only)
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID")
GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "DRAFT")
GUARDRAIL_ENABLED = os.getenv("GUARDRAIL_ENABLED", "false").lower() == "true"

# Initialize Bedrock Runtime client for guardrail validation
bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION) if GUARDRAIL_ENABLED and GUARDRAIL_ID else None

# Initialize memory clients if memory is configured
memory_client = None
agentcore_client = None  # boto3 client for RetrieveMemoryRecords
if MEMORY_ID:
    try:
        memory_client = MemoryClient(region_name=REGION)
        agentcore_client = boto3.client('bedrock-agentcore', region_name=REGION)
        logger.info(f"AgentCore Memory clients initialized: {MEMORY_ID}")
    except Exception as e:
        logger.warning(f"Failed to initialize memory clients: {e}")
        memory_client = None
        agentcore_client = None


def retrieve_user_preferences(user_id: str, query: str, max_results: int = 10) -> List[Dict]:
    """
    Retrieve user preferences from AgentCore Memory using semantic search.

    Namespaces follow the unified '/strategies/{strategyId}/actors/{actorId}/'
    convention (docs/design/memory-improvements.md piste 5). We search the
    '/strategies/' prefix and keep only this user's records; the legacy
    '/strategy/StravaContentPreferences/...' namespace is tried second during
    the transition (records are migrated by configure_memory_strategy.py).
    """
    if not MEMORY_ID or not agentcore_client:
        return []

    try:
        for namespace, needs_user_filter in [
            ("/strategies/", True),
            (f"/strategy/StravaContentPreferences/actors/{user_id}/", False),
        ]:
            try:
                response = agentcore_client.retrieve_memory_records(
                    memoryId=MEMORY_ID,
                    namespace=namespace,
                    searchCriteria={
                        'searchQuery': query
                    },
                    maxResults=max_results
                )

                records = response.get('memoryRecordSummaries', [])
                if needs_user_filter:
                    records = [
                        r for r in records
                        if any(f"/actors/{user_id}/" in ns for ns in (r.get('namespaces') or []))
                    ]
                if records:
                    logger.info(f"Retrieved {len(records)} preference records (namespace={namespace})")
                    for i, record in enumerate(records[:5]):
                        content = record.get('content', {}).get('text', '')[:200]
                        score = record.get('score', 0)
                        logger.info(f"  Record {i+1} (score={score:.3f}): {content}...")
                    return records
            except Exception as ns_err:
                logger.debug(f"Namespace {namespace} failed: {ns_err}")
                continue

        logger.info("No preference records found in any namespace")
        return []

    except Exception as e:
        logger.warning(f"Failed to retrieve memory records: {e}")
        # Fallback: try get_last_k_turns for backward compatibility
        return _fallback_get_preferences(user_id)


def _fallback_get_preferences(user_id: str) -> List[Dict]:
    """Fallback to get_last_k_turns if RetrieveMemoryRecords is not available."""
    if not memory_client:
        return []

    try:
        # Try with user_id first, then fall back to "system" for old-format events
        for actor_id in [user_id, "system"]:
            turns = memory_client.get_last_k_turns(
                memory_id=MEMORY_ID,
                actor_id=actor_id,
                session_id="feedback_learning" if actor_id == "system" else None,
                k=3
            )
            if turns:
                logger.info(f"Fallback: loaded {len(turns)} turns from memory (actor={actor_id})")
                return [{'content': {'text': json.dumps(turns)}, '_fallback': True}]
        return []
    except Exception as e:
        logger.warning(f"Fallback memory read also failed: {e}")
        return []


class AgentCoreMemoryHook(HookProvider):
    """
    Hook for AgentCore Memory — saves generated content to STM for
    UserPreferenceStrategy to process alongside feedback diffs.
    """

    def on_message_added(self, event):
        """Save assistant responses to memory for context."""
        if not MEMORY_ID or not memory_client:
            return

        try:
            session_id = event.agent.state.get("session_id") or "default"
            actor_id = event.agent.state.get("actor_id") or "default_user"

            msg = event.agent.messages[-1]
            if msg.get("role") != "assistant":
                return

            content = str(msg.get("content", ""))
            if len(content) > 9000:
                content = content[:9000] + "... [truncated]"

            memory_client.create_event(
                memory_id=MEMORY_ID,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(content, msg["role"])]
            )
            logger.info(f"Saved response to memory for actor {actor_id}, session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to save to memory: {e}")

    def register_hooks(self, registry):
        registry.add_callback(MessageAddedEvent, self.on_message_added)


def validate_user_input_with_guardrail(text: str, field_name: str) -> tuple[str, bool]:
    """
    Validate user input (title/description) with Bedrock Guardrail
    
    This applies guardrail ONLY to user-provided content (Strava title/description)
    to detect prompt injection, without processing the entire prompt.
    
    Args:
        text: User input to validate (title or description)
        field_name: Name of the field for logging
        
    Returns:
        tuple: (validated_text, is_blocked)
            - validated_text: Original text or sanitized version
            - is_blocked: True if guardrail blocked the content
    """
    if not GUARDRAIL_ENABLED or not GUARDRAIL_ID or not bedrock_runtime:
        logger.debug(f"Guardrail validation skipped for {field_name} (not enabled)")
        return text, False
    
    if not text or len(text.strip()) == 0:
        return text, False
    
    try:
        logger.info(f"🛡️ Validating {field_name} with guardrail ({len(text)} chars)")
        logger.info(f"   Guardrail ID: {GUARDRAIL_ID}")
        logger.info(f"   Guardrail Version: {GUARDRAIL_VERSION}")
        logger.info(f"   Text preview: {text[:100]}...")
        
        # Call ApplyGuardrail API directly (not via model inference)
        logger.info(f"   Calling bedrock_runtime.apply_guardrail()...")
        response = bedrock_runtime.apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID,
            guardrailVersion=GUARDRAIL_VERSION,
            source="INPUT",
            content=[{
                "text": {
                    "text": text
                }
            }]
        )
        
        logger.info(f"   API Response received: {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
        
        # Check if content was blocked
        action = response.get('action', 'NONE')
        logger.info(f"   Guardrail action: {action}")
        
        if action == 'GUARDRAIL_INTERVENED':
            logger.warning(f"⚠️ Guardrail blocked {field_name}: {text[:100]}...")
            
            # Log assessment details
            assessments = response.get('assessments', [])
            logger.warning(f"   Assessments count: {len(assessments)}")
            for assessment in assessments:
                content_policy = assessment.get('contentPolicy', {})
                if content_policy:
                    filters = content_policy.get('filters', [])
                    for filter_item in filters:
                        filter_type = filter_item.get('type')
                        confidence = filter_item.get('confidence')
                        action = filter_item.get('action')
                        logger.warning(f"   Filter: {filter_type}, Confidence: {confidence}, Action: {action}")
            
            # Return sanitized version
            sanitized = f"[Contenu bloqué - {field_name}]"
            return sanitized, True
        
        logger.info(f"✅ Guardrail passed for {field_name}")
        logger.info(f"   Usage: {response.get('usage', {})}")
        return text, False
        
    except Exception as e:
        logger.error(f"❌ Guardrail validation failed for {field_name}: {e}")
        logger.error(f"   Exception type: {type(e).__name__}")
        logger.error(f"   Exception details: {str(e)}")
        # On error, allow content through (fail open for availability)
        return text, False


AGE_CONTEXT = {
    '18-25': {
        'expressions': ['Mode boost active', 'Performance unlocked', 'Level up', 'Data en temps reel', 'Algo optimise'],
        'tone': 'Energetic, ambitious, data-driven',
        'example': "Cette perf' merite un post ! Mes stats parlent d'elles-memes",
    },
    '26-35': {
        'expressions': ['Optimiser le temps', 'ROI de l\'entrainement', 'Efficacite maximale', 'Dashboard perso', 'Metrics optimisees'],
        'tone': 'Efficient, strategic, results-focused',
        'example': 'Session efficace entre deux meetings - j\'ai bien investi mon temps !',
    },
    '36-45': {
        'expressions': ['Prendre soin de soi', 'Montrer l\'exemple', 'Equilibre vie pro/perso', 'Investissement sante'],
        'tone': 'Balanced, wise, sustainable',
        'example': 'Ces sorties regulieres, c\'est l\'investissement sante qui compte',
    },
    '46-55': {
        'expressions': ['L\'experience parle', 'La regularite paye', 'Sagesse du corps'],
        'tone': 'Experienced, measured, encouraging',
        'example': 'Apres toutes ces annees, on sait ecouter son corps - sortie parfaite !',
    },
    '56-65': {
        'expressions': ['Le plaisir avant tout', 'Profiter de chaque instant', 'La forme c\'est la sante'],
        'tone': 'Positive, health-focused, community-oriented',
        'example': 'Ces sorties, c\'est le bonheur simple - garder la forme et profiter !',
    },
    '65+': {
        'expressions': ['Le plaisir avant tout', 'Profiter de chaque instant', 'La forme c\'est la sante'],
        'tone': 'Positive, health-focused, community-oriented',
        'example': 'Ces sorties, c\'est le bonheur simple - garder la forme et profiter !',
    },
}

INTEREST_EXPRESSIONS = {
    'technology': ['Les donnees parlent d\'elles-memes', 'Systeme bien calibre', 'Optimiser les parametres', 'Algorithme parfaitement execute', 'Debug des sensations reussi'],
    'music': ['Trouver son rythme', 'En harmonie avec le corps', 'Tempo parfait', 'Cette cadence groove', 'Comme une playlist bien caliee - crescendo maitrise', 'Les jambes jouent la bonne partition'],
    'travel': ['Explorer de nouveaux horizons', 'Chaque km est une decouverte', 'Voyage interieur', 'Comme un road trip a l\'echelle du quartier', 'Depaysement garanti meme sur les chemins connus'],
    'food': ['Bien nourrir l\'effort', 'Digerer les kilometres', 'Carburant optimal', 'Recette parfaitement dosee', 'Un effort a savourer', 'Ingredients du jour: regulariete et constance'],
    'nature': ['Profiter du paysage', 'S\'adapter aux elements', 'Respirer l\'air frais', 'En osmose avec le terrain', 'La nature comme terrain de jeu'],
    'photography': ['Capturer l\'instant', 'Belle image de progression', 'Moment a immortaliser', 'Un snapshot de forme parfait', 'Cadrage ideal sur cette performance'],
    'family': ['Equilibrer les priorites', 'Montrer l\'exemple', 'Prendre soin de soi pour les autres', 'Du temps bien investi pour soi'],
    'competition': ['Se depasser', 'Viser plus haut', 'Battre ses records', 'Challenger ses limites', 'Mode guerrier active', 'La course est lancee'],
}

SPORT_APPROACH_EXAMPLES = {
    'performance & competition': {
        'focus': 'Metriques precises, comparaisons, objectifs, elements competitifs',
        'narrative': 'Race narrative — tactical decisions, splits analysis, competitive mindset, next challenge',
        'example': 'Mission accomplie ! J\'ai atomise mon record sur 5K (21:45) avec un negatif split de champion (4:28->4:15/km). Mode competition active, je suis pret pour la prochaine course !',
    },
    'health & wellness': {
        'focus': 'Bien-etre, stress relief, niveaux d\'energie, sante globale',
        'narrative': 'Mindfulness journey — body sensations, breathing, inner peace, recovery quality',
        'example': 'Sortie bien-etre parfaite ! 90 minutes d\'endurance fondamentale (allure tres facile) avec un ressenti de reve. Mon corps ronronne, mon esprit se libere.',
    },
    'social & fun': {
        'focus': 'Plaisir, aspects sociaux, communaute, experiences partagees',
        'narrative': 'Shared experience — group energy, fun moments, community connection',
        'example': 'Sortie de groupe qui fait du bien ! 10K en mode convivial avec une belle regularite. J\'adore ces moments partages, ca vaut tous les chronos du monde.',
    },
    'personal challenge': {
        'focus': 'Amelioration personnelle, depasser les obstacles, croissance',
        'narrative': 'Hero\'s journey — overcoming doubt, pushing through discomfort, personal growth',
        'example': 'Defi releve ! J\'ai fait plus long que d\'habitude, je repousse mes limites. Chaque km de plus est une victoire personnelle.',
    },
    'stress relief': {
        'focus': 'Benefices mentaux, relaxation, echappatoire du quotidien',
        'narrative': 'Escape narrative — leaving stress behind, decompression, mental clarity',
        'example': 'Sortie decompression parfaite. Mon rythme regulier, l\'air frais, mon esprit qui se vide - ma meilleure therapie.',
    },
    'weight management': {
        'focus': 'Regularite, habitudes saines, progres durables',
        'narrative': 'Progress story — consistency, building habits, incremental wins',
        'example': 'Encore une sortie de faite ! Ma regularite paye, chaque km compte dans ma progression.',
    },
}


def build_profile_context(user_profile: Optional[Dict[str, Any]]) -> str:
    """Build profile-specific context with examples for the system prompt.

    Only includes the sections matching the current user's profile,
    instead of the full catalog of all age/interest/approach combinations.
    """
    if not user_profile:
        return ""

    sections = []

    # Age-specific expressions and example
    age = user_profile.get('age_range', '')
    age_data = AGE_CONTEXT.get(age)
    if age_data:
        sections.append(
            f"### Age Context ({age})\n"
            f"Tone: {age_data['tone']}\n"
            f"Suggested expressions: {', '.join(age_data['expressions'][:4])}\n"
            f"Example: \"{age_data['example']}\"\n"
            f"Use max 1 age-appropriate reference per activity. Keep it subtle."
        )

    # Interest expressions
    interests = user_profile.get('interests', [])
    if interests:
        lines = []
        for interest in interests[:5]:
            exprs = INTEREST_EXPRESSIONS.get(interest.lower(), [])
            if exprs:
                lines.append(f"- {interest}: {', '.join(exprs[:3])}")
        if lines:
            sections.append(
                "### Interest References\n"
                "IMPORTANT: Include at least 1 interest-inspired expression or metaphor in every activity description. "
                "Weave them naturally into the narrative (e.g. as a metaphor, analogy, or closing remark). "
                "Pick the interest that fits best with the activity context. "
                "Don't label them — integrate seamlessly.\n"
                + "\n".join(lines)
            )

    # Sport approach example
    approach = user_profile.get('sport_approach', '')
    approach_data = SPORT_APPROACH_EXAMPLES.get(approach)
    if approach_data:
        sections.append(
            f"### Sport Approach: {approach}\n"
            f"Focus: {approach_data['focus']}\n"
            f"Narrative style: {approach_data['narrative']}\n"
            f"Example: \"{approach_data['example']}\""
        )

    if not sections:
        return ""

    return "\n\n## Profile Context (for this user)\n\n" + "\n\n".join(sections)


def build_preference_instructions(user_profile: Optional[Dict[str, Any]]) -> str:
    """Build targeted style instructions from user preferences instead of raw JSON."""
    if not user_profile:
        return "No user profile provided"

    prefs = user_profile.get('content_preferences', {})
    instructions = []

    # Tone
    tone = prefs.get('tone', 'motivational & energetic')
    tone_map = {
        'technical & analytical': 'Data-driven language, precise metrics, scientific terms. Include lap-by-lap analysis when laps available.',
        'motivational & energetic': 'Exclamation marks, action verbs, uplifting and celebratory language.',
        'casual & friendly': 'Conversational tone, contractions, friendly and accessible language.',
        'humorous & fun': 'Light humor, playful metaphors, creative wordplay. Keep it fun.',
        'authentic & personal': 'Genuine insights, personal perspective, introspective tone.',
    }
    instructions.append(f"- TONE: {tone_map.get(tone, tone)}")

    # Emoji limits
    emoji = prefs.get('emoji_usage', 'moderate')
    emoji_limits = {'none': 0, 'minimal': 2, 'moderate': 5, 'enthusiastic': 10}
    max_emoji = emoji_limits.get(emoji, 5)
    if max_emoji == 0:
        instructions.append("- EMOJIS: ZERO emojis. No emoji characters at all.")
    else:
        instructions.append(
            f"- EMOJIS: STRICT LIMIT: MAXIMUM {max_emoji} emojis TOTAL, title included. "
            "Count every emoji in title + description before answering; if over the limit, remove the extras."
        )

    # Content length
    length = prefs.get('length', 'medium')
    length_limits = {'short': 300, 'medium': 800, 'detailed': 1500}
    if length in length_limits:
        instructions.append(f"- LENGTH: MAX {length_limits[length]} characters ({length}). Includes signature.")

    # Language
    lang = prefs.get('language', 'french')
    instructions.append(f"- LANGUAGE: Generate ALL content (title + description) in {lang}.")
    if lang != 'french':
        instructions.append(f"  OVERRIDE: Do NOT use French. Write everything in {lang.upper()}.")

    # Sport approach
    approach = user_profile.get('sport_approach', 'health & wellness')
    approach_map = {
        'health & wellness': 'Emphasize feeling good, stress relief, energy levels, overall wellbeing.',
        'performance & competition': 'Emphasize metrics, improvements, goals, competitive elements.',
        'social & fun': 'Highlight enjoyment, social aspects, community, shared experiences.',
        'personal challenge': 'Focus on self-improvement, overcoming obstacles, personal growth.',
        'stress relief': 'Emphasize mental benefits, relaxation, escape from daily pressures.',
        'weight management': 'Focus on consistency, healthy habits, sustainable progress.',
    }
    instructions.append(f"- FOCUS: {approach_map.get(approach, approach)}")

    # Technical detail
    technical = prefs.get('technical_detail', 'intermediate')
    technical_map = {
        'basic': 'Key metrics only (distance, duration, pace). No deep analysis.',
        'intermediate': 'Include key metrics with brief insights. Use lap data for intervals.',
        'advanced': 'Full lap-by-lap analysis. Include HR zones, pace variations, physiological insights.',
    }
    instructions.append(f"- TECHNICAL: {technical_map.get(technical, technical)}")

    # Age context and interests are injected via build_profile_context() in the system prompt
    # with richer expressions and examples — no need to duplicate here.

    return "STYLE INSTRUCTIONS (from user preferences):\n" + "\n".join(instructions)


def _build_intervals_icu_context(intervals_icu_data: dict | None) -> str:
    """Build a compact fitness/fatigue context string from Intervals.icu data."""
    if not intervals_icu_data:
        return ""

    lines = [
        "FORME & RÉCUPÉRATION (Intervals.icu):",
        "Légende: CTL = charge chronique (fitness long terme, 0-20 débutant, 40-60 intermédiaire, 80+ élite)",
        "         ATL = charge aiguë (fatigue récente, élevée = grosse semaine)",
        "         Form = CTL-ATL (>5 frais, 0 à -10 normal, <-20 très fatigué — explique les sensations lourdes)",
        "         Ramp = vitesse de montée en charge (>5 attention surcharge, <3 progression douce)",
        "         Decoupling = dérive cardiaque (<3% excellent aérobie, >5% fatigue ou manque d'endurance)",
        "         VO2max = capacité aérobie estimée (30-40 moyen, 45-55 bon, 60+ excellent)",
        "         RestingHR = FC repos (plus bas = meilleure condition, hausse = fatigue/stress)",
    ]
    fitness = intervals_icu_data.get('fitness', {})
    if fitness:
        parts = []
        if fitness.get('ctl') is not None:
            parts.append(f"CTL={fitness['ctl']:.0f}")
        if fitness.get('atl') is not None:
            parts.append(f"ATL={fitness['atl']:.0f}")
        if fitness.get('form') is not None:
            form = fitness['form']
            label = "frais" if form > 5 else "neutre" if form > -5 else "fatigué" if form > -20 else "très fatigué"
            parts.append(f"Form={form:.0f} ({label})")
        if fitness.get('ramp_rate') is not None:
            parts.append(f"Ramp={fitness['ramp_rate']:.1f}")
        if parts:
            lines.append(f"📊 {' | '.join(parts)}")

        if fitness.get('hrv') is not None:
            lines.append(f"❤️ HRV: {fitness['hrv']}ms")
        if fitness.get('resting_hr') is not None:
            lines.append(f"💓 FC repos: {fitness['resting_hr']} bpm")
        if fitness.get('vo2max') is not None:
            lines.append(f"🫁 VO2max: {fitness['vo2max']:.1f} ml/kg/min")

    sleep = intervals_icu_data.get('sleep', {})
    if sleep:
        sleep_parts = []
        duration = sleep.get('duration_seconds')
        if duration is not None:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            sleep_parts.append(f"{hours}h{minutes:02d}")
        quality = sleep.get('quality')
        if quality is not None:
            sleep_parts.append(f"qualité {quality}/5")
        if sleep_parts:
            lines.append(f"😴 Sommeil: {' — '.join(sleep_parts)}")

    decoupling = intervals_icu_data.get('decoupling')
    if decoupling is not None:
        label = "excellent" if decoupling < 3 else "bon" if decoupling < 5 else "dérive notable"
        lines.append(f"🔄 Decoupling: {decoupling}% ({label})")

    # Trends (30-day evolution)
    trends = intervals_icu_data.get('trends', {})
    if trends:
        lines.append("")
        lines.append("TENDANCES (évolution sur 30 jours) :")
        trend_labels = {
            'vo2max': ('VO2max', 'ml/kg/min'),
            'hrv': ('HRV', 'ms'),
            'resting_hr': ('FC repos', 'bpm'),
            'ctl': ('CTL', ''),
            'sleep_duration': ('Sommeil', ''),
            'sleep_quality': ('Qualité sommeil', '/5'),
        }
        direction_arrows = {'up': '↗️', 'down': '↘️', 'stable': '→'}
        for key, (label, unit) in trend_labels.items():
            t = trends.get(key)
            if not t:
                continue
            arrow = direction_arrows.get(t['direction'], '→')
            delta_str = ""
            if t.get('delta_7d') is not None:
                sign = '+' if t['delta_7d'] > 0 else ''
                if key == 'sleep_duration':
                    delta_min = int(t['delta_7d'] / 60)
                    delta_str = f" ({sign}{delta_min}min vs sem. précédente)"
                else:
                    delta_str = f" ({sign}{t['delta_7d']}{unit} vs sem. précédente)"
            if key == 'sleep_duration':
                current_h = int(t['current'] // 3600)
                current_m = int((t['current'] % 3600) // 60)
                avg_h = int(t['avg_30d'] // 3600)
                avg_m = int((t['avg_30d'] % 3600) // 60)
                lines.append(f"  {arrow} {label}: {current_h}h{current_m:02d} moy. 30j (⚠️ PAS la nuit avant cette activité), moy. 30j: {avg_h}h{avg_m:02d}{delta_str}")
            else:
                lines.append(f"  {arrow} {label}: {t['current']}{unit} aujourd'hui, moy. 30j: {t['avg_30d']}{unit}{delta_str}")

    if len(lines) <= 6:
        return ""

    lines.append("→ Intègre ces métriques dans le récit : mentionne le chiffre ET son interprétation (ex: 'Form à -24 = grosse fatigue accumulée', 'decoupling 2.5% = aérobie solide', 'VO2max à 52 = bon niveau aérobie'). Pas de listing sec, tisse-les dans le narratif.")
    lines.append("→ CORRÉLATIONS : croise ces données avec la performance. Exemples : Form très négatif + séance dure = 'normal avec cette fatigue accumulée', HRV bas + FC élevée = 'le corps n'avait pas récupéré'. Toujours expliquer le POURQUOI.")
    lines.append("→ TENDANCES : si une tendance est notable (hausse/baisse), mentionne-la. Ne mentionne que les tendances significatives, pas les métriques stables.")
    lines.append("⚠️ RÈGLE ABSOLUE : Ne JAMAIS inventer d'heure de réveil, de coucher, ou de durée de sommeil. Si aucune ligne 😴 Sommeil n'apparaît ci-dessus, la donnée n'est PAS disponible pour cette activité — ne l'invente pas. Les données 'Sommeil' dans TENDANCES sont des moyennes 30 jours, PAS la nuit précédant cette activité.")
    return "\n".join(lines) + "\n"


def _format_laps_for_prompt(laps: list) -> str:
    """Format device-recorded laps into a readable string for the LLM prompt.

    Each lap contains pace, distance, time, HR and cadence as recorded by the
    athlete's watch (auto-lap every km or manual lap button for intervals).
    """
    if not laps:
        return "No laps recorded"

    lines = [f"- Laps: {len(laps)} lap(s) recorded by device"]
    for lap in laps:
        idx = lap.get('lap_index', 0)
        name = lap.get('name', f'Lap {idx}')
        distance_m = lap.get('distance', 0)
        moving_time = lap.get('moving_time', 0)
        elapsed_time = lap.get('elapsed_time', 0)
        avg_speed = lap.get('average_speed', 0)
        max_speed = lap.get('max_speed', 0)
        avg_hr = lap.get('average_heartrate')
        max_hr = lap.get('max_heartrate')
        avg_cadence = lap.get('average_cadence')
        pace_zone = lap.get('pace_zone')
        elevation = lap.get('total_elevation_gain', 0)

        # Format pace from m/s
        if avg_speed > 0:
            pace_total_s = 1000 / avg_speed
            pace_str = f"{int(pace_total_s // 60)}:{int(pace_total_s % 60):02d}/km"
        else:
            pace_str = "N/A"

        if max_speed > 0:
            max_pace_s = 1000 / max_speed
            max_pace_str = f"{int(max_pace_s // 60)}:{int(max_pace_s % 60):02d}/km"
        else:
            max_pace_str = "N/A"

        time_str = f"{moving_time // 60}:{moving_time % 60:02d}"

        line = f"  {name}: {distance_m:.0f}m in {time_str} — pace {pace_str} (max {max_pace_str})"
        if avg_hr:
            line += f", HR {avg_hr:.0f}"
            if max_hr:
                line += f"/{max_hr:.0f}"
            line += " bpm"
        if avg_cadence:
            line += f", cadence {avg_cadence:.0f} spm"
        if pace_zone:
            line += f", zone {pace_zone}"
        if elevation and elevation > 0:
            line += f", D+ {elevation:.0f}m"

        lines.append(line)

    return "\n".join(lines)


def resolve_adaptive_content_length(laps, duration_min, user_profile):
    """
    Resolve 'adaptive' content_length to a concrete value.

    Rules:
    - If intervals detected (>=5 laps with significant pace variation) + technical profile -> detailed (1500)
    - If long activity (>60min) or technical_detail: advanced -> detailed (1500)
    - If short activity (<30min) without intervals -> medium (800)
    - Otherwise -> medium (800)
    """
    content_prefs = user_profile.get('content_preferences', {}) if user_profile else {}
    technical_detail = content_prefs.get('technical_detail', 'basic')
    content_tone = content_prefs.get('tone', '')

    # Check for interval structure from laps
    has_intervals = False
    if laps and len(laps) >= 5:
        paces_s = []
        for lap in laps:
            avg_speed = lap.get('average_speed', 0)
            if avg_speed > 0:
                paces_s.append(1000 / avg_speed)  # seconds per km

        if len(paces_s) >= 4:
            pace_variation = max(paces_s) - min(paces_s)
            has_intervals = pace_variation > 30  # >30 seconds/km variation

    is_technical = technical_detail == 'advanced' or 'technical' in content_tone.lower()

    # Resolve
    if has_intervals and is_technical:
        return 'detailed', 1500
    if duration_min > 60 or technical_detail == 'advanced':
        return 'detailed', 1500
    if duration_min < 30 and not has_intervals:
        return 'medium', 800

    return 'medium', 800


@app.entrypoint
def invoke(payload, context=None):
    """
    AgentCore entrypoint for content generation operations
    
    Args:
        payload: Input data containing activity data and generation parameters
        context: AgentCore context (optional)
        
    Returns:
        Generated content with metadata and analysis
    """
    try:
        # Extract parameters from payload first
        activity_data = payload.get('activity_data', {})
        activity_id = activity_data.get('id', 'unknown')
        user_id = payload.get('user_id', 'default_user')
        
        # Use the embedded complete prompt
        # P1.2: Split into cached static part + dynamic part for prompt caching.
        # The static CONTENT_GENERATION_PROMPT is ~35KB (~9K tokens) — well above
        # the 1024-token minimum. Dynamic parts (memory feedback + profile) are
        # appended after the cache point so cache hits still work.
        static_system_prompt = CONTENT_GENERATION_PROMPT
        dynamic_system_prompt = ""

        # Load user preferences from AgentCore Memory via semantic search
        feedback_instructions = ""
        if MEMORY_ID:
            try:
                # Build a contextual query based on current activity
                sport_type = activity_data.get('sport_type', 'Run')
                distance_km = activity_data.get('distance', 0) / 1000
                query = f"content preferences for {sport_type} activity {distance_km:.0f}km"

                # Retrieve preferences via semantic search (UserPreferenceStrategy records)
                records = retrieve_user_preferences(
                    user_id=str(user_id),
                    query=query,
                    max_results=10
                )

                if records:
                    feedback_instructions = "\n\n## FEEDBACK UTILISATEUR (Préférences Apprises)\n\n"
                    feedback_instructions += "**Ces préférences ont été extraites automatiquement depuis tes modifications. RESPECTE-LES.**\n"
                    feedback_instructions += "**En cas de conflit avec les STYLE INSTRUCTIONS du user prompt, les STYLE INSTRUCTIONS ont priorité (choix explicite de l'utilisateur).**\n\n"

                    for record in records:
                        content = record.get('content', {})
                        text = content.get('text', '') if isinstance(content, dict) else str(content)
                        if text:
                            feedback_instructions += f"- {text}\n"

                    logger.info(f"Loaded {len(records)} preference records from AgentCore Memory")
                else:
                    logger.info("No user preferences found in memory yet")
            except Exception as e:
                logger.warning(f"Failed to load user preferences from memory: {e}")

        # Append feedback instructions if available
        if feedback_instructions:
            dynamic_system_prompt += feedback_instructions

        # Inject profile-specific context (age, interests, sport approach examples)
        user_profile = payload.get('user_profile')
        profile_context = build_profile_context(user_profile)
        if profile_context:
            dynamic_system_prompt += profile_context

        # P1.2: Build SystemContentBlock array with cache point after static prompt.
        # Bedrock min cache threshold ≈ 1024 tokens (~4KB). Fall back to string if shorter.
        from strands.types.content import SystemContentBlock
        if len(static_system_prompt) >= 4096:
            system_prompt = [SystemContentBlock(text=static_system_prompt),
                             SystemContentBlock(cachePoint={"type": "default"})]
            if dynamic_system_prompt:
                system_prompt.append(SystemContentBlock(text=dynamic_system_prompt))
        else:
            system_prompt = static_system_prompt + dynamic_system_prompt

        # Create Strands agent WITHOUT guardrails on the model
        # Guardrails are applied manually on user inputs only (title/description)
        from strands.models import BedrockModel
        
        logger.info(f"Creating agent without model-level guardrails (input validation done separately)")
        agent = Agent(
            model=MODEL_ID,  # No guardrails on model - we validate inputs manually
            system_prompt=system_prompt,
            hooks=[],  # Disabled: AgentCoreMemoryHook() - Memory writes only after feedback validation
            state={
                "session_id": f"activity-{activity_id}",
                "actor_id": str(user_id)
            }
        )
        
        if MEMORY_ID:
            logger.info(f"Agent created with AgentCore Memory (LTM) READ-ONLY for user {user_id}, activity {activity_id}")
            logger.info(f"⚠️ Memory writes disabled - will be written after feedback validation")
        else:
            logger.info(f"Agent created without memory (MEMORY_ID not configured)")
        
        # Define callback handler for model reasoning logs
        def reasoning_callback_handler(**kwargs):
            """Log model reasoning and tool usage"""
            if kwargs.get("init_event_loop"):
                logger.info("🔄 Agent event loop initialized")
            elif kwargs.get("start_event_loop"):
                logger.info("▶️ Agent event loop cycle starting")
            elif kwargs.get("reasoning"):
                # Log reasoning events (extended thinking from models like Claude)
                reasoning_text = kwargs.get("reasoningText", "")
                if reasoning_text:
                    logger.info(f"🧠 Model reasoning: {reasoning_text[:500]}...")
                reasoning_sig = kwargs.get("reasoning_signature")
                if reasoning_sig:
                    logger.info(f"   Reasoning signature: {reasoning_sig}")
            elif "current_tool_use" in kwargs and kwargs["current_tool_use"].get("name"):
                tool_name = kwargs["current_tool_use"]["name"]
                tool_input = kwargs["current_tool_use"].get("input", {})
                logger.info(f"🔧 Agent using tool: {tool_name}")
                logger.info(f"   Tool input: {str(tool_input)[:200]}...")
            elif "message" in kwargs:
                role = kwargs["message"].get("role")
                content_preview = str(kwargs["message"].get("content", ""))[:200]
                logger.info(f"📬 Message created: {role} ({len(str(kwargs['message'].get('content', '')))} chars)")
                logger.info(f"   Preview: {content_preview}...")
            elif kwargs.get("complete"):
                logger.info("✅ Agent event loop cycle completed")
            elif kwargs.get("force_stop"):
                logger.warning(f"🛑 Agent force-stopped: {kwargs.get('force_stop_reason', 'unknown')}")
        
        # Add callback handler to agent for reasoning logs
        agent.callback_handler = reasoning_callback_handler
        
        # Extract remaining parameters from payload (user_profile already extracted above)
        active_modules = payload.get('active_modules', [])
        campus_coach_session = payload.get('campus_coach_session')
        enduraw_data = payload.get('enduraw_data')
        intervals_icu_data = payload.get('intervals_icu_data')
        laps_data = payload.get('laps_data')
        athlete_stats = payload.get('athlete_stats', {})
        athlete_profile = payload.get('athlete_profile', {})
        # Log Campus Coach data details
        if campus_coach_session:
            if isinstance(campus_coach_session, list):
                logger.info(f"🎯 Campus Coach: Received {len(campus_coach_session)} sessions for matching")
                for i, session in enumerate(campus_coach_session[:3]):  # Log first 3 sessions
                    logger.info(f"   Session {i+1}: {session.get('title', 'Unknown')} - {session.get('targetedMetrics', {}).get('target_distance_km', 0)}km")
            else:
                logger.info(f"🎯 Campus Coach: Received single session - {campus_coach_session.get('title', 'Unknown')}")
        else:
            logger.info("ℹ️ Campus Coach: No sessions provided")
        
        # Log detailed invocation info
        logger.info(f"=== Content Generation Started ===")
        logger.info(f"Activity ID: {activity_id}")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Activity Type: {activity_data.get('type', 'unknown')}")
        logger.info(f"Distance: {float(activity_data.get('distance', 0))/1000:.2f} km")
        logger.info(f"Speed: Avg {float(activity_data.get('average_speed', 0))*3.6:.1f} km/h, Max {float(activity_data.get('max_speed', 0))*3.6:.1f} km/h")
        if activity_data.get('average_cadence'):
            logger.info(f"Cadence: Avg {activity_data.get('average_cadence'):.0f} spm")
        if activity_data.get('average_watts'):
            logger.info(f"Power: Avg {activity_data.get('average_watts'):.0f}W, Weighted {activity_data.get('weighted_average_watts', 0):.0f}W")
        if activity_data.get('calories'):
            logger.info(f"Calories: {activity_data.get('calories'):.0f} kcal")
        if activity_data.get('suffer_score'):
            logger.info(f"Suffer Score: {activity_data.get('suffer_score'):.0f}/100")
        logger.info(f"Active Modules: {[m.get('name') for m in active_modules]}")
        logger.info(f"Campus Coach Session: {'Yes' if campus_coach_session else 'No'}")
        logger.info(f"Enduraw Data: {'Yes' if enduraw_data else 'No'}")
        logger.info(f"Laps Data: {'Yes (' + str(len(laps_data)) + ' laps)' if laps_data else 'No'}")
        logger.info(f"Workout Classification: {(payload.get('workout_classification') or {}).get('type', 'unknown')}")
        logger.info(f"Memory Enabled: {MEMORY_ID is not None}")
        logger.info(f"Achievements: {activity_data.get('achievement_count', 0)}, PRs: {activity_data.get('pr_count', 0)}, Kudos: {activity_data.get('kudos_count', 0)}")
        logger.info(f"Segment Efforts: {len(activity_data.get('segment_efforts', []))}, Best Efforts: {len(activity_data.get('best_efforts', []))}")
        
        # Log athlete stats if available
        if athlete_stats:
            ytd_run = athlete_stats.get('ytd_run_totals', {})
            if ytd_run and ytd_run.get('distance'):
                logger.info(f"Athlete YTD: {ytd_run.get('distance', 0)/1000:.0f} km in {ytd_run.get('count', 0)} runs")
        else:
            logger.info(f"Athlete Stats: Not available")
        
        # Log user preferences if available
        if user_profile:
            logger.info(f"=== User Preferences ===")
            content_prefs = user_profile.get('content_preferences', {})
            logger.info(f"Content Tone: {content_prefs.get('tone') or 'not set'}")
            logger.info(f"Content Length: {content_prefs.get('length') or 'not set'}")
            logger.info(f"Technical Detail: {content_prefs.get('technical_detail') or 'not set'}")
            logger.info(f"Emoji Usage: {content_prefs.get('emoji_usage') or 'not set'}")
            logger.info(f"Language: {content_prefs.get('language') or 'not set'}")
            logger.info(f"Sport Approach: {user_profile.get('sport_approach') or 'not set'}")
            logger.info(f"Interests: {user_profile.get('interests') or []}")
            logger.info(f"Age Range: {user_profile.get('age_range') or 'not set'}")
        else:
            logger.info(f"User Preferences: Not configured")
        
        # Validate required data
        if not activity_data:
            logger.error("Missing activity_data in payload")
            return {
                "error": "activity_data is required for content generation",
                "user_id": user_id
            }
        
        # CRITICAL: Validate user-provided content with guardrail BEFORE including in prompt
        # This prevents prompt injection without processing the entire 230K+ char prompt
        original_title = activity_data.get('name', 'Untitled')
        original_description = activity_data.get('description', 'No description provided')
        
        validated_title, title_blocked = validate_user_input_with_guardrail(original_title, "title")
        validated_description, desc_blocked = validate_user_input_with_guardrail(original_description, "description")
        
        if title_blocked or desc_blocked:
            logger.warning(f"🛡️ Guardrail intervention detected:")
            logger.warning(f"   Title blocked: {title_blocked}")
            logger.warning(f"   Description blocked: {desc_blocked}")
            
            # Return safe fallback content
            return {
                "response": json.dumps({
                    "title": f"{activity_data.get('type', 'Activity')} - {activity_data.get('distance', 0)/1000:.1f}km",
                    "description": f"Activité de {activity_data.get('moving_time', 0)//60} minutes.\n\n@Generated by Strava AI Boost (Safe Mode)",
                    "confidence": 0.5,
                    "guardrail_blocked": True,
                    "blocked_fields": {
                        "title": title_blocked,
                        "description": desc_blocked
                    }
                }),
                "user_id": user_id,
                "activity_id": activity_id,
                "guardrail_intervention": True
            }
        
        # Generate prompt for content creation with ALL user preferences
        activity_type = activity_data.get('sport_type', activity_data.get('type', 'Activity'))
        distance = float(activity_data.get('distance', 0)) / 1000  # km
        duration = float(activity_data.get('moving_time', 0)) / 60  # minutes
        elapsed_time = float(activity_data.get('elapsed_time', 0)) / 60  # minutes
        elevation = float(activity_data.get('total_elevation_gain', 0))
        avg_hr = activity_data.get('average_heartrate')
        max_hr = activity_data.get('max_heartrate')
        
        # Speed metrics
        avg_speed = float(activity_data.get('average_speed') or 0) * 3.6  # m/s to km/h
        max_speed = float(activity_data.get('max_speed') or 0) * 3.6  # m/s to km/h

        def _opt_num(key: str):
            """Optional numeric field: coerce to float, None if absent/invalid.

            DynamoDB/JSON round-trips can turn numbers into strings (see the
            2026-07-15 manual/indoor crash); the prompt f-strings use :.0f
            which raises on str/None.
            """
            value = activity_data.get(key)
            if value in (None, ''):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        # Cadence metrics
        avg_cadence = _opt_num('average_cadence')
        max_cadence = _opt_num('max_cadence')

        # Power metrics
        avg_watts = _opt_num('average_watts')
        max_watts = _opt_num('max_watts')
        weighted_avg_watts = _opt_num('weighted_average_watts')
        device_watts = activity_data.get('device_watts', False)

        # Performance metrics
        calories = _opt_num('calories')
        suffer_score = _opt_num('suffer_score')
        workout_type = activity_data.get('workout_type')
        workout_type_names = {0: 'Default', 1: 'Race', 2: 'Long Run', 3: 'Workout', 10: 'Tempo', 11: 'Intervals', 12: 'Recovery'}
        workout_type_str = workout_type_names.get(workout_type, 'Unknown') if workout_type is not None else None
        
        # Extract athlete profile from payload
        athlete_profile = payload.get('athlete_profile', {})

        # Build athlete context (FTP, weight, power-to-weight ratio)
        athlete_context = ""
        ftp = athlete_profile.get('ftp')
        weight = athlete_profile.get('weight')
        if ftp and weight and avg_watts:
            watts_per_kg = avg_watts / weight
            ftp_percentage = (avg_watts / ftp) * 100 if ftp > 0 else 0
            athlete_context += f"💪 Power-to-Weight: {watts_per_kg:.1f} W/kg (FTP: {ftp}W, Weight: {weight}kg)\n"
            athlete_context += f"📊 Effort Level: {ftp_percentage:.0f}% of FTP\n"

        # Splits and Laps
        splits_metric = activity_data.get('splits_metric', [])
        splits_standard = activity_data.get('splits_standard', [])
        laps = laps_data if laps_data else activity_data.get('laps', [])
        
        # Build data payload for agent (system_prompt already has all instructions)
        user_profile_str = build_preference_instructions(user_profile)
        active_modules_str = ', '.join([m.get('name', 'unknown') for m in active_modules]) if active_modules else 'No active modules'
        campus_session_str = json.dumps(campus_coach_session, indent=2) if campus_coach_session else 'No Campus Coach session matched'
        enduraw_str = json.dumps(enduraw_data, indent=2) if enduraw_data else 'No Enduraw data available'
        
        # Extract location and weather data (always used when available)
        location_city = activity_data.get('location_city', '')
        location_country = activity_data.get('location_country', '')
        avg_temp = activity_data.get('average_temp')
        fetched_weather = activity_data.get('fetched_weather', {})  # From Open-Meteo via activity_fetcher
        
        location_context = ""
        if location_city or location_country:
            location_parts = [p for p in [location_city, location_country] if p]
            location_context = f"Location: {', '.join(location_parts)}"
        if avg_temp is not None:
            location_context += f"\nTemperature (Strava): {avg_temp}°C"
        if fetched_weather:
            location_context += f"\nWeather (Open-Meteo): Temp {fetched_weather.get('temperature')}°C, Wind {fetched_weather.get('wind_speed')}km/h, Humidity {fetched_weather.get('humidity')}%"
        if not location_context:
            location_context = "No location data available"
        
        # Extract achievements and performance highlights
        achievement_count = activity_data.get('achievement_count', 0)
        pr_count = activity_data.get('pr_count', 0)
        segment_efforts = activity_data.get('segment_efforts', [])
        best_efforts = activity_data.get('best_efforts', [])
        
        # Build achievements context
        achievements_context = ""
        if achievement_count > 0:
            achievements_context += f"🏆 {achievement_count} achievement(s) unlocked!\n"
        if pr_count > 0:
            achievements_context += f"⭐ {pr_count} personal record(s) set!\n"
        if best_efforts:
            achievements_context += f"💪 Best efforts: {len(best_efforts)} recorded\n"
            # Add details of best efforts (e.g., best 1km, 5km, etc.)
            for effort in best_efforts[:3]:  # Top 3 best efforts
                effort_name = effort.get('name', 'Unknown')
                effort_time = effort.get('elapsed_time', 0)
                achievements_context += f"   - {effort_name}: {effort_time//60}:{effort_time%60:02d}\n"
        if segment_efforts:
            achievements_context += f"🎯 {len(segment_efforts)} segment(s) completed\n"
        
        if not achievements_context:
            achievements_context = "No achievements or PRs for this activity"
        
        # Build athlete stats context (yearly totals, records, etc.)
        athlete_stats_context = ""
        if athlete_stats:
            # Year-to-date totals
            ytd_run = athlete_stats.get('ytd_run_totals', {})
            if ytd_run and ytd_run.get('distance'):
                ytd_distance = ytd_run.get('distance', 0) / 1000  # km
                ytd_count = ytd_run.get('count', 0)
                ytd_time = ytd_run.get('moving_time', 0) / 3600  # hours
                ytd_elevation = ytd_run.get('elevation_gain', 0)
                athlete_stats_context += f"📊 Year-to-Date (2025): {ytd_distance:.0f} km in {ytd_count} runs ({ytd_time:.0f}h, {ytd_elevation:.0f}m D+)\n"
            
            # All-time totals
            all_run = athlete_stats.get('all_run_totals', {})
            if all_run and all_run.get('distance'):
                all_distance = all_run.get('distance', 0) / 1000  # km
                all_count = all_run.get('count', 0)
                athlete_stats_context += f"🏃 All-Time: {all_distance:.0f} km in {all_count} runs\n"
            
            # Recent totals (last 4 weeks)
            recent_run = athlete_stats.get('recent_run_totals', {})
            if recent_run and recent_run.get('distance'):
                recent_distance = recent_run.get('distance', 0) / 1000  # km
                recent_count = recent_run.get('count', 0)
                athlete_stats_context += f"📅 Last 4 Weeks: {recent_distance:.0f} km in {recent_count} runs\n"
            
            # Records
            biggest_ride = athlete_stats.get('biggest_ride_distance')
            biggest_climb = athlete_stats.get('biggest_climb_elevation_gain')
            if biggest_ride:
                athlete_stats_context += f"🚴 Longest Ride: {biggest_ride:.1f} km\n"
            if biggest_climb:
                athlete_stats_context += f"⛰️ Biggest Climb: {biggest_climb:.0f}m D+\n"
        
        if not athlete_stats_context:
            athlete_stats_context = "No athlete stats available"
        
        # Build data-only prompt (instructions are in system_prompt from CONTENT_GENERATION_PROMPT)
        # BUT add explicit size reminder since model ignores system prompt limits
        content_length_pref = user_profile.get('content_preferences', {}).get('length', 'medium') if user_profile else 'medium'
        size_limits = {
            'short': 300,
            'medium': 800,
            'detailed': 1500
        }

        # Resolve "adaptive" content_length intelligently
        if content_length_pref == 'adaptive':
            resolved_length, max_chars = resolve_adaptive_content_length(
                laps, duration, user_profile
            )
            logger.info(f"Adaptive content_length resolved to '{resolved_length}' ({max_chars} chars)")
            logger.info(f"  Laps: {len(laps) if laps else 0}, Duration: {duration:.0f}min")
            content_length_pref = resolved_length
        else:
            max_chars = size_limits.get(content_length_pref, 800)
        
        # P1: Enforce content_language user preference
        content_lang = user_profile.get('content_preferences', {}).get('language', 'french') if user_profile else 'french'
        language_override = ""
        if content_lang != 'french':
            language_override = f"""⚠️ LANGUAGE OVERRIDE: User preference content_language is "{content_lang}".
Generate ALL content (title + description) in {content_lang.upper()}. Do NOT use French.

"""

        prompt = f"""{language_override}⚠️ CRITICAL SIZE LIMIT: User preference is "{content_length_pref}" = MAX {max_chars} characters for description (including signature)!
If you exceed {max_chars} chars, CUT content to fit. Keep most important elements, preserve signature.

🎯 ORIGINAL USER INPUT (PRIORITÉ #1 — REPRENDS CES MOTS TEXTUELLEMENT):
Title: "{validated_title}"
Description: "{validated_description}"
{f"⚠️ Note: Title was sanitized by security filters" if title_blocked else ""}
{f"⚠️ Note: Description was sanitized by security filters" if desc_blocked else ""}
⚠️ Construis ton récit AUTOUR de ces sensations. Elles sont le fil narratif, les données viennent les enrichir — pas l'inverse.

{f"## Athlete Profile\n{user_profile.get('athlete_profile', '')}\n\n" if user_profile and user_profile.get('athlete_profile') else ""}ACTIVITY DATA:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes (Moving: {duration:.0f} min, Elapsed: {elapsed_time:.0f} min)
- Elevation: {elevation:.0f} m
- Average Speed: {avg_speed:.1f} km/h
- Max Speed: {max_speed:.1f} km/h
- Average HR: {avg_hr} bpm (Max: {max_hr} bpm)
{f"- Zone FC (Strava, SOURCE DE VERITE): {activity_data['_strava_hr_zone']['label']}, {activity_data['_strava_hr_zone']['dominant_pct']}% du temps. Regle stricte: n'ecris JAMAIS un autre numero de zone FC que celui-ci. Si cette ligne est absente, ne mentionne AUCUNE zone FC numerotee." if activity_data.get('_strava_hr_zone') else ""}
{f"- Average Cadence: {avg_cadence:.0f} spm{f' (Max: {max_cadence:.0f} spm)' if max_cadence else ''}" if avg_cadence else ""}
{f"- Power: Avg {avg_watts:.0f}W{f', Max {max_watts:.0f}W' if max_watts else ''}{f', Weighted {weighted_avg_watts:.0f}W' if weighted_avg_watts else ''} {'(Device)' if device_watts else '(Estimated)'}" if avg_watts else ""}
{f"- Calories: {calories:.0f} kcal" if calories else ""}
{f"- Suffer Score: {suffer_score:.0f}/100" if suffer_score else ""}
{f"- Workout Type: {workout_type_str}" if workout_type_str else ""}
- Date: {activity_data.get('start_date', 'Unknown')}

ATHLETE CONTEXT (Power-to-Weight, FTP):
{athlete_context}

ACHIEVEMENTS & PERFORMANCE HIGHLIGHTS:
{achievements_context}

ATHLETE STATS (Yearly Progress & Records):
{athlete_stats_context}

SPLITS & LAPS:
{f"- Metric Splits: {len(splits_metric)} km splits available" if splits_metric else ""}
{f"- Standard Splits: {len(splits_standard)} mile splits available" if splits_standard else ""}
{_format_laps_for_prompt(laps)}

LOCATION & WEATHER:
{location_context}

{user_profile_str}

ACTIVE MODULES:
{active_modules_str}

CAMPUS COACH SESSION:
{campus_session_str}

ENDURAW DATA:
{enduraw_str}

{_build_intervals_icu_context(intervals_icu_data)}
AVANT DE GÉNÉRER, réfléchis étape par étape (dans un bloc <thinking>):
1. Quelles sensations/émotions l'utilisateur exprime dans son titre et sa description ?
2. Comment les données (FC, pace, phases) confirment ou enrichissent ces sensations ?
3. Quel arc narratif construire autour de ces sensations ?
Puis génère le JSON.

RAPPEL FINAL NON NÉGOCIABLE : zéro em dash (—/–), et AUCUNE expression de la liste "Expressions bannies (clichés gen-AI sportif)" du system prompt (ex. "la machine", "le corps se réveille", "rythme de croisière", "les kilomètres défilent", ni aucune variante proche). Relis ta réponse et reformule si besoin AVANT de rendre le JSON.

MOMENT DE LA JOURNÉE : n'invente JAMAIS un moment ("ce matin", "ce midi", "ce soir") pour une séance dont tu n'as pas l'heure explicite. Si l'athlète a enchaîné plusieurs séances le même jour, écris "juste avant" ou "plus tôt dans la journée", jamais un moment précis que tu ne connais pas.

VOCABULAIRE : le renforcement musculaire s'écrit "renfo" (jamais "rando" ni "rendo"). "rando" désigne la randonnée, un sport différent : ne l'emploie jamais pour une séance de musculation ou de renforcement.

SÉANCE RENFO / PPG : quand une séance Campus est fournie (CAMPUS COACH SESSION), le commentaire doit INTÉGRER toute la séance, exercice par exercice, dans l'ordre des blocs, d'après campus_coach_session : reprends chaque exercice par son "name" (Extension de Mollet, Gainage Frontal, Mollet statique, Gainage Latéral, Split Squat, Bond sur place, Swing...) avec ses "reps"/"duration". Les CHARGES ne sont pas dans Campus : MAPPE les charges que l'athlète donne dans SA description sur l'exercice correspondant (ex. "mollet 12kg" -> Extension de Mollet, "split squat 2 kettlebells de 20kg" -> Split Squat, "swing 24kg" -> Swing), fidèlement, SANS transformer une charge en nombre de reps ("2 kettlebells de 20kg" n'est PAS "20 fentes") et SANS ajouter de variante non écrite ("bulgare"). Tout exercice pour lequel l'athlète ne précise AUCUNE charge est réalisé AU POIDS DU CORPS : dis-le explicitement (gainages, bonds, mollet statique...) et n'invente jamais de kg.

Generate content now."""
        
        # Invoke agent
        logger.info(f"Invoking agent with prompt length: {len(prompt)} characters")
        logger.info(f"🎯 User original input - Title: '{validated_title}' | Description: '{validated_description[:150]}'")
        logger.info(f"🎯 Prompt starts with: {prompt[:500]}")
        result = agent(prompt)

        # P1.2: Log prompt cache metrics
        try:
            usage = result.metrics.accumulated_usage
            cache_write = usage.get('cacheWriteInputTokens', 0)
            cache_read = usage.get('cacheReadInputTokens', 0)
            logger.info(f"📦 Prompt cache: write={cache_write} read={cache_read} tokens")
        except Exception:
            pass

        # No need to check guardrail intervention on model (we validated inputs separately)
        # Parse the response — handle None message (model timeout/throttle/empty response)
        if result.message is None:
            raise RuntimeError("Agent returned no message (possible model throttle or empty response)")
        response_text = result.message.get('content', [{}])[0].get('text', str(result))
        
        logger.info(f"=== Content Generation Completed ===")
        logger.info(f"Response length: {len(response_text)} characters")
        logger.info(f"Model used: {MODEL_ID}")
        logger.info(f"Memory used: {MEMORY_ID is not None}")
        
        # Return the structured response
        return {
            "response": response_text,
            "user_id": user_id,
            "activity_id": activity_data.get('id', 'unknown'),
            "model_id": MODEL_ID,
            "agentcore_runtime": "content_generation_with_memory",
            "prompt_source": "embedded_detailed_prompt"
        }
        
    except Exception as e:
        logger.error(f"=== Content Generation Failed ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Activity ID: {payload.get('activity_data', {}).get('id', 'unknown')}")
        return {
            "error": "Content generation failed. Check CloudWatch logs for details.",
            "user_id": payload.get('user_id', 'unknown'),
            "activity_id": payload.get('activity_data', {}).get('id', 'unknown'),
            "model_id": MODEL_ID,
            "agentcore_runtime": "content_generation_with_memory"
        }


# Required AgentCore app.run() call
if __name__ == "__main__":
    app.run()