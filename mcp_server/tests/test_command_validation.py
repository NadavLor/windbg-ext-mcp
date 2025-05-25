#!/usr/bin/env python
"""
Unit tests for command validation in the refactored core.validation module.
"""
import unittest
import sys
import os

# Add parent directory to the path to import the modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.validation import validate_command, is_safe_for_automation

class TestCommandValidation(unittest.TestCase):
    """Test cases for WinDbg command validation."""

    def test_validate_empty_command(self):
        """Test that empty commands are rejected."""
        is_valid, error = validate_command("")
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        
        is_valid, error = validate_command("   ")
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_validate_safe_commands(self):
        """Test that safe commands are accepted."""
        for cmd in ["lm", "dt nt!_EPROCESS", "x nt!*", "!process 0 0", "r", 
                    "dd 0x1000", "dq 0x1000", "k", "!peb", "!teb"]:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")

    def test_validate_dangerous_commands(self):
        """Test that dangerous commands are rejected."""
        for cmd in ["q", "qq", "qd", ".kill", ".detach"]:
            is_valid, error = validate_command(cmd)
            self.assertFalse(is_valid, f"Command should be invalid: {cmd}")
            self.assertIsNotNone(error, f"Error expected for: {cmd}")

    def test_command_length_limit(self):
        """Test that very long commands are rejected."""
        long_cmd = "lm " + "a" * 5000  # Create a command longer than the limit
        is_valid, error = validate_command(long_cmd)
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        self.assertIn("too long", error)

    def test_process_command_validation(self):
        """Test validation of !process commands."""
        # Valid process commands
        valid_cmds = ["!process 0 0", "!process ffffc001e1234567 7"]
        for cmd in valid_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")

    def test_memory_command_validation(self):
        """Test validation of memory display commands."""
        # Valid memory commands
        valid_cmds = ["dd 0x1000", "db ffffc001e1234567", "dq ffffc001e1234567"]
        for cmd in valid_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")

    def test_breakpoint_command_validation(self):
        """Test validation of breakpoint commands."""
        # Valid breakpoint commands
        valid_cmds = ["bp 0x1000", "bp nt!NtCreateFile", "bl", "bc *", "bc 0", "be 1", "bd 2"]
        for cmd in valid_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")

    def test_execution_commands(self):
        """Test validation of execution control commands."""
        # These should be valid for both manual use and automation now
        execution_cmds = ["g", "p", "t", "gu"]
        for cmd in execution_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")
            
            # CHANGED: Now safe for automation to enable LLM debugging workflows
            self.assertTrue(is_safe_for_automation(cmd), f"Command should now be safe for automation: {cmd}")

    def test_safe_for_automation(self):
        """Test the automation safety check."""
        # Information commands should be safe for automation
        safe_cmds = ["lm", "dt nt!_EPROCESS", "x nt!*", "r", "dd 0x1000", "k"]
        for cmd in safe_cmds:
            self.assertTrue(is_safe_for_automation(cmd), f"Command should be safe for automation: {cmd}")
        
        # CHANGED: Execution control and breakpoint commands are now safe for automation
        now_safe_cmds = ["g", "p", "t", "gu", "bp 0x1000", "bc 0", "be 1", "bd 2"]
        for cmd in now_safe_cmds:
            self.assertTrue(is_safe_for_automation(cmd), f"Command should now be safe for automation: {cmd}")
        
        # Only genuinely dangerous commands should not be safe
        unsafe_cmds = ["q", "qq", ".kill", ".detach", ".restart"]
        for cmd in unsafe_cmds:
            self.assertFalse(is_safe_for_automation(cmd), f"Command should not be safe for automation: {cmd}")

    def test_extension_commands(self):
        """Test that extension commands are generally allowed."""
        extension_cmds = ["!process", "!thread", "!handle", "!object", "!idt"]
        for cmd in extension_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Extension command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")

    def test_breakpoint_automation_safety(self):
        """Test that breakpoint commands are now safe for automation."""
        breakpoint_cmds = ["bp nt!NtCreateFile", "bp 0x12345678", "bc *", "bc 0", "be 1", "bd 2", "bl"]
        for cmd in breakpoint_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Breakpoint command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")
            self.assertTrue(is_safe_for_automation(cmd), f"Breakpoint command should be safe for automation: {cmd}")

    def test_context_switch_automation_safety(self):
        """Test that context switch commands are now safe for automation."""
        context_cmds = [".thread", ".process"]
        for cmd in context_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Context command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")
            self.assertTrue(is_safe_for_automation(cmd), f"Context command should be safe for automation: {cmd}")

if __name__ == "__main__":
    unittest.main() 