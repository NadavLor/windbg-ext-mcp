"""
Command optimization and batching for WinDbg commands.

This module provides intelligent command batching, caching decisions,
and command sequence optimization for better performance.
"""
import logging
import threading
from typing import List, Tuple

logger = logging.getLogger(__name__)

class CommandOptimizer:
    """Optimizes command execution and batching."""
    
    def __init__(self):
        self.batch_size = 5
        self.batch_timeout = 1.0  # seconds
        self._pending_commands = []
        self._batch_lock = threading.Lock()
    
    def should_cache_command(self, command: str) -> Tuple[bool, int]:
        """Determine if command should be cached and for how long."""
        command_lower = command.lower().strip()
        
        # Commands that change rarely - cache longer
        long_cache_commands = [
            "version", "lm", ".effmach", "!pcr"
        ]
        
        # Commands that are expensive but stable
        medium_cache_commands = [
            "!process 0 0", "!handle 0 f", "dt nt!_eprocess"
        ]
        
        # Commands that change frequently - short cache or no cache
        no_cache_commands = [
            "r", "k", "~", "!thread", "g", "p", "t"
        ]
        
        for cmd in long_cache_commands:
            if cmd in command_lower:
                return True, 1800  # 30 minutes
        
        for cmd in medium_cache_commands:
            if cmd in command_lower:
                return True, 300  # 5 minutes
        
        for cmd in no_cache_commands:
            if cmd in command_lower:
                return False, 0
        
        # Default: short cache for most commands
        return True, 60  # 1 minute
    
    def optimize_command_sequence(self, commands: List[str]) -> List[List[str]]:
        """Optimize a sequence of commands for batching."""
        if len(commands) <= 1:
            return [commands]
        
        # Group commands by type and priority
        batches = []
        current_batch = []
        
        for command in commands:
            command_lower = command.lower().strip()
            
            # Commands that should run individually
            individual_commands = ["g", "p", "t", "!analyze"]
            
            if any(cmd in command_lower for cmd in individual_commands):
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                batches.append([command])
            else:
                current_batch.append(command)
                
                # Batch size limit
                if len(current_batch) >= self.batch_size:
                    batches.append(current_batch)
                    current_batch = []
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    def is_expensive_command(self, command: str) -> bool:
        """Determine if a command is computationally expensive."""
        command_lower = command.lower().strip()
        
        expensive_commands = [
            "!process 0 0",   # List all processes
            "!handle 0 f",    # List all handles
            "!vm",            # Virtual memory analysis
            "!poolused",      # Pool usage analysis
            "!verifier",      # Driver verifier
            "!analyze"        # Crash analysis
        ]
        
        return any(cmd in command_lower for cmd in expensive_commands)
    
    def get_command_category(self, command: str) -> str:
        """Categorize command for optimization purposes."""
        command_lower = command.lower().strip()
        
        if any(cmd in command_lower for cmd in ["r", "k", "~"]):
            return "context"  # Context-dependent commands
        elif any(cmd in command_lower for cmd in ["lm", "version", ".effmach"]):
            return "static"   # Static information commands  
        elif any(cmd in command_lower for cmd in ["!process", "!thread", "!handle"]):
            return "analysis"  # Analysis commands
        elif any(cmd in command_lower for cmd in ["g", "p", "t"]):
            return "execution"  # Execution control
        else:
            return "general"   # General commands
    
    def should_parallelize_commands(self, commands: List[str]) -> bool:
        """Determine if commands can be executed in parallel."""
        # Only allow parallelization for read-only, independent commands
        safe_for_parallel = True
        
        for command in commands:
            command_lower = command.lower().strip()
            
            # Execution control commands must be sequential
            if any(cmd in command_lower for cmd in ["g", "p", "t", "!analyze"]):
                safe_for_parallel = False
                break
            
            # Commands that modify state
            if any(cmd in command_lower for cmd in ["ed", "eb", "ew", "bp", "bc"]):
                safe_for_parallel = False
                break
        
        return safe_for_parallel and len(commands) > 1 