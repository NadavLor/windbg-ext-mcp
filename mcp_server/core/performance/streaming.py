"""
Streaming handler for large WinDbg command outputs.

This module provides chunked streaming of large command results to prevent
memory issues and improve responsiveness for huge outputs.
"""
import logging
import time
from typing import Dict, Any, Generator

from ..connection_resilience import execute_resilient_command

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
            
            # Execute the command with resilience
            success, result, metadata = execute_resilient_command(command, timeout_category)
            
            if not success:
                yield {
                    "type": "error", 
                    "message": result,
                    "metadata": metadata
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