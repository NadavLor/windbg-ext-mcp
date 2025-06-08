"""
Tests for the unified execution system.

This module contains comprehensive tests to validate the refactoring
and ensure no regressions are introduced.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from core.execution import (
    UnifiedCommandExecutor, ExecutionContext, ExecutionResult, ExecutionMode,
    TimeoutResolver, get_executor, execute_command
)
from core.execution.strategies import (
    DirectStrategy, ResilientStrategy, OptimizedStrategy, AsyncStrategy
)
from core.execution.timeout_resolver import TimeoutCategory
from config import DebuggingMode


class TestTimeoutResolver:
    """Test the centralized timeout resolver."""
    
    def test_get_category_quick_commands(self):
        """Test categorization of quick commands."""
        resolver = TimeoutResolver()
        
        assert resolver.get_category("version") == TimeoutCategory.QUICK
        assert resolver.get_category("r") == TimeoutCategory.QUICK
        assert resolver.get_category("help") == TimeoutCategory.QUICK
        assert resolver.get_category(".effmach") == TimeoutCategory.QUICK
    
    def test_get_category_symbol_commands(self):
        """Test categorization of symbol commands."""
        resolver = TimeoutResolver()
        
        assert resolver.get_category(".reload") == TimeoutCategory.SYMBOLS
        assert resolver.get_category(".sympath") == TimeoutCategory.SYMBOLS
        assert resolver.get_category(".symfix") == TimeoutCategory.SYMBOLS
        
        # Extended commands should take precedence
        assert resolver.get_category(".reload /f") == TimeoutCategory.EXTENDED
        assert resolver.get_category(".reload -f") == TimeoutCategory.EXTENDED
    
    def test_get_category_bulk_commands(self):
        """Test categorization of bulk commands."""
        resolver = TimeoutResolver()
        
        assert resolver.get_category("lm") == TimeoutCategory.BULK
        assert resolver.get_category("!dlls") == TimeoutCategory.BULK
        assert resolver.get_category("!vm") == TimeoutCategory.BULK
    
    def test_get_category_caching(self):
        """Test that category results are cached."""
        resolver = TimeoutResolver()
        
        # First call
        category1 = resolver.get_category("version")
        # Second call should use cache
        category2 = resolver.get_category("version")
        
        assert category1 == category2 == TimeoutCategory.QUICK
        assert "version" in resolver._category_cache
    
    @patch('core.execution.timeout_resolver.get_timeout_for_command')
    def test_get_timeout_with_override(self, mock_get_timeout):
        """Test timeout resolution with category override."""
        mock_get_timeout.return_value = 30000
        resolver = TimeoutResolver()
        
        timeout = resolver.get_timeout("some_command", category_override="bulk")
        
        # Should call config with representative command for bulk category
        mock_get_timeout.assert_called_once()
        assert timeout == 30000
    
    def test_resolve_timeout_and_category(self):
        """Test resolving both timeout and category together."""
        resolver = TimeoutResolver()
        
        with patch('core.execution.timeout_resolver.get_timeout_for_command', return_value=5000):
            timeout_ms, category = resolver.resolve_timeout_and_category("version")
            
            assert timeout_ms == 5000
            assert category == "quick"


class TestExecutionStrategies:
    """Test the individual execution strategies."""
    
    @patch('core.execution.strategies.send_command')
    def test_direct_strategy_success(self, mock_send):
        """Test direct strategy successful execution."""
        mock_send.return_value = "Command output"
        strategy = DirectStrategy()
        
        context = ExecutionContext(command="version")
        result = strategy.execute(context)
        
        assert result.success
        assert result.result == "Command output"
        assert result.execution_mode == ExecutionMode.DIRECT
        assert result.timeout_category == "quick"
        mock_send.assert_called_once()
    
    @patch('core.execution.strategies.send_command')
    def test_direct_strategy_failure(self, mock_send):
        """Test direct strategy handling failures."""
        mock_send.side_effect = Exception("Connection failed")
        strategy = DirectStrategy()
        
        context = ExecutionContext(command="version")
        result = strategy.execute(context)
        
        assert not result.success
        assert "Connection failed" in result.error
        assert result.execution_mode == ExecutionMode.DIRECT
    
    @patch('core.execution.strategies.execute_with_retry')
    def test_resilient_strategy_success(self, mock_retry):
        """Test resilient strategy with retry logic."""
        mock_retry.return_value = "Command output after retry"
        strategy = ResilientStrategy()
        
        context = ExecutionContext(command="k", max_retries=3)
        result = strategy.execute(context)
        
        assert result.success
        assert result.result == "Command output after retry"
        assert result.execution_mode == ExecutionMode.RESILIENT
        mock_retry.assert_called_once()
    
    @patch('core.execution.strategies.send_command')
    def test_optimized_strategy_success(self, mock_send):
        """Test optimized strategy with direct execution."""
        mock_send.return_value = "Optimized output"
        strategy = OptimizedStrategy()
        
        context = ExecutionContext(command="lm")
        result = strategy.execute(context)
        
        assert result.success
        assert result.result == "Optimized output"
        assert result.execution_mode == ExecutionMode.OPTIMIZED
        assert result.optimization_level == "direct"
        mock_send.assert_called_once()


class TestUnifiedCommandExecutor:
    """Test the main unified command executor."""
    
    def test_executor_singleton(self):
        """Test that get_executor returns the same instance."""
        executor1 = get_executor()
        executor2 = get_executor()
        
        assert executor1 is executor2
    
    @patch('core.execution.strategies.send_command')
    def test_execute_basic_command(self, mock_send):
        """Test basic command execution."""
        mock_send.return_value = "Basic output"
        executor = UnifiedCommandExecutor()
        
        result = executor.execute("version")
        
        assert result.success
        assert result.result == "Basic output"
        assert "unified_execution" in result.metadata
        assert "strategy_type" in result.metadata
    
    def test_execute_empty_command(self):
        """Test handling of empty commands."""
        executor = UnifiedCommandExecutor()
        
        result = executor.execute("")
        
        assert not result.success
        assert "Parameter error" in result.error
        assert "empty" in result.error.lower()
    
    @patch('core.execution.strategies.send_command')
    def test_execute_with_different_strategies(self, mock_send):
        """Test executor chooses correct strategies."""
        mock_send.return_value = "Output"
        executor = UnifiedCommandExecutor()
        
        # Test different parameter combinations
        test_cases = [
            (True, True, False, "OptimizedStrategy"),    # resilient + optimize
            (True, False, False, "ResilientStrategy"),   # resilient only
            (False, True, False, "OptimizedStrategy"),   # optimize only
            (False, False, False, "DirectStrategy"),     # neither
            (False, False, True, "AsyncStrategy"),       # async mode
        ]
        
        for resilient, optimize, async_mode, expected_strategy in test_cases:
            result = executor.execute(
                "version",
                resilient=resilient,
                optimize=optimize,
                async_mode=async_mode
            )
            
            assert result.success
            assert expected_strategy in result.metadata["strategy_type"]
    
    @patch('core.execution.strategies.send_command')
    def test_execute_batch_success(self, mock_send):
        """Test batch execution with all successful commands."""
        mock_send.return_value = "Command output"
        executor = UnifiedCommandExecutor()
        
        commands = ["version", "r", "k"]
        result = executor.execute_batch(commands)
        
        assert result["success"]
        assert len(result["results"]) == 3
        assert result["summary"]["successful_commands"] == 3
        assert result["summary"]["failed_commands"] == 0
        assert result["summary"]["success_rate"] == 1.0
    
    @patch('core.execution.strategies.send_command')
    def test_execute_batch_with_failures(self, mock_send):
        """Test batch execution with some failures."""
        # First command succeeds, second fails, third succeeds
        mock_send.side_effect = ["Success", Exception("Failed"), "Success"]
        executor = UnifiedCommandExecutor()
        
        commands = ["version", "bad_command", "r"]
        result = executor.execute_batch(commands, stop_on_error=False)
        
        assert not result["success"]  # Overall batch failed due to one failure
        assert len(result["results"]) == 3
        assert result["summary"]["successful_commands"] == 2
        assert result["summary"]["failed_commands"] == 1
    
    @patch('core.execution.strategies.send_command')
    def test_execute_batch_stop_on_error(self, mock_send):
        """Test batch execution stops on first error when configured."""
        mock_send.side_effect = ["Success", Exception("Failed")]
        executor = UnifiedCommandExecutor()
        
        commands = ["version", "bad_command", "r"]
        result = executor.execute_batch(commands, stop_on_error=True)
        
        assert not result["success"]
        assert len(result["results"]) == 2  # Should stop after second command
        assert result["summary"]["execution_stopped"]
    
    def test_strategy_caching(self):
        """Test that strategies are cached properly."""
        executor = UnifiedCommandExecutor()
        
        # Create strategy through internal method
        strategy1 = executor._get_strategy(True, True, False)
        strategy2 = executor._get_strategy(True, True, False)
        
        # Should be the same instance
        assert strategy1 is strategy2
        assert len(executor._strategy_cache) == 1
    
    def test_clear_caches(self):
        """Test cache clearing functionality."""
        executor = UnifiedCommandExecutor()
        
        # Populate caches
        executor._get_strategy(True, True, False)
        executor.timeout_resolver.get_category("version")
        
        assert len(executor._strategy_cache) > 0
        assert len(executor.timeout_resolver._category_cache) > 0
        
        # Clear caches
        executor.clear_caches()
        
        assert len(executor._strategy_cache) == 0
        assert len(executor.timeout_resolver._category_cache) == 0


class TestBackwardCompatibility:
    """Test backward compatibility functions."""
    
    @patch('core.execution.strategies.send_command')
    def test_execute_command_unified(self, mock_send):
        """Test the convenience function for unified execution."""
        mock_send.return_value = "Output"
        
        result = execute_command("version", resilient=True, optimize=True)
        
        assert result.success
        assert result.result == "Output"
        assert isinstance(result, ExecutionResult)
    
# Legacy backward compatibility tests removed - unified system only


class TestIntegration:
    """Integration tests for the complete unified system."""
    
    @patch('core.execution.strategies.send_command')
    def test_complete_execution_flow(self, mock_send):
        """Test the complete execution flow from top to bottom."""
        # Setup mocks
        mock_send.return_value = "Optimized output"
        
        # Execute through the unified system
        result = execute_command(
            command="!analyze",
            resilient=True,
            optimize=True,
            timeout_category="analysis"
        )
        
        # Verify results
        assert result.success
        assert result.result == "Optimized output"
        assert result.execution_mode == ExecutionMode.OPTIMIZED
        assert result.timeout_category == "analysis"
        assert result.optimization_level == "direct"
        assert result.metadata["unified_execution"]
    
    def test_timeout_consistency(self):
        """Test that timeout resolution is consistent across the system."""
        resolver = TimeoutResolver()
        
        # Test various commands
        test_commands = [
            ("version", "quick"),
            ("k", "normal"),
            ("!analyze", "analysis"),
            ("lm", "bulk"),
            (".reload /f", "extended")
        ]
        
        for command, expected_category in test_commands:
            category = resolver.get_category_name(command)
            assert category == expected_category, f"Command '{command}' should be '{expected_category}', got '{category}'"


if __name__ == "__main__":
    pytest.main([__file__]) 