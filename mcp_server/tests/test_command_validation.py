#!/usr/bin/env python
"""
Unit tests for command validation in windbg_api.py.
"""
import unittest
import sys
import os

# Add parent directory to the path to import the modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from commands.windbg_api import validate_command, CommandCategory, get_command_category

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

    def test_validate_restricted_commands(self):
        """Test that restricted commands are rejected."""
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
        
        # Invalid process address
        is_valid, error = validate_command("!process xyz 7")
        self.assertTrue(is_valid)  # Let handler do extra validation
        
    def test_memory_command_validation(self):
        """Test validation of memory display commands."""
        # Valid memory commands
        valid_cmds = ["dd 0x1000", "db ffffc001e1234567", "dq ffffc001e1234567 L100"]
        for cmd in valid_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")
        
        # Memory command with non-standard format (logged but allowed)
        is_valid, error = validate_command("dd @$peb+10 L10")
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_breakpoint_command_validation(self):
        """Test validation of breakpoint commands."""
        # Valid breakpoint commands
        valid_cmds = ["bp 0x1000", "bp nt!NtCreateFile", "bl", "bc *", "bc 0", "be 1", "bd 2"]
        for cmd in valid_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")

    def test_command_category_determination(self):
        """Test that command categories are correctly determined."""
        self.assertEqual(CommandCategory.MEMORY, get_command_category("dd 0x1000"))
        self.assertEqual(CommandCategory.EXECUTION, get_command_category("g"))
        self.assertEqual(CommandCategory.BREAKPOINT, get_command_category("bp 0x1000"))
        self.assertEqual(CommandCategory.PROCESS, get_command_category("!process 0 0"))
        self.assertEqual(CommandCategory.MODULE, get_command_category("lm"))
        self.assertEqual(CommandCategory.EXTENSION, get_command_category("!handle"))
        self.assertEqual(CommandCategory.SYSTEM, get_command_category(".echo test"))
        self.assertEqual(CommandCategory.UNKNOWN, get_command_category("unknown_command"))

    def test_meta_command_validation(self):
        """Test validation of meta commands."""
        # Valid meta commands
        valid_cmds = [".echo test", ".printf \"%d\\n\", 1"]
        for cmd in valid_cmds:
            is_valid, error = validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(error, f"No error expected for: {cmd}")
            
        # Potentially dangerous meta commands
        dangerous_cmds = [".dump", ".dumpcab", ".server", ".load", ".kill"]
        for cmd in dangerous_cmds:
            is_valid, error = validate_command(cmd)
            self.assertFalse(is_valid, f"Command should be invalid: {cmd}")
            self.assertIsNotNone(error, f"Error expected for: {cmd}")

if __name__ == "__main__":
    unittest.main() 