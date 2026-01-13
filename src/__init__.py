"""
Voice Agent Package
Modular real-time voice conversation system
"""

__version__ = "1.0.0"
__author__ = "Your Name"

from .orchestrator import VoiceOrchestrator
from .config import validate_config

__all__ = ['VoiceOrchestrator', 'validate_config']

