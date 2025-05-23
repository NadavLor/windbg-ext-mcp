"""
Lightweight context management for WinDbg MCP Extension.

This module provides simple context tracking and switching for process
and thread contexts during debugging operations.
"""
import logging
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DebugContext:
    """Represents a debugging context state."""
    process_address: Optional[str] = None
    thread_address: Optional[str] = None
    
    def __bool__(self) -> bool:
        """Return True if any context is saved."""
        return bool(self.process_address or self.thread_address)

class ContextManager:
    """
    Simple context manager for debugging sessions.
    
    Maintains a stack of contexts to allow nested context switches
    with proper restoration.
    """
    
    def __init__(self):
        self._context_stack = []
        self._current_context = DebugContext()
    
    def save_current_context(self, communication_func) -> DebugContext:
        """
        Save the current debugging context.
        
        Args:
            communication_func: Function to send commands (e.g., send_command)
            
        Returns:
            The saved context
        """
        context = DebugContext()
        
        try:
            # Get current process context
            process_result = communication_func(".process")
            if process_result and "Implicit process is" in process_result:
                match = re.search(r'Implicit process is ([0-9a-fA-F`]+)', process_result)
                if match:
                    context.process_address = match.group(1)
                    logger.debug(f"Saved process context: {context.process_address}")
            
            # Get current thread context
            thread_result = communication_func(".thread")
            if thread_result and "Current thread is" in thread_result:
                match = re.search(r'Current thread is ([0-9a-fA-F`]+)', thread_result)
                if match:
                    context.thread_address = match.group(1)
                    logger.debug(f"Saved thread context: {context.thread_address}")
                    
        except Exception as e:
            logger.warning(f"Failed to save context: {e}")
            
        self._current_context = context
        return context
    
    def push_context(self, communication_func) -> DebugContext:
        """
        Push the current context onto the stack and save new context.
        
        Args:
            communication_func: Function to send commands
            
        Returns:
            The saved context
        """
        # Save current context and push to stack
        saved_context = self.save_current_context(communication_func)
        if saved_context:
            self._context_stack.append(saved_context)
            logger.debug(f"Pushed context to stack (depth: {len(self._context_stack)})")
        
        return saved_context
    
    def pop_context(self, communication_func) -> bool:
        """
        Pop and restore the most recent context from the stack.
        
        Args:
            communication_func: Function to send commands
            
        Returns:
            True if context was restored, False if stack was empty
        """
        if not self._context_stack:
            logger.debug("No context to pop from stack")
            return False
        
        context = self._context_stack.pop()
        success = self.restore_context(context, communication_func)
        
        if success:
            logger.debug(f"Popped and restored context (stack depth: {len(self._context_stack)})")
        
        return success
    
    def restore_context(self, context: DebugContext, communication_func) -> bool:
        """
        Restore a specific debugging context.
        
        Args:
            context: The context to restore
            communication_func: Function to send commands
            
        Returns:
            True if restoration was successful, False otherwise
        """
        if not context:
            return False
        
        success = True
        
        try:
            # Restore process context if available
            if context.process_address:
                logger.debug(f"Restoring process context to: {context.process_address}")
                result = communication_func(f".process /r /p {context.process_address}")
                if not result or "failed" in result.lower():
                    logger.warning(f"Failed to restore process context to {context.process_address}")
                    success = False
            
            # Restore thread context if available
            if context.thread_address:
                logger.debug(f"Restoring thread context to: {context.thread_address}")
                result = communication_func(f".thread {context.thread_address}")
                if not result or "failed" in result.lower():
                    logger.warning(f"Failed to restore thread context to {context.thread_address}")
                    success = False
                    
        except Exception as e:
            logger.error(f"Exception during context restoration: {e}")
            success = False
        
        if success:
            self._current_context = context
            
        return success
    
    def switch_to_process(self, process_address: str, communication_func) -> bool:
        """
        Switch to a specific process context.
        
        Args:
            process_address: The process address to switch to
            communication_func: Function to send commands
            
        Returns:
            True if switch was successful, False otherwise
        """
        try:
            logger.debug(f"Switching to process: {process_address}")
            result = communication_func(f".process /r /p {process_address}")
            
            if result and "Implicit process is now" in result:
                self._current_context.process_address = process_address
                return True
            else:
                logger.warning(f"Failed to switch to process {process_address}: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Exception switching to process {process_address}: {e}")
            return False
    
    def switch_to_thread(self, thread_address: str, communication_func) -> bool:
        """
        Switch to a specific thread context.
        
        Args:
            thread_address: The thread address to switch to
            communication_func: Function to send commands
            
        Returns:
            True if switch was successful, False otherwise
        """
        try:
            logger.debug(f"Switching to thread: {thread_address}")
            result = communication_func(f".thread {thread_address}")
            
            if result and "Current thread is now" in result:
                self._current_context.thread_address = thread_address
                return True
            else:
                logger.warning(f"Failed to switch to thread {thread_address}: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Exception switching to thread {thread_address}: {e}")
            return False
    
    def get_current_context(self) -> DebugContext:
        """
        Get the current context.
        
        Returns:
            The current debugging context
        """
        return self._current_context
    
    def clear_stack(self):
        """Clear the context stack."""
        self._context_stack.clear()
        logger.debug("Cleared context stack")
    
    def stack_depth(self) -> int:
        """
        Get the current stack depth.
        
        Returns:
            Number of contexts in the stack
        """
        return len(self._context_stack)

# Global context manager instance
_context_manager = ContextManager()

def get_context_manager() -> ContextManager:
    """
    Get the global context manager instance.
    
    Returns:
        The global ContextManager instance
    """
    return _context_manager

# Convenience functions for common operations

def with_saved_context(communication_func):
    """
    Decorator to execute a function with saved context that gets restored afterwards.
    
    Args:
        communication_func: Function to send commands
        
    Returns:
        Decorator function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            context_mgr = get_context_manager()
            saved_context = context_mgr.push_context(communication_func)
            
            try:
                return func(*args, **kwargs)
            finally:
                if saved_context:
                    context_mgr.pop_context(communication_func)
        
        return wrapper
    return decorator

def save_context(communication_func) -> DebugContext:
    """
    Save the current debugging context.
    
    Args:
        communication_func: Function to send commands
        
    Returns:
        The saved context
    """
    return get_context_manager().save_current_context(communication_func)

def restore_context(context: DebugContext, communication_func) -> bool:
    """
    Restore a debugging context.
    
    Args:
        context: The context to restore
        communication_func: Function to send commands
        
    Returns:
        True if successful, False otherwise
    """
    return get_context_manager().restore_context(context, communication_func) 