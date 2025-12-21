"""
Base Module Interface for Strava AI Boost

Defines the interface that all modules must implement for consistent integration.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel


class ModuleConfig(BaseModel):
    """Module configuration model"""
    module_id: str
    enabled: bool
    credentials: Optional[Dict[str, str]] = None
    settings: Dict[str, Any] = {}


class ModuleInsight(BaseModel):
    """Module analysis result model"""
    module_id: str
    insights: Dict[str, Any]
    confidence: float
    metadata: Dict[str, Any] = {}


class BaseModule(ABC):
    """
    Base class for all Strava AI Boost modules
    
    Modules provide additional analysis and enhancement capabilities:
    - Campus Coach: Training session matching
    - Enduraw: Enhanced analytics
    - Future modules: Runna, TrainingPeaks, etc.
    """
    
    def __init__(self, config: ModuleConfig):
        self.config = config
        self.enabled = config.enabled
    
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
    
    def is_enabled(self) -> bool:
        """Check if module is enabled"""
        return self.enabled
    
    def enable(self) -> None:
        """Enable the module"""
        self.enabled = True
        self.config.enabled = True
    
    def disable(self) -> None:
        """Disable the module"""
        self.enabled = False
        self.config.enabled = False
    
    def get_config(self) -> ModuleConfig:
        """Get current module configuration"""
        return self.config
    
    def update_settings(self, settings: Dict[str, Any]) -> None:
        """Update module settings"""
        self.config.settings.update(settings)