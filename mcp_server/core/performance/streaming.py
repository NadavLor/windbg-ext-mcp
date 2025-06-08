"""
Streaming handler for large WinDbg command outputs.

This module provides chunked streaming of large command results to prevent
memory issues and improve responsiveness for huge outputs.
"""
import logging
import time
from typing import Dict, Any, Generator

from core.communication import send_command

logger = logging.getLogger(__name__)

class StreamingHandler:
    """Handles streaming of large command outputs."""
    
    def __init__(self, chunk_size: int = 4096):
        self.chunk_size = chunk_size
    
    def stream_large_output(self, command: str, timeout_category: str = "bulk") -> Generator[Dict[str, Any], None, None]:
        """Stream large command output in chunks."""
        try:
            # For very large operations, we'll execute and yield progress
            yield {
                "type": "progress",
                "message": f"Executing command: {command}",
                "progress": 0.1
            }
            
            # Execute the command
            try:
                # Use centralized timeout resolution (fixes hardcoded timeout bug)
                from core.execution.timeout_resolver import resolve_timeout
                from config import DebuggingMode
                
                # Create a representative command for the timeout category
                category_commands = {
                    "quick": "version",
                    "normal": "k",
                    "slow": "!analyze", 
                    "bulk": "lm",
                    "analysis": "!analyze -v"
                }
                representative_command = category_commands.get(timeout_category, "k")
                timeout_ms = resolve_timeout(representative_command, DebuggingMode.VM_NETWORK)
                
                result = send_command(command, timeout_ms=timeout_ms)
                metadata = {"cached": False, "streaming": True}
            except Exception as e:
                yield {
                    "type": "error", 
                    "message": str(e),
                    "metadata": {"error": True}
                }
                return
            
            # Determine if we should stream the result
            result_size = len(result.encode('utf-8'))
            
            if result_size < 50000:  # < 50KB, send as single chunk
                yield {
                    "type": "complete",
                    "data": result,
                    "metadata": metadata,
                    "size": result_size
                }
            else:
                # Stream in chunks
                lines = result.split('\n')
                total_lines = len(lines)
                chunk_lines = max(10, total_lines // 20)  # ~20 chunks
                
                for i in range(0, total_lines, chunk_lines):
                    chunk = '\n'.join(lines[i:i + chunk_lines])
                    progress = min(1.0, (i + chunk_lines) / total_lines)
                    
                    yield {
                        "type": "chunk",
                        "data": chunk,
                        "chunk_index": i // chunk_lines,
                        "progress": progress,
                        "is_final": (i + chunk_lines) >= total_lines
                    }
                    
                    # Small delay to prevent overwhelming
                    time.sleep(0.01)
                
                # Final metadata
                yield {
                    "type": "complete",
                    "metadata": metadata,
                    "total_size": result_size,
                    "total_lines": total_lines
                }
                
        except Exception as e:
            yield {
                "type": "error",
                "message": f"Streaming error: {str(e)}"
            }
    
    def estimate_streaming_needed(self, expected_output_size: int) -> bool:
        """Estimate if streaming will be needed based on expected output size."""
        return expected_output_size > 50000  # 50KB threshold
    
    def get_optimal_chunk_size(self, total_size: int) -> int:
        """Get optimal chunk size based on total output size."""
        if total_size < 100000:  # < 100KB
            return 4096
        elif total_size < 1000000:  # < 1MB  
            return 8192
        else:  # >= 1MB
            return 16384 