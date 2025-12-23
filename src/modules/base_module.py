"""
Base Module Interface for Strava AI Boost

Defines the interface that all modules must implement for consistent integration.
Includes lifecycle management, error handling, and module registry system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Type, Callable
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import logging
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)


class ModuleStatus(str, Enum):
    """Module status enumeration"""
    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class ModuleConfig(BaseModel):
    """Module configuration model with validation"""
    module_id: str = Field(..., description="Unique module identifier")
    enabled: bool = Field(default=False, description="Whether module is enabled")
    credentials: Optional[Dict[str, str]] = Field(default=None, description="Module credentials")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Module settings")
    priority: int = Field(default=100, description="Module execution priority (lower = higher priority)")
    timeout_seconds: int = Field(default=30, description="Module execution timeout")
    retry_attempts: int = Field(default=3, description="Number of retry attempts on failure")
    
    @field_validator('module_id')
    @classmethod
    def validate_module_id(cls, v):
        if not v or not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('module_id must be alphanumeric with underscores/hyphens')
        return v
    
    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v < 0 or v > 1000:
            raise ValueError('priority must be between 0 and 1000')
        return v


class ModuleInsight(BaseModel):
    """Module analysis result model with enhanced metadata"""
    module_id: str = Field(..., description="Module that generated the insight")
    insights: Dict[str, Any] = Field(..., description="Analysis results")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    processing_time_ms: Optional[int] = Field(default=None, description="Processing time in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Error message if processing failed")
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v


class ModuleError(Exception):
    """Base exception for module-related errors"""
    def __init__(self, module_id: str, message: str, original_error: Optional[Exception] = None):
        self.module_id = module_id
        self.message = message
        self.original_error = original_error
        super().__init__(f"Module {module_id}: {message}")


class ModuleConfigurationError(ModuleError):
    """Exception for module configuration errors"""
    pass


class ModuleProcessingError(ModuleError):
    """Exception for module processing errors"""
    pass


class BaseModule(ABC):
    """
    Enhanced base class for all Strava AI Boost modules
    
    Provides lifecycle management, error handling, and consistent interface.
    Modules provide additional analysis and enhancement capabilities:
    - Campus Coach: Training session matching
    - Enduraw: Enhanced analytics
    - Future modules: Runna, TrainingPeaks, etc.
    """
    
    def __init__(self, config: ModuleConfig):
        self.config = config
        self.enabled = config.enabled
        self.status = ModuleStatus.INACTIVE
        self.last_error: Optional[str] = None
        self.initialization_time: Optional[datetime] = None
        self.last_activity_time: Optional[datetime] = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """
        Initialize the module
        
        Returns:
            True if initialization successful
        """
        try:
            self.status = ModuleStatus.INITIALIZING
            logger.info(f"Initializing module {self.config.module_id}")
            
            # Validate configuration
            if not await self.validate_configuration():
                raise ModuleConfigurationError(
                    self.config.module_id, 
                    "Configuration validation failed"
                )
            
            # Perform module-specific initialization
            await self._initialize_module()
            
            self.status = ModuleStatus.ACTIVE
            self.initialization_time = datetime.now(timezone.utc)
            self._initialized = True
            self.last_error = None
            
            logger.info(f"Module {self.config.module_id} initialized successfully")
            return True
            
        except Exception as e:
            self.status = ModuleStatus.ERROR
            self.last_error = str(e)
            logger.error(f"Module {self.config.module_id} initialization failed: {str(e)}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown the module and cleanup resources"""
        try:
            logger.info(f"Shutting down module {self.config.module_id}")
            await self._shutdown_module()
            self.status = ModuleStatus.INACTIVE
            self._initialized = False
            logger.info(f"Module {self.config.module_id} shutdown complete")
        except Exception as e:
            logger.error(f"Module {self.config.module_id} shutdown error: {str(e)}")
    
    async def analyze_activity_with_timeout(
        self, 
        activity_data: Dict[str, Any],
        streams_data: Optional[Dict[str, Any]] = None
    ) -> ModuleInsight:
        """
        Analyze activity with timeout and error handling
        
        Args:
            activity_data: Complete Strava activity data
            streams_data: Optional streams data for detailed analysis
            
        Returns:
            ModuleInsight with analysis results
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.is_enabled() or self.status != ModuleStatus.ACTIVE:
            return ModuleInsight(
                module_id=self.config.module_id,
                insights={},
                confidence=0.0,
                metadata={"status": "disabled", "reason": "Module not active"}
            )
        
        start_time = datetime.now()
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self.analyze_activity(activity_data, streams_data),
                timeout=self.config.timeout_seconds
            )
            
            # Update processing time
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_time_ms = int(processing_time)
            
            self.last_activity_time = datetime.now(timezone.utc)
            return result
            
        except asyncio.TimeoutError:
            error_msg = f"Module processing timeout after {self.config.timeout_seconds}s"
            logger.error(f"Module {self.config.module_id}: {error_msg}")
            return ModuleInsight(
                module_id=self.config.module_id,
                insights={},
                confidence=0.0,
                metadata={"status": "timeout"},
                error_message=error_msg
            )
            
        except Exception as e:
            error_msg = f"Module processing error: {str(e)}"
            logger.error(f"Module {self.config.module_id}: {error_msg}")
            return ModuleInsight(
                module_id=self.config.module_id,
                insights={},
                confidence=0.0,
                metadata={"status": "error"},
                error_message=error_msg
            )
    
    @abstractmethod
    async def analyze_activity(
        self, 
        activity_data: Dict[str, Any],
        streams_data: Optional[Dict[str, Any]] = None
    ) -> ModuleInsight:
        """
        Analyze activity data and return insights
        
        Args:
            activity_data: Complete Strava activity data
            streams_data: Optional streams data for detailed analysis
            
        Returns:
            ModuleInsight with analysis results
        """
        pass
    
    @abstractmethod
    async def configure(self, credentials: Dict[str, str]) -> bool:
        """
        Configure module with credentials and settings
        
        Args:
            credentials: Module-specific credentials
            
        Returns:
            True if configuration successful
        """
        pass
    
    @abstractmethod
    async def validate_configuration(self) -> bool:
        """
        Validate current module configuration
        
        Returns:
            True if configuration is valid
        """
        pass
    
    async def _initialize_module(self) -> None:
        """
        Module-specific initialization logic
        Override in subclasses for custom initialization
        """
        pass
    
    async def _shutdown_module(self) -> None:
        """
        Module-specific shutdown logic
        Override in subclasses for custom cleanup
        """
        pass
    
    def is_enabled(self) -> bool:
        """Check if module is enabled"""
        return self.enabled and self.config.enabled
    
    def enable(self) -> None:
        """Enable the module"""
        self.enabled = True
        self.config.enabled = True
        if self.status == ModuleStatus.DISABLED:
            self.status = ModuleStatus.INACTIVE
    
    def disable(self) -> None:
        """Disable the module"""
        self.enabled = False
        self.config.enabled = False
        self.status = ModuleStatus.DISABLED
    
    def get_config(self) -> ModuleConfig:
        """Get current module configuration"""
        return self.config
    
    def get_status(self) -> Dict[str, Any]:
        """Get module status information"""
        return {
            "module_id": self.config.module_id,
            "enabled": self.is_enabled(),
            "status": self.status.value,
            "last_error": self.last_error,
            "initialization_time": self.initialization_time.isoformat() if self.initialization_time else None,
            "last_activity_time": self.last_activity_time.isoformat() if self.last_activity_time else None,
            "priority": self.config.priority
        }
    
    def update_settings(self, settings: Dict[str, Any]) -> None:
        """Update module settings"""
        self.config.settings.update(settings)
    
    def get_required_credentials(self) -> List[str]:
        """
        Get list of required credential fields
        Override in subclasses to specify required credentials
        """
        return []
    
    def get_module_info(self) -> Dict[str, Any]:
        """
        Get module information for display
        Override in subclasses to provide module-specific info
        """
        return {
            "module_id": self.config.module_id,
            "name": self.config.module_id.replace('_', ' ').title(),
            "description": "Base module",
            "version": "1.0.0",
            "required_credentials": self.get_required_credentials(),
            "settings_schema": {}
        }


class ModuleRegistry:
    """
    Registry for managing available modules
    
    Provides module discovery, registration, and lifecycle management
    """
    
    def __init__(self):
        self._modules: Dict[str, Type[BaseModule]] = {}
        self._instances: Dict[str, BaseModule] = {}
        self._initialization_callbacks: List[Callable] = []
    
    def register_module(self, module_class: Type[BaseModule], module_id: str) -> None:
        """
        Register a module class
        
        Args:
            module_class: Module class to register
            module_id: Unique module identifier
        """
        if not issubclass(module_class, BaseModule):
            raise ValueError(f"Module class must inherit from BaseModule")
        
        if module_id in self._modules:
            logger.warning(f"Module {module_id} already registered, overwriting")
        
        self._modules[module_id] = module_class
        logger.info(f"Registered module: {module_id}")
    
    def get_available_modules(self) -> List[str]:
        """Get list of available module IDs"""
        return list(self._modules.keys())
    
    def get_module_info(self, module_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific module"""
        if module_id not in self._modules:
            return None
        
        # Create temporary instance to get info
        temp_config = ModuleConfig(module_id=module_id, enabled=False)
        temp_instance = self._modules[module_id](temp_config)
        return temp_instance.get_module_info()
    
    def create_module_instance(self, module_id: str, config: ModuleConfig) -> Optional[BaseModule]:
        """
        Create a module instance
        
        Args:
            module_id: Module identifier
            config: Module configuration
            
        Returns:
            Module instance or None if not found
        """
        if module_id not in self._modules:
            logger.error(f"Module {module_id} not found in registry")
            return None
        
        try:
            instance = self._modules[module_id](config)
            self._instances[module_id] = instance
            logger.info(f"Created instance of module {module_id}")
            return instance
        except Exception as e:
            logger.error(f"Failed to create module {module_id}: {str(e)}")
            return None
    
    def get_module_instance(self, module_id: str) -> Optional[BaseModule]:
        """Get existing module instance"""
        return self._instances.get(module_id)
    
    async def initialize_all_modules(self) -> Dict[str, bool]:
        """
        Initialize all module instances
        
        Returns:
            Dict mapping module_id to initialization success
        """
        results = {}
        
        for module_id, instance in self._instances.items():
            try:
                success = await instance.initialize()
                results[module_id] = success
                
                # Call initialization callbacks
                for callback in self._initialization_callbacks:
                    try:
                        await callback(module_id, success)
                    except Exception as e:
                        logger.error(f"Initialization callback failed: {str(e)}")
                        
            except Exception as e:
                logger.error(f"Failed to initialize module {module_id}: {str(e)}")
                results[module_id] = False
        
        return results
    
    async def shutdown_all_modules(self) -> None:
        """Shutdown all module instances"""
        for module_id, instance in self._instances.items():
            try:
                await instance.shutdown()
            except Exception as e:
                logger.error(f"Failed to shutdown module {module_id}: {str(e)}")
        
        self._instances.clear()
    
    def add_initialization_callback(self, callback: Callable) -> None:
        """Add callback to be called after module initialization"""
        self._initialization_callbacks.append(callback)
    
    def get_registry_status(self) -> Dict[str, Any]:
        """Get registry status information"""
        return {
            "registered_modules": len(self._modules),
            "active_instances": len(self._instances),
            "modules": {
                module_id: instance.get_status() 
                for module_id, instance in self._instances.items()
            }
        }


# Global module registry instance
module_registry = ModuleRegistry()