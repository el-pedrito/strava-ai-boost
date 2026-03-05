"""
Streams Analysis Module

Handles stream compression, workout classification, phase detection,
and Enduraw report extraction.
"""

import json
import os
import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()

REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
ACTIVITIES_TABLE = os.environ.get('ACTIVITIES_TABLE', 'strava-ai-boost-activities')


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


def classify_workout_from_streams(blocks: List[Dict[str, Any]],
                                  pace_zones: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Classify the workout type based on pace variability across blocks.
    Uses user-configured pace zones when available, falls back to statistical heuristics.
    Filters warmup/cooldown outliers using IQR.
    """
    all_paces = [b.get('pace_min_km', 0) for b in blocks if 0 < b.get('pace_min_km', 0) < 15]
    valid_hrs = [b.get('hr_bpm', 0) for b in blocks if b.get('hr_bpm', 0) > 0]

    if len(all_paces) < 3:
        return {'type': 'unknown', 'confidence': 0}

    # Filter outliers using IQR
    sorted_paces = sorted(all_paces)
    q1_idx = len(sorted_paces) // 4
    q3_idx = 3 * len(sorted_paces) // 4
    q1 = sorted_paces[q1_idx]
    q3 = sorted_paces[q3_idx]
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    core_paces = [p for p in all_paces if lower_bound <= p <= upper_bound]

    if len(core_paces) < 3:
        core_paces = all_paces

    avg_pace = sum(core_paces) / len(core_paces)
    pace_std = (sum((p - avg_pace) ** 2 for p in core_paces) / len(core_paces)) ** 0.5
    pace_range = max(core_paces) - min(core_paces)
    avg_hr = sum(valid_hrs) / len(valid_hrs) if valid_hrs else 0
    hr_std = (sum((h - avg_hr) ** 2 for h in valid_hrs) / len(valid_hrs)) ** 0.5 if valid_hrs else 0

    # Step 1: Detect intervals by variability
    if pace_std > 0.6 and pace_range > 2.0:
        workout_type = 'intervals'
        label = 'Fractionne / Intervalles'
    elif pace_std > 0.40:
        # Check if it's a progression
        first_third = core_paces[:len(core_paces)//3]
        last_third = core_paces[2*len(core_paces)//3:]
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
        # Step 2: Steady pace — try pace zone classification
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
            'hr_std': round(hr_std, 1) if hr_std else None,
            'blocks_analyzed': len(core_paces),
        }
    }

    logger.info(f"Workout classification: {workout_type} ({label}) — std={pace_std:.2f}, range={pace_range:.2f}")
    return result


def detect_workout_phases(streams_compressed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pre-compute workout phases from compressed blocks.
    Groups consecutive blocks with similar pace into phases.
    Uses adaptive tolerance based on workout variability.
    """
    if not streams_compressed:
        return []

    blocks = streams_compressed.get('blocks', [])
    if not blocks:
        return []

    all_paces = [b.get('pace_min_km', 0) for b in blocks if 0 < b.get('pace_min_km', 0) < 15]
    if len(all_paces) < 3:
        return []

    sorted_paces = sorted(all_paces)
    q1 = sorted_paces[len(sorted_paces) // 4]
    q3 = sorted_paces[3 * len(sorted_paces) // 4]
    iqr = q3 - q1
    core_paces = [p for p in all_paces if (q1 - 1.5 * iqr) <= p <= (q3 + 1.5 * iqr)]
    if len(core_paces) < 3:
        core_paces = all_paces

    avg_core = sum(core_paces) / len(core_paces)
    pace_std = (sum((p - avg_core) ** 2 for p in core_paces) / len(core_paces)) ** 0.5

    # Adaptive tolerance
    if pace_std < 0.35:
        tolerance = 1.0
    elif pace_std < 0.6:
        tolerance = 0.7
    else:
        tolerance = 0.3

    phases = []
    current_phase = None

    for block in blocks:
        pace = block.get('pace_min_km', 0)
        hr = block.get('hr_bpm', 0)
        duration = block.get('duration_s', 30)

        if pace <= 0 or pace > 15:
            continue

        if current_phase is None:
            current_phase = {'paces': [pace], 'hrs': [hr], 'duration_s': duration}
        elif abs(pace - (sum(current_phase['paces']) / len(current_phase['paces']))) < tolerance:
            current_phase['paces'].append(pace)
            current_phase['hrs'].append(hr)
            current_phase['duration_s'] += duration
        else:
            phases.append(current_phase)
            current_phase = {'paces': [pace], 'hrs': [hr], 'duration_s': duration}

    if current_phase:
        phases.append(current_phase)

    summary = []
    for p in phases:
        avg_pace = sum(p['paces']) / len(p['paces'])
        avg_hr = sum(p['hrs']) / len(p['hrs']) if any(p['hrs']) else 0
        dur_min = p['duration_s'] / 60

        if dur_min < 0.5:
            continue

        pace_min = int(avg_pace)
        pace_sec = int((avg_pace - pace_min) * 60)

        summary.append({
            'duration_min': round(dur_min, 1),
            'avg_pace': f"{pace_min}:{pace_sec:02d}/km",
            'avg_hr': round(avg_hr) if avg_hr else None,
            'blocks_count': len(p['paces'])
        })

    logger.info(f"Detected {len(summary)} workout phases from {len(blocks)} blocks (tolerance={tolerance})")
    return summary


def compress_streams_to_blocks(streams_data: Dict[str, Any], activity_data: Dict[str, Any], activity_id: str) -> Optional[Dict[str, Any]]:
    """
    Compress streams data into adaptive blocks based on activity duration.

    Adaptive compression:
    - < 60 min: 10s blocks (light, enables phase detection)
    - >= 60 min: 30s blocks (standard)
    """
    if not streams_data or not streams_data.get('velocity_smooth'):
        logger.info("No streams data available for compression")
        return None

    try:
        # Check cache in DynamoDB
        table = dynamodb.Table(ACTIVITIES_TABLE)
        response = table.get_item(Key={'activity_id': activity_id})

        if 'Item' in response and response['Item'].get('streams_analysis_json'):
            logger.info("Using cached compressed streams from DynamoDB")
            return json.loads(response['Item']['streams_analysis_json'])

        logger.info("No cached data found, compressing streams with adaptive blocks...")

        velocity = streams_data.get('velocity_smooth', {}).get('data', [])
        heartrate = streams_data.get('heartrate', {}).get('data', [])
        time_series = streams_data.get('time', {}).get('data', [])
        cadence_stream = streams_data.get('cadence', {}).get('data', [])
        watts_stream = streams_data.get('watts', {}).get('data', [])

        if not velocity or len(velocity) < 10:
            logger.info("Insufficient streams data for compression")
            return None

        activity_duration_seconds = activity_data.get('elapsed_time', 0)
        activity_duration_minutes = activity_duration_seconds / 60

        if activity_duration_minutes < 60:
            block_duration = 10
            compression_level = "light"
        else:
            block_duration = 30
            compression_level = "standard"

        logger.info(f"Activity duration: {activity_duration_minutes:.1f} min -> Block duration: {block_duration}s ({compression_level})")

        blocks = []
        i = 0
        while i < len(velocity):
            start_time = time_series[i] if i < len(time_series) else i
            end_time = start_time + block_duration

            block_velocities = []
            block_hrs = []
            block_cadences = []
            block_watts = []
            block_end_idx = i

            while block_end_idx < len(velocity):
                current_time = time_series[block_end_idx] if block_end_idx < len(time_series) else block_end_idx
                if current_time >= end_time:
                    break

                if velocity[block_end_idx] > 0:
                    block_velocities.append(velocity[block_end_idx])
                if block_end_idx < len(heartrate) and heartrate[block_end_idx]:
                    block_hrs.append(heartrate[block_end_idx])
                if block_end_idx < len(cadence_stream) and cadence_stream[block_end_idx]:
                    block_cadences.append(cadence_stream[block_end_idx])
                if block_end_idx < len(watts_stream) and watts_stream[block_end_idx]:
                    block_watts.append(watts_stream[block_end_idx])

                block_end_idx += 1

            if block_velocities:
                avg_velocity = sum(block_velocities) / len(block_velocities)
                avg_pace_min_km = 1000 / (avg_velocity * 60) if avg_velocity > 0 else 0
                avg_speed_kmh = avg_velocity * 3.6

                block = {
                    'time_min': round(start_time / 60, 1),
                    'duration_s': block_duration,
                    'pace_min_km': round(avg_pace_min_km, 2),
                    'speed_kmh': round(avg_speed_kmh, 1)
                }

                if block_hrs:
                    block['hr_bpm'] = int(sum(block_hrs) / len(block_hrs))
                if block_cadences:
                    block['cadence'] = int(sum(block_cadences) / len(block_cadences))
                if block_watts:
                    block['watts'] = int(sum(block_watts) / len(block_watts))

                blocks.append(block)

            i = block_end_idx if block_end_idx > i else i + 1

        # Extract route landmarks from Strava segments
        route_landmarks = []
        segment_efforts = activity_data.get('segment_efforts', [])
        if segment_efforts:
            sorted_segments = sorted(segment_efforts, key=lambda s: s.get('start_index', 0))

            if len(sorted_segments) >= 3:
                key_indices = [0, len(sorted_segments) // 2, len(sorted_segments) - 1]
            elif len(sorted_segments) == 2:
                key_indices = [0, 1]
            else:
                key_indices = [0]

            for idx in key_indices:
                segment_effort = sorted_segments[idx]
                segment = segment_effort.get('segment', {})
                segment_name = segment.get('name')
                city = segment.get('city')
                country = segment.get('country')

                if city or segment_name:
                    position = 'start' if idx == 0 else 'end' if idx == len(key_indices) - 1 else 'middle'
                    route_landmarks.append({
                        'position': position,
                        'segment_name': segment_name,
                        'city': city,
                        'country': country,
                        'distance_m': segment_effort.get('distance', 0),
                        'elapsed_time_s': segment_effort.get('elapsed_time', 0),
                        'pr_rank': segment_effort.get('pr_rank'),
                    })

        # Extract segment PRs
        segment_prs = []
        for se in segment_efforts:
            pr_rank = se.get('pr_rank')
            if pr_rank and pr_rank <= 3:
                segment_prs.append({
                    'name': se.get('segment', {}).get('name', ''),
                    'pr_rank': pr_rank,
                    'elapsed_time_s': se.get('elapsed_time', 0),
                    'distance_m': se.get('distance', 0),
                })

        # Build performance_summary
        performance_summary = {}
        if heartrate:
            performance_summary['avg_hr_bpm'] = int(sum(heartrate) / len(heartrate))
            performance_summary['max_hr_bpm'] = max(heartrate)
        if velocity:
            non_zero_vel = [v for v in velocity if v > 0]
            if non_zero_vel:
                avg_vel = sum(non_zero_vel) / len(non_zero_vel)
                performance_summary['avg_speed_kmh'] = round(avg_vel * 3.6, 1)
                performance_summary['max_speed_kmh'] = round(max(non_zero_vel) * 3.6, 1)
                performance_summary['avg_pace_min_km'] = round(1000 / (avg_vel * 60), 2) if avg_vel > 0 else None
        if cadence_stream:
            non_zero_cad = [c for c in cadence_stream if c > 0]
            if non_zero_cad:
                performance_summary['avg_cadence'] = int(sum(non_zero_cad) / len(non_zero_cad))
                performance_summary['max_cadence'] = max(non_zero_cad)
        if watts_stream:
            non_zero_watts = [w for w in watts_stream if w > 0]
            if non_zero_watts:
                performance_summary['avg_watts'] = int(sum(non_zero_watts) / len(non_zero_watts))
                performance_summary['max_watts'] = max(non_zero_watts)
        for key in ('workout_type', 'suffer_score', 'pr_count', 'achievement_count'):
            val = activity_data.get(key)
            if val is not None:
                performance_summary[key] = val

        compressed_data = {
            'blocks': blocks,
            'block_duration_s': block_duration,
            'compression_level': compression_level,
            'activity_duration_min': round(activity_duration_minutes, 1),
            'total_blocks': len(blocks),
            'total_duration_min': round(blocks[-1]['time_min'] if blocks else 0, 1),
            'compression_ratio': f"{len(velocity)} points -> {len(blocks)} blocks ({block_duration}s blocks)",
            'route_landmarks': route_landmarks if route_landmarks else None,
            'performance_summary': performance_summary if performance_summary else None,
            'segment_prs': segment_prs if segment_prs else None
        }

        # Cache in DynamoDB
        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="SET streams_analysis_json = :data, updated_at = :updated",
            ExpressionAttributeValues={
                ':data': json.dumps(compressed_data),
                ':updated': datetime.now(timezone.utc).isoformat()
            }
        )

        logger.info(f"Streams compressed: {len(velocity)} points -> {len(blocks)} blocks ({block_duration}s each)")
        return compressed_data

    except Exception as e:
        logger.error(f"Failed to compress streams: {str(e)}")
        return None


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
