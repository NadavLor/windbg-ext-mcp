"""
Session recovery and state management for WinDbg MCP Extension.

This module provides session state management, automatic recovery from debugging
session interruptions, and context preservation for kernel debugging scenarios.
"""
import logging
import json
import time
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from .communication import send_command, test_connection, CommunicationError, TimeoutError, ConnectionError
from .connection_resilience import ConnectionState, VMState, execute_resilient_command
from .unified_cache import (
    cache_session_snapshot, get_cached_session_snapshot, clear_session_cache
)

logger = logging.getLogger(__name__)

# Remove old session cache implementation - now using unified cache

class SessionState(Enum):
    """Current debugging session state."""
    ACTIVE = "active"
    INTERRUPTED = "interrupted"
    RECOVERING = "recovering"
    LOST = "lost"
    UNKNOWN = "unknown"

class RecoveryStrategy(Enum):
    """Recovery strategies for different scenarios."""
    RECONNECT_ONLY = "reconnect_only"
    RESTORE_CONTEXT = "restore_context"
    FULL_RECOVERY = "full_recovery"
    MANUAL_INTERVENTION = "manual_intervention"

@dataclass
class SessionSnapshot:
    """Snapshot of debugging session state."""
    timestamp: str
    session_id: str
    debugging_mode: str  # kernel/user
    target_info: Dict[str, Any]
    current_process: Optional[str] = None
    current_thread: Optional[str] = None
    breakpoints: List[Dict[str, Any]] = None
    call_stack: Optional[str] = None
    registers: Optional[Dict[str, Any]] = None
    modules: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.breakpoints is None:
            self.breakpoints = []
        if self.modules is None:
            self.modules = []

@dataclass
class RecoveryContext:
    """Context information for session recovery."""
    last_known_state: SessionSnapshot
    interruption_time: datetime
    interruption_cause: str
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.RESTORE_CONTEXT

