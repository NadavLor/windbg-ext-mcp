"""
Unified retry utilities for WinDbg MCP Server.

This module provides centralized retry logic and decorators to replace
the scattered retry implementations across different modules.
"""
import time
import logging
from typing import Callable, Any, Optional, Type, Union, Tuple
from functools import wraps
from datetime import datetime

from config import (
    DEFAULT_RETRY_CONFIG, get_retry_delay, DebuggingMode, 
    get_timeout_for_command
)

logger = logging.getLogger(__name__)

class RetryableError(Exception):
    """Base class for errors that should trigger retries."""
    pass

class NonRetryableError(Exception):
    """Base class for errors that should NOT trigger retries."""
    pass

def retry_on_failure(
    max_attempts: int = None,
    delay_base_ms: int = None,
    exponential_backoff: bool = None,
    retry_on: Union[Type[Exception], Tuple[Type[Exception], ...]] = (Exception,),
    no_retry_on: Union[Type[Exception], Tuple[Type[Exception], ...]] = (NonRetryableError,),
    before_retry: Optional[Callable[[int, Exception], None]] = None,
    after_failure: Optional[Callable[[int, Exception], None]] = None
):
    """
    Decorator for adding retry logic to functions.
    
    Args:
        max_attempts: Maximum number of retry attempts (uses config default if None)
        delay_base_ms: Base delay in milliseconds (uses config default if None)
        exponential_backoff: Use exponential backoff (uses config default if None)
        retry_on: Exception types that should trigger retries
        no_retry_on: Exception types that should NOT trigger retries
        before_retry: Callback called before each retry (attempt, exception)
        after_failure: Callback called after final failure (attempts, exception)
    
    Returns:
        Decorated function with retry logic
    """
    # Use config defaults if not specified
    if max_attempts is None:
        max_attempts = DEFAULT_RETRY_CONFIG.max_attempts
    if delay_base_ms is None:
        delay_base_ms = DEFAULT_RETRY_CONFIG.base_delay_ms
    if exponential_backoff is None:
        exponential_backoff = DEFAULT_RETRY_CONFIG.exponential_backoff
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                    
                except no_retry_on as e:
                    # Don't retry these exceptions
                    logger.debug(f"Non-retryable error in {func.__name__}: {e}")
                    raise
                    
                except retry_on as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:  # Not the last attempt
                        delay_seconds = get_retry_delay(
                            attempt, delay_base_ms, exponential_backoff
                        )
                        
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                        )
                        logger.info(f"Retrying in {delay_seconds:.1f} seconds...")
                        
                        # Call before_retry callback if provided
                        if before_retry:
                            try:
                                before_retry(attempt, e)
                            except Exception as callback_error:
                                logger.error(f"before_retry callback failed: {callback_error}")
                        
                        time.sleep(delay_seconds)
                        continue
                    else:
                        # Final attempt failed
                        break
            
            # All attempts failed
            logger.error(f"{func.__name__} failed after {max_attempts} attempts")
            
            # Call after_failure callback if provided
            if after_failure:
                try:
                    after_failure(max_attempts, last_exception)
                except Exception as callback_error:
                    logger.error(f"after_failure callback failed: {callback_error}")
            
            raise last_exception
            
        return wrapper
    return decorator

def execute_with_retry(
    func: Callable,
    *args,
    max_attempts: int = None,
    delay_base_ms: int = None,
    exponential_backoff: bool = None,
    retry_on: Union[Type[Exception], Tuple[Type[Exception], ...]] = (Exception,),
    no_retry_on: Union[Type[Exception], Tuple[Type[Exception], ...]] = (NonRetryableError,),
    **kwargs
) -> Any:
    """
    Execute a function with retry logic.
    
    This is a functional version of the retry_on_failure decorator for cases
    where you want to apply retry logic without decorating the function.
    
    Args:
        func: Function to execute
        *args: Arguments to pass to the function
        max_attempts: Maximum retry attempts
        delay_base_ms: Base delay in milliseconds
        exponential_backoff: Use exponential backoff
        retry_on: Exception types that should trigger retries
        no_retry_on: Exception types that should NOT trigger retries
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        Result of the function call
        
    Raises:
        The last exception if all retries fail
    """
    decorated_func = retry_on_failure(
        max_attempts=max_attempts,
        delay_base_ms=delay_base_ms,
        exponential_backoff=exponential_backoff,
        retry_on=retry_on,
        no_retry_on=no_retry_on
    )(func)
    
    return decorated_func(*args, **kwargs)

class RetryContext:
    """
    Context manager for retry operations with metrics tracking.
    """
    
    def __init__(self, operation_name: str, max_attempts: int = None):
        self.operation_name = operation_name
        self.max_attempts = max_attempts or DEFAULT_RETRY_CONFIG.max_attempts
        self.attempt_count = 0
        self.start_time = None
        self.success = False
        self.last_exception = None
        
    def __enter__(self):
        self.start_time = datetime.now()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = datetime.now() - self.start_time
        
        if exc_type is None:
            self.success = True
            logger.debug(
                f"Operation '{self.operation_name}' succeeded after "
                f"{self.attempt_count + 1} attempts in {duration.total_seconds():.2f}s"
            )
        else:
            self.last_exception = exc_val
            logger.error(
                f"Operation '{self.operation_name}' failed after "
                f"{self.attempt_count + 1} attempts in {duration.total_seconds():.2f}s: {exc_val}"
            )
        
        return False  # Don't suppress exceptions
    
    def attempt(self) -> bool:
        """
        Register an attempt and return whether retries should continue.
        
        Returns:
            True if this is not the final attempt, False if it is
        """
        self.attempt_count += 1
        return self.attempt_count < self.max_attempts

def create_timeout_retry_decorator(debugging_mode: DebuggingMode = DebuggingMode.LOCAL):
    """
    Create a retry decorator that uses smart timeout calculation.
    
    Args:
        debugging_mode: Current debugging mode for timeout optimization
        
    Returns:
        Configured retry decorator
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(command: str, *args, **kwargs):
            # Calculate optimal timeout for this command and mode
            if 'timeout_ms' not in kwargs:
                kwargs['timeout_ms'] = get_timeout_for_command(command, debugging_mode)
            
            # Apply retry logic
            return execute_with_retry(
                func, 
                command, 
                *args, 
                **kwargs,
                retry_on=(ConnectionError, TimeoutError),
                no_retry_on=(NonRetryableError, ValueError, TypeError)
            )
        return wrapper
    return decorator

# Pre-configured decorators for common scenarios
resilient_command = retry_on_failure(
    retry_on=(ConnectionError, TimeoutError),
    no_retry_on=(NonRetryableError, ValueError, TypeError)
)

network_resilient_command = retry_on_failure(
    max_attempts=5,  # More attempts for network issues
    exponential_backoff=True,
    retry_on=(ConnectionError, TimeoutError),
    no_retry_on=(NonRetryableError, ValueError, TypeError)
) 