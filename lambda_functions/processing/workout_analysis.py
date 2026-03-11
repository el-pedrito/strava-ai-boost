"""
Workout Analysis Module

Workout classification from laps and Enduraw report extraction.
"""

import re
from typing import Dict, Any, Optional, List

from shared.logger import get_logger

logger = get_logger("workout-analysis")


def _parse_pace_mmss(pace_str: str) -> float:
    """Convert mm:ss pace string to float minutes. E.g. '5:45' -> 5.75"""
    try:
        parts = str(pace_str).split(':')
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60.0
        return float(pace_str)
    except (ValueError, TypeError):
        return 0.0


def _classify_by_pace_zones(avg_pace: float, pace_zones: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Classify workout by matching average pace against user-configured pace zones.
    Returns {'type': ..., 'label': ...} if a zone matches, None otherwise.
    """
    zone_labels = {
        'recovery': ('recovery_run', 'Recup / Recovery'),
        'ef': ('steady_easy_run', 'Endurance Fondamentale'),
        'aerobic': ('aerobic', 'Allure Aerobie'),
        'tempo': ('tempo', 'Tempo'),
        'sweet_spot': ('sweet_spot', 'Sweet Spot'),
        'seuil_60': ('threshold_60', 'Seuil 60'),
        'seuil_30': ('threshold_30', 'Seuil 30'),
        'allure_marathon': ('marathon_pace', 'Allure Marathon'),
        'allure_semi': ('half_marathon_pace', 'Allure Semi'),
        'interval': ('intervals', 'Intervalles / VMA'),
    }

    best_match = None
    best_distance = float('inf')

    for zone_key, zone_val in pace_zones.items():
        if not isinstance(zone_val, dict):
            continue
        zone_min = _parse_pace_mmss(zone_val.get('min', '0'))
        zone_max = _parse_pace_mmss(zone_val.get('max', '0'))
        if zone_min <= 0 or zone_max <= 0:
            continue

        slow_pace = max(zone_min, zone_max)
        fast_pace = min(zone_min, zone_max)

        if fast_pace <= avg_pace <= slow_pace:
            midpoint = (fast_pace + slow_pace) / 2
            distance = abs(avg_pace - midpoint)
            if distance < best_distance:
                best_distance = distance
                type_name, label_fr = zone_labels.get(zone_key, (zone_key, zone_key.replace('_', ' ').title()))
                best_match = {'type': type_name, 'label': label_fr}

    if best_match:
        logger.info(f"Pace zone match: avg_pace={avg_pace:.2f} -> {best_match['label']}")
    return best_match


def classify_workout_from_laps(
    laps: List[Dict[str, Any]],
    pace_zones: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Classify the workout type based on device-recorded laps.

    Uses pace variability between laps and user-configured pace zones
    to determine workout type (intervals, fartlek, steady, progression, etc.).
    """
    if not laps or len(laps) < 2:
        return {'type': 'unknown', 'confidence': 0}

    # Extract paces from laps (min/km)
    all_paces = []
    for lap in laps:
        avg_speed = lap.get('average_speed', 0)
        if avg_speed > 0:
            pace = 1000 / (avg_speed * 60)  # min/km
            if 0 < pace < 15:
                all_paces.append(pace)

    if len(all_paces) < 2:
        return {'type': 'unknown', 'confidence': 0}

    avg_pace = sum(all_paces) / len(all_paces)
    pace_std = (sum((p - avg_pace) ** 2 for p in all_paces) / len(all_paces)) ** 0.5
    pace_range = max(all_paces) - min(all_paces)

    # Collect HR stats from laps
    valid_hrs = [lap.get('average_heartrate', 0) for lap in laps if lap.get('average_heartrate', 0) > 0]
    avg_hr = sum(valid_hrs) / len(valid_hrs) if valid_hrs else 0

    # Detect intervals by variability
    if pace_std > 0.6 and pace_range > 2.0:
        workout_type = 'intervals'
        label = 'Fractionne / Intervalles'
    elif pace_std > 0.40:
        # Check if it's a progression
        first_third = all_paces[:len(all_paces) // 3]
        last_third = all_paces[2 * len(all_paces) // 3:]
        if first_third and last_third:
            avg_first = sum(first_third) / len(first_third)
            avg_last = sum(last_third) / len(last_third)
            if avg_first - avg_last > 0.5:
                workout_type = 'progression'
                label = 'Progression / Negative Split'
            else:
                workout_type = 'fartlek'
                label = 'Fartlek'
        else:
            workout_type = 'fartlek'
            label = 'Fartlek'
    else:
        # Steady pace — try pace zone classification
        workout_type = 'steady'
        label = 'Sortie Reguliere'

        if pace_zones:
            zone_match = _classify_by_pace_zones(avg_pace, pace_zones)
            if zone_match:
                workout_type = zone_match['type']
                label = zone_match['label']

    result = {
        'type': workout_type,
        'label': label,
        'confidence': min(0.95, 0.6 + (1.0 - pace_std) * 0.3) if workout_type != 'unknown' else 0,
        'stats': {
            'avg_pace': round(avg_pace, 2),
            'pace_std': round(pace_std, 2),
            'pace_range': round(pace_range, 2),
            'avg_hr': round(avg_hr) if avg_hr else None,
            'laps_analyzed': len(all_paces),
        }
    }

    logger.info(f"Workout classification: {workout_type} ({label}) — std={pace_std:.2f}, range={pace_range:.2f}")
    return result


def extract_enduraw_report(activity_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract Enduraw Report from activity description"""
    try:
        description = activity_data.get('description', '')

        if not description or '𝗘𝗻𝗱𝘂𝗿𝗮𝘄 𝗥𝗲𝗽𝗼𝗿𝘁' not in description:
            return None

        enduraw_pattern = r'📈 𝗠𝘆 𝗘𝗻𝗱𝘂𝗿𝗮𝘄 𝗥𝗲𝗽𝗼𝗿𝘁 📈(.*?)(?:Try it now|$)'
        match = re.search(enduraw_pattern, description, re.DOTALL)

        if not match:
            return None

        report_text = match.group(1).strip()

        enduraw_data = {
            'report_available': True,
            'report_text': report_text,
            'metrics': {}
        }

        # Extract adjusted pace
        pace_match = re.search(r'Adjusted Pace:\s*([𝟬-𝟵]+):([𝟬-𝟵]+)/km', report_text)
        if pace_match:
            min_bold = pace_match.group(1).translate(str.maketrans('𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵', '0123456789'))
            sec_bold = pace_match.group(2).translate(str.maketrans('𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵', '0123456789'))
            enduraw_data['metrics']['adjusted_pace'] = f"{min_bold}:{sec_bold}/km"

        # Extract wind impact
        wind_match = re.search(r'Wind \(([0-9.]+)km/h\) cost you ([𝟬-𝟵]+)\'([𝟬-𝟵]+)"/km', report_text)
        if wind_match:
            wind_speed = wind_match.group(1)
            min_bold = wind_match.group(2).translate(str.maketrans('𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵', '0123456789'))
            sec_bold = wind_match.group(3).translate(str.maketrans('𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵', '0123456789'))
            enduraw_data['metrics']['wind_speed'] = f"{wind_speed}km/h"
            enduraw_data['metrics']['wind_cost'] = f"{min_bold}'{sec_bold}\"/km"

        # Extract elevation impact
        elev_match = re.search(r'Elevation \(([0-9.]+)% avg\) cost you ([𝟬-𝟵]+)\'([𝟬-𝟵]+)"/km', report_text)
        if elev_match:
            elev_pct = elev_match.group(1)
            min_bold = elev_match.group(2).translate(str.maketrans('𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵', '0123456789'))
            sec_bold = elev_match.group(3).translate(str.maketrans('𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵', '0123456789'))
            enduraw_data['metrics']['elevation_avg'] = f"{elev_pct}%"
            enduraw_data['metrics']['elevation_cost'] = f"{min_bold}'{sec_bold}\"/km"

        logger.info(f"Extracted Enduraw Report: {enduraw_data['metrics']}")
        return enduraw_data

    except Exception as e:
        logger.error(f"Failed to extract Enduraw Report: {str(e)}")
        return None