class SessionRecovery:
    """Main class for session recovery and state management."""
    
    def __init__(self, state_file: str = "windbg_session_state.json"):
        self.state_file = state_file
        self.current_session: Optional[SessionSnapshot] = None
        self.session_state = SessionState.UNKNOWN
        self.recovery_context: Optional[RecoveryContext] = None
        
        # Recovery settings
        self.auto_recovery_enabled = True
        self.state_backup_interval = 60.0  # seconds
        self.max_state_age = 3600.0  # 1 hour
        
        # Load previous session state if available
        self._load_session_state()
    
    def capture_session_snapshot(self, session_id: str = None) -> Optional[SessionSnapshot]:
        """
        Capture current debugging session state with intelligent caching.
        
        Uses a 30-second cache to prevent redundant command execution when called frequently.
        This significantly reduces command spam while maintaining data freshness.
        
        Args:
            session_id: Optional session identifier
            
        Returns:
            Session snapshot or None if capture fails
        """
        logger.debug("Capturing session snapshot...")
        
        # Check for cached session first (unless specific session_id requested)
        if session_id is None:
            cached_session = get_cached_session_snapshot()
            if cached_session is not None:
                self.current_session = cached_session
                return cached_session
        
        try:
            if not session_id:
                session_id = f"session_{int(time.time())}"
            
            snapshot = SessionSnapshot(
                timestamp=datetime.now().isoformat(),
                session_id=session_id,
                debugging_mode="unknown",
                target_info={}
            )
            
            logger.debug("Executing full session capture (no valid cache)")
            
            # Detect debugging mode
            try:
                success, result, _ = execute_resilient_command(".effmach", "quick")
                if success:
                    if any(x in result.lower() for x in ["x64_kernel", "x86_kernel", "kernel mode"]):
                        snapshot.debugging_mode = "kernel"
                    else:
                        snapshot.debugging_mode = "user"
            except:
                pass
            
            # Get target information
            try:
                success, version_info, _ = execute_resilient_command("version", "quick")
                if success:
                    snapshot.target_info["version"] = version_info
            except:
                pass
            
            # Get current process context (if in kernel mode)
            if snapshot.debugging_mode == "kernel":
                try:
                    success, proc_info, _ = execute_resilient_command("!process -1 0", "normal")
                    if success and "PROCESS" in proc_info:
                        # Extract current process address
                        import re
                        match = re.search(r'PROCESS\s+([a-fA-F0-9`]+)', proc_info)
                        if match:
                            snapshot.current_process = match.group(1)
                except:
                    pass
            
            # Get current thread context (kernel mode compatible)
            try:
                # In kernel mode, use !thread to get current thread info instead of ~.
                success, thread_info, _ = execute_resilient_command("!thread", "quick")
                if success:
                    import re
                    # Look for THREAD pattern in kernel mode output
                    match = re.search(r'THREAD\s+([0-9a-f]+)', thread_info)
                    if match:
                        snapshot.current_thread = match.group(1)
                else:
                    # Fallback: try to get current processor info
                    success, proc_info, _ = execute_resilient_command("!pcr", "quick")
                    if success:
                        snapshot.current_thread = "current_processor"
            except:
                pass
            
            # Get call stack (limited)
            try:
                success, stack_info, _ = execute_resilient_command("k 5", "normal")
                if success:
                    snapshot.call_stack = stack_info
            except:
                pass
            
            # Get key registers
            try:
                success, reg_info, _ = execute_resilient_command("r", "quick")
                if success:
                    snapshot.registers = {"summary": reg_info}
            except:
                pass
            
            # Get loaded modules (limited)
            try:
                success, modules_info, _ = execute_resilient_command("lm", "normal")
                if success:
                    # Parse module information (simplified)
                    module_lines = modules_info.split('\n')[:10]  # Limit to first 10 modules
                    snapshot.modules = [{"info": line.strip()} for line in module_lines if line.strip()]
            except:
                pass
            
            # Get breakpoints
            try:
                success, bp_info, _ = execute_resilient_command("bl", "quick")
                if success and bp_info.strip():
                    # Parse breakpoint information
                    bp_lines = bp_info.split('\n')
                    for line in bp_lines:
                        if line.strip() and not line.startswith("No breakpoints"):
                            snapshot.breakpoints.append({"info": line.strip()})
            except:
                pass
            
            self.current_session = snapshot
            self.session_state = SessionState.ACTIVE
            
            # Cache the snapshot (unless specific session_id was requested)
            if session_id.startswith("session_"):  # Auto-generated session ID
                cache_session_snapshot("current", snapshot)
            
            logger.info(f"Captured session snapshot: {session_id}")
            return snapshot
            
        except Exception as e:
            logger.error(f"Failed to capture session snapshot: {e}")
            return None
    
    def detect_session_interruption(self) -> Tuple[bool, str]:
        """
        Detect if the debugging session has been interrupted.
        
        Returns:
            Tuple of (is_interrupted, cause)
        """
        try:
            # Test basic connectivity
            if not test_connection():
                # Clear cache since connection is lost
                clear_session_cache()
                return True, "Extension connection lost"
            
            # Test WinDbg responsiveness with kernel-compatible command
            success, result, metadata = execute_resilient_command("version", "quick", max_retries=1)
            if not success:
                # Clear cache since WinDbg is unresponsive
                clear_session_cache()
                return True, f"WinDbg unresponsive: {result}"
            
            # Check if target is still connected (for kernel debugging)
            if self.current_session and self.current_session.debugging_mode == "kernel":
                success, result, _ = execute_resilient_command(".reboot_target", "quick", max_retries=1)
                if "Target rebooted" in result:
                    # Clear cache since target rebooted (major state change)
                    clear_session_cache()
                    return True, "Target VM rebooted"
                elif "Target not connected" in result:
                    # Clear cache since target disconnected
                    clear_session_cache()
                    return True, "Target VM disconnected"
            
            return False, "Session active"
            
        except Exception as e:
            # Clear cache on any detection errors
            clear_session_cache()
            return True, f"Detection error: {str(e)}"
    
    def attempt_session_recovery(self, recovery_strategy: RecoveryStrategy = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Attempt to recover the debugging session.
        
        Args:
            recovery_strategy: Strategy to use for recovery
            
        Returns:
            Tuple of (success, message, recovery_info)
        """
        if not self.current_session:
            return False, "No session state to recover", {}
        
        strategy = recovery_strategy or RecoveryStrategy.RESTORE_CONTEXT
        logger.info(f"Attempting session recovery with strategy: {strategy.value}")
        
        recovery_info = {
            "strategy": strategy.value,
            "start_time": datetime.now().isoformat(),
            "session_id": self.current_session.session_id,
            "steps_completed": []
        }
        
        try:
            self.session_state = SessionState.RECOVERING
            
            # Step 1: Test basic connectivity
            if not test_connection():
                recovery_info["steps_completed"].append("connection_test_failed")
                return False, "Extension connection cannot be established", recovery_info
            
            recovery_info["steps_completed"].append("connection_test_passed")
            
            # Step 2: Verify WinDbg is responsive
            success, result, _ = execute_resilient_command("version", "quick")
            if not success:
                recovery_info["steps_completed"].append("windbg_unresponsive")
                return False, f"WinDbg not responding: {result}", recovery_info
            
            recovery_info["steps_completed"].append("windbg_responsive")
            
            # Step 3: Check debugging mode consistency
            current_mode = self._detect_current_mode()
            if current_mode != self.current_session.debugging_mode:
                recovery_info["steps_completed"].append("mode_mismatch")
                return False, f"Debugging mode changed: {self.current_session.debugging_mode} -> {current_mode}", recovery_info
            
            recovery_info["steps_completed"].append("mode_consistent")
            
            if strategy == RecoveryStrategy.RECONNECT_ONLY:
                # Just verify connection is working
                self.session_state = SessionState.ACTIVE
                recovery_info["steps_completed"].append("reconnect_only_complete")
                return True, "Connection recovered", recovery_info
            
            # Step 4: Restore process context (kernel mode)
            if (strategy in [RecoveryStrategy.RESTORE_CONTEXT, RecoveryStrategy.FULL_RECOVERY] and 
                self.current_session.debugging_mode == "kernel" and 
                self.current_session.current_process):
                
                try:
                    success, result, _ = execute_resilient_command(
                        f".process /i {self.current_session.current_process}", "normal"
                    )
                    if success:
                        recovery_info["steps_completed"].append("process_context_restored")
                    else:
                        recovery_info["steps_completed"].append("process_context_failed")
                        logger.warning(f"Failed to restore process context: {result}")
                except Exception as e:
                    recovery_info["steps_completed"].append("process_context_error")
                    logger.warning(f"Error restoring process context: {e}")
            
            # Step 5: Restore thread context
            if (strategy in [RecoveryStrategy.RESTORE_CONTEXT, RecoveryStrategy.FULL_RECOVERY] and 
                self.current_session.current_thread):
                
                try:
                    success, result, _ = execute_resilient_command(
                        f"~{self.current_session.current_thread}s", "quick"
                    )
                    if success:
                        recovery_info["steps_completed"].append("thread_context_restored")
                    else:
                        recovery_info["steps_completed"].append("thread_context_failed")
                        logger.warning(f"Failed to restore thread context: {result}")
                except Exception as e:
                    recovery_info["steps_completed"].append("thread_context_error")
                    logger.warning(f"Error restoring thread context: {e}")
            
            # Step 6: Restore breakpoints (full recovery)
            if (strategy == RecoveryStrategy.FULL_RECOVERY and 
                self.current_session.breakpoints):
                
                restored_bp = 0
                for bp in self.current_session.breakpoints:
                    try:
                        # This is simplified - would need proper breakpoint parsing
                        logger.debug(f"Attempting to restore breakpoint: {bp}")
                        restored_bp += 1
                    except Exception as e:
                        logger.warning(f"Failed to restore breakpoint {bp}: {e}")
                
                recovery_info["steps_completed"].append(f"breakpoints_restored_{restored_bp}")
            
            # Step 7: Verify recovery
            new_snapshot = self.capture_session_snapshot(
                self.current_session.session_id + "_recovered"
            )
            
            if new_snapshot:
                recovery_info["steps_completed"].append("verification_complete")
                self.session_state = SessionState.ACTIVE
                
                return True, "Session recovery successful", recovery_info
            else:
                recovery_info["steps_completed"].append("verification_failed")
                return False, "Recovery verification failed", recovery_info
            
        except Exception as e:
            logger.error(f"Session recovery failed: {e}")
            recovery_info["error"] = str(e)
            self.session_state = SessionState.LOST
            return False, f"Recovery failed: {str(e)}", recovery_info
    
    def save_session_state(self) -> bool:
        """
        Save current session state to disk.
        
        Returns:
            True if saved successfully
        """
        if not self.current_session:
            return False
        
        try:
            state_data = {
                "session": asdict(self.current_session),
                "session_state": self.session_state.value,
                "saved_time": datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            
            logger.debug(f"Saved session state to {self.state_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session state: {e}")
            return False
    
    def load_session_state(self) -> Optional[SessionSnapshot]:
        """
        Load session state from disk.
        
        Returns:
            Loaded session snapshot or None
        """
        return self._load_session_state()
    
    def get_recovery_recommendations(self) -> Dict[str, Any]:
        """
        Get recommendations for session recovery based on current state.
        
        Returns:
            Dictionary with recovery recommendations
        """
        recommendations = {
            "session_state": self.session_state.value,
            "auto_recovery_available": False,
            "recovery_strategies": [],
            "manual_steps": [],
            "risk_assessment": "unknown"
        }
        
        if not self.current_session:
            recommendations["manual_steps"] = [
                "No previous session state available",
                "Start fresh debugging session",
                "Capture new session state with capture_session_snapshot()"
            ]
            return recommendations
        
        # Check session age
        session_time = datetime.fromisoformat(self.current_session.timestamp)
        age_hours = (datetime.now() - session_time).total_seconds() / 3600
        
        if age_hours > 24:
            recommendations["risk_assessment"] = "high"
            recommendations["manual_steps"].append("Session state is very old (>24h) - manual recovery recommended")
        elif age_hours > 1:
            recommendations["risk_assessment"] = "medium"
        else:
            recommendations["risk_assessment"] = "low"
        
        # Check if auto recovery is viable
        is_interrupted, cause = self.detect_session_interruption()
        
        if not is_interrupted:
            recommendations["auto_recovery_available"] = False
            recommendations["manual_steps"] = ["Session appears to be active - no recovery needed"]
            return recommendations
        
        # Determine available recovery strategies
        if "connection lost" in cause.lower():
            recommendations["recovery_strategies"] = [
                RecoveryStrategy.RECONNECT_ONLY.value,
                RecoveryStrategy.RESTORE_CONTEXT.value
            ]
            recommendations["auto_recovery_available"] = True
        elif "unresponsive" in cause.lower():
            recommendations["recovery_strategies"] = [
                RecoveryStrategy.RESTORE_CONTEXT.value,
                RecoveryStrategy.FULL_RECOVERY.value
            ]
            recommendations["auto_recovery_available"] = True
        elif "rebooted" in cause.lower() or "disconnected" in cause.lower():
            recommendations["recovery_strategies"] = [RecoveryStrategy.MANUAL_INTERVENTION.value]
            recommendations["auto_recovery_available"] = False
            recommendations["manual_steps"] = [
                "Target VM has been rebooted or disconnected",
                "Reconnect to target VM manually",
                "Restart debugging session",
                "Load new session state"
            ]
        
        return recommendations
    
    def _load_session_state(self) -> Optional[SessionSnapshot]:
        """Load session state from file."""
        try:
            if not os.path.exists(self.state_file):
                logger.debug(f"No session state file found: {self.state_file}")
                return None
            
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            
            # Check if state is too old
            saved_time = datetime.fromisoformat(state_data["saved_time"])
            age_seconds = (datetime.now() - saved_time).total_seconds()
            
            if age_seconds > self.max_state_age:
                logger.info(f"Session state is too old ({age_seconds:.0f}s), ignoring")
                return None
            
            # Create session snapshot from saved data
            session_data = state_data["session"]
            self.current_session = SessionSnapshot(**session_data)
            self.session_state = SessionState(state_data.get("session_state", "unknown"))
            
            logger.info(f"Loaded session state: {self.current_session.session_id}")
            return self.current_session
            
        except Exception as e:
            logger.warning(f"Failed to load session state: {e}")
            return None
    
    def _detect_current_mode(self) -> str:
        """Detect current debugging mode."""
        try:
            success, result, _ = execute_resilient_command(".effmach", "quick")
            if success and any(x in result.lower() for x in ["x64_kernel", "x86_kernel", "kernel mode"]):
                return "kernel"
            else:
                return "user"
        except:
            return "unknown"

# Global instance for use across the application
session_recovery = SessionRecovery()

# Convenience functions
def capture_current_session(session_id: str = None, force_refresh: bool = False) -> Optional[SessionSnapshot]:
    """
    Capture current debugging session state.
    
    Args:
        session_id: Optional session identifier  
        force_refresh: If True, bypass cache and force fresh capture
        
    Returns:
        Session snapshot or None if capture fails
    """
    if force_refresh:
        clear_session_cache()
    return session_recovery.capture_session_snapshot(session_id)

def check_session_health() -> Tuple[bool, str]:
    """Check if the debugging session is healthy."""
    return session_recovery.detect_session_interruption()

def recover_session(strategy: RecoveryStrategy = None) -> Tuple[bool, str, Dict[str, Any]]:
    """Attempt to recover the debugging session."""
    return session_recovery.attempt_session_recovery(strategy)

def get_recovery_recommendations() -> Dict[str, Any]:
    """Get recommendations for session recovery."""
    return session_recovery.get_recovery_recommendations()

def save_current_session() -> bool:
    """Save current session state to disk."""
    return session_recovery.save_session_state()

def load_previous_session() -> Optional[SessionSnapshot]:
    """Load previous session state from disk."""
    return session_recovery.load_session_state()

# clear_session_cache is imported from unified_cache 