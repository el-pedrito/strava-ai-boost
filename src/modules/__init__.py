# Modules package for Strava AI Boost

from .base_module import (
    BaseModule, 
    ModuleConfig, 
    ModuleInsight, 
    ModuleStatus,
    ModuleError,
    ModuleConfigurationError,
    ModuleProcessingError,
    ModuleRegistry,
    module_registry
)

from .enduraw_module import EndurawModule

# Import registry to auto-register modules
from . import registry

__all__ = [
    'BaseModule',
    'ModuleConfig',
    'ModuleInsight',
    'ModuleStatus',
    'ModuleError',
    'ModuleConfigurationError',
    'ModuleProcessingError',
    'ModuleRegistry',
    'module_registry',
    'EndurawModule'
]