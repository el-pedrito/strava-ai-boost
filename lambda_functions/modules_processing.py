"""
Modules Processing

Handles module discovery, activation, and per-module processing
(Campus Coach session matching, Enduraw, etc.)
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta, timezone

import boto3

logger = logging.getLogger()

REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
COACHING_SESSIONS_TABLE = os.environ.get('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')


def get_active_modules(user_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get list of active modules for the user using module registry"""
    try:
        from modules import module_registry

        modules_config = user_config.get('modules_config', {})
        active_modules = []

        available_modules = module_registry.get_available_modules()

        for module_id in available_modules:
            config = modules_config.get(module_id, {})
            if config.get('enabled', False):
                module_info = module_registry.get_module_info(module_id)
                if module_info:
                    active_modules.append({
                        'name': module_id,
                        'config': config,
                        'enabled': True,
                        'info': module_info
                    })

        logger.info(f"Found {len(active_modules)} active modules from registry")
        return active_modules

    except ImportError:
        logger.warning("Module registry not available, using fallback")
        modules_config = user_config.get('modules_config', {})
        active_modules = []

        for module_id, config in modules_config.items():
            if config.get('enabled', False):
                active_modules.append({
                    'name': module_id,
                    'config': config,
                    'enabled': True
                })

        logger.info(f"Found {len(active_modules)} active modules (fallback)")
        return active_modules

    except Exception as e:
        logger.error(f"Failed to get active modules: {str(e)}")
        return []


def apply_module_processing(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    modules: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Apply module-specific processing using module registry"""
    enhanced_modules = []

    try:
        from modules import module_registry, ModuleConfig

        for module in modules:
            try:
                module_id = module['name']
                config_data = module.get('config', {})
                module_config = ModuleConfig(
                    module_id=module_id,
                    enabled=module.get('enabled', False),
                    credentials=config_data.get('credentials'),
                    settings=config_data.get('settings', {})
                )

                module_instance = module_registry.create_module_instance(module_id, module_config)

                if module_instance:
                    enhanced_module = _apply_module_instance_processing(
                        activity_data, streams_data, module, module_instance
                    )
                    enhanced_modules.append(enhanced_module)
                else:
                    enhanced_module = _apply_legacy_module_processing(
                        activity_data, module
                    )
                    enhanced_modules.append(enhanced_module)

            except Exception as e:
                logger.error(f"Module {module.get('name', 'unknown')} processing failed: {str(e)}")
                module_with_error = module.copy()
                module_with_error['processing_error'] = str(e)
                enhanced_modules.append(module_with_error)

    except ImportError:
        logger.warning("Module registry not available, using legacy processing")
        for module in modules:
            try:
                enhanced_module = _apply_legacy_module_processing(
                    activity_data, module
                )
                enhanced_modules.append(enhanced_module)
            except Exception as e:
                logger.error(f"Legacy module {module.get('name', 'unknown')} processing failed: {str(e)}")
                module_with_error = module.copy()
                module_with_error['processing_error'] = str(e)
                enhanced_modules.append(module_with_error)

    return enhanced_modules


def _apply_module_instance_processing(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    module: Dict[str, Any],
    module_instance: Any
) -> Dict[str, Any]:
    """Apply processing using module registry instance"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            insight = loop.run_until_complete(
                module_instance.analyze_activity_with_timeout(activity_data, streams_data)
            )

            enhanced_module = module.copy()
            enhanced_module['insight'] = {
                'module_id': insight.module_id,
                'insights': insight.insights,
                'confidence': insight.confidence,
                'metadata': insight.metadata,
                'processing_time_ms': insight.processing_time_ms,
                'error_message': insight.error_message
            }

            logger.info(f"Module {module['name']} processed with confidence: {insight.confidence}")
            return enhanced_module

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Module instance processing error: {str(e)}")
        enhanced_module = module.copy()
        enhanced_module['processing_error'] = str(e)
        return enhanced_module


def _apply_legacy_module_processing(
    activity_data: Dict[str, Any],
    module: Dict[str, Any]
) -> Dict[str, Any]:
    """Apply legacy module processing"""
    try:
        module_name = module['name']

        if module_name == 'campus_coach' and module.get('enabled', False):
            return _apply_campus_coach_processing(activity_data, module)
        elif module_name == 'enduraw' and module.get('enabled', False):
            return module
        else:
            return module

    except Exception as e:
        logger.error(f"Legacy module {module.get('name', 'unknown')} processing failed: {str(e)}")
        module_with_error = module.copy()
        module_with_error['processing_error'] = str(e)
        return module_with_error


def _apply_campus_coach_processing(
    activity_data: Dict[str, Any],
    module: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply Campus Coach session matching.
    Retrieves recent sessions from DynamoDB for agent analysis.
    """
    try:
        logger.info("Retrieving Campus Coach sessions for intelligent agent matching...")

        activity_date = activity_data.get('start_date_local', activity_data.get('start_date', ''))
        distance_km = activity_data.get('distance', 0) / 1000
        duration_min = activity_data.get('moving_time', 0) / 60
        activity_type = activity_data.get('type', '').lower()

        sessions = _get_recent_campus_sessions(activity_date)

        enhanced_module = module.copy()

        if sessions:
            logger.info(f"Retrieved {len(sessions)} Campus Coach sessions for agent analysis")
            enhanced_module['campus_coach_sessions'] = sessions
            enhanced_module['sessions_available'] = True
            enhanced_module['session_count'] = len(sessions)
            enhanced_module['activity_context'] = {
                'date': activity_date,
                'distance_km': distance_km,
                'duration_min': duration_min,
                'type': activity_type,
                'title': activity_data.get('name', ''),
                'description': activity_data.get('description', '')
            }
        else:
            enhanced_module['campus_coach_sessions'] = []
            enhanced_module['sessions_available'] = False
            enhanced_module['note'] = 'No recent Campus Coach sessions found'

        return enhanced_module

    except Exception as e:
        logger.error(f"Campus Coach processing error: {str(e)}")
        enhanced_module = module.copy()
        enhanced_module['campus_coach_sessions'] = []
        enhanced_module['sessions_available'] = False
        enhanced_module['error'] = str(e)
        return enhanced_module


def _get_recent_campus_sessions(activity_date: str = None) -> List[Dict[str, Any]]:
    """Get Campus Coach sessions for the current week only (max 6)"""
    try:
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)

        if activity_date:
            try:
                act_dt = datetime.fromisoformat(activity_date.replace('Z', '+00:00'))
            except Exception:
                act_dt = datetime.now(timezone.utc)
        else:
            act_dt = datetime.now(timezone.utc)

        cutoff_date = (act_dt - timedelta(days=14)).isoformat()

        response = table.scan(
            FilterExpression='updated_at >= :cutoff AND #status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':cutoff': cutoff_date,
                ':status': 'À faire'
            }
        )

        sessions = response.get('Items', [])
        sessions = sorted(sessions, key=lambda x: x.get('updated_at', ''), reverse=True)
        sessions = sessions[:6]

        def decimal_to_float(obj: Any) -> Any:
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: decimal_to_float(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [decimal_to_float(item) for item in obj]
            return obj

        sessions = decimal_to_float(sessions)

        logger.info(f"Retrieved {len(sessions)} Campus Coach sessions")
        return sessions

    except Exception as e:
        logger.error(f"Failed to retrieve Campus Coach sessions: {str(e)}")
        return []
