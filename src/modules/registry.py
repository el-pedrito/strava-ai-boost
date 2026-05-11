"""
Module Registry Setup for Strava AI Boost

Registers all available modules with the module registry system.
"""

import logging
from .base_module import module_registry
from .enduraw_module import EndurawModule

logger = logging.getLogger(__name__)


def register_all_modules() -> None:
    """Register all available modules with the registry"""
    try:
        # Register Enduraw module
        module_registry.register_module(EndurawModule, "enduraw")
        
        # Additional modules can be registered here
        # module_registry.register_module(RunnaModule, "runna")
        # module_registry.register_module(TrainingPeaksModule, "training_peaks")
        
        logger.info("All modules registered successfully")
        
    except Exception as e:
        logger.error(f"Failed to register modules: {str(e)}")
        raise


def get_module_registry():
    """Get the configured module registry"""
    return module_registry


# Auto-register modules when this module is imported
register_all_modules()