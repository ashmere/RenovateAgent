"""
State management for RenovateAgent.

This package provides abstract state management with pluggable backends
for different deployment modes (serverless vs standalone).
"""

from .manager import InMemoryStateManager, StateManager, StateManagerFactory

__all__ = [
    "StateManager",
    "StateManagerFactory",
    "InMemoryStateManager",
]
