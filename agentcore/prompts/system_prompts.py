"""
Prompt Management System for Strava AI Boost

Centralizes all prompts for AgentCore agents and Bedrock fallbacks.
Provides dynamic loading and validation of prompt files.
"""

import os
from typing import Dict, Optional
from pathlib import Path

class PromptManager:
    """Manages loading and caching of prompt files for agents and fallbacks"""
    
    def __init__(self, prompts_dir: Optional[str] = None):
        if prompts_dir is None:
            # Default to agentcore/prompts directory
            self.prompts_dir = Path(__file__).parent
        else:
            self.prompts_dir = Path(prompts_dir)
        
        self._prompt_cache = {}
    
    def load_prompt(self, prompt_name: str) -> str:
        """
        Load a prompt file with caching
        
        Args:
            prompt_name: Name of the prompt file (without .md extension)
            
        Returns:
            Prompt content as string
        """
        if prompt_name in self._prompt_cache:
            return self._prompt_cache[prompt_name]
        
        prompt_file = self.prompts_dir / f"{prompt_name}.md"
        
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Cache the content
        self._prompt_cache[prompt_name] = content
        return content
    
    def get_system_prompt(self, agent_type: str) -> str:
        """
        Get system prompt for specific agent type
        
        Args:
            agent_type: 'campus_coach' or 'content_generation'
            
        Returns:
            System prompt content
        """
        prompt_mapping = {
            'campus_coach': 'campus_coach_agent_prompt',
            'content_generation': 'content_generation_agent_prompt'
        }
        
        if agent_type not in prompt_mapping:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        return self.load_prompt(prompt_mapping[agent_type])
    
    def get_bedrock_prompt(self, agent_type: str, action: str = None) -> str:
        """
        Get optimized prompt for direct Bedrock fallback
        
        Args:
            agent_type: 'campus_coach' or 'content_generation'
            action: Optional specific action for the prompt
            
        Returns:
            Bedrock-optimized prompt
        """
        base_prompt = self.get_system_prompt(agent_type)
        
        # Add Bedrock-specific optimizations
        bedrock_prefix = """
BEDROCK DIRECT MODE: You are operating in direct Bedrock mode without AgentCore tools.
Provide complete responses based on the input data without tool calls.
Return structured JSON responses when appropriate.

"""
        
        return bedrock_prefix + base_prompt
    
    def clear_cache(self):
        """Clear the prompt cache to force reload"""
        self._prompt_cache.clear()

# Global prompt manager instance
prompt_manager = PromptManager()

# Convenience functions for easy access
def get_campus_coach_prompt() -> str:
    """Get Campus Coach agent system prompt"""
    return prompt_manager.get_system_prompt('campus_coach')

def get_content_generation_prompt() -> str:
    """Get Content Generation agent system prompt"""
    return prompt_manager.get_system_prompt('content_generation')

def get_bedrock_campus_coach_prompt() -> str:
    """Get Campus Coach prompt optimized for direct Bedrock use"""
    return prompt_manager.get_bedrock_prompt('campus_coach')

def get_bedrock_content_generation_prompt() -> str:
    """Get Content Generation prompt optimized for direct Bedrock use"""
    return prompt_manager.get_bedrock_prompt('content_generation')