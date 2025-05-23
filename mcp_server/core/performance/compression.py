"""
Data compression utilities for large WinDbg command outputs.

This module provides intelligent compression and decompression of text data,
with automatic threshold detection to ensure compression is beneficial.
"""
import logging
import gzip
from typing import Union, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class DataSize(Enum):
    """Data size categories for optimization decisions."""
    SMALL = "small"      # < 1KB
    MEDIUM = "medium"    # 1KB - 100KB  
    LARGE = "large"      # 100KB - 1MB
    HUGE = "huge"        # > 1MB

class DataCompressor:
    """Handles data compression for large outputs."""
    
    @staticmethod
    def compress_text(text: str, min_size: int = 1024) -> Tuple[Union[str, bytes], bool]:
        """Compress text if beneficial."""
        if len(text) < min_size:
            return text, False
        
        try:
            compressed = gzip.compress(text.encode('utf-8'))
            if len(compressed) < len(text.encode('utf-8')) * 0.8:  # 20% savings threshold
                return compressed, True
            else:
                return text, False
        except Exception:
            return text, False
    
    @staticmethod
    def decompress_text(data: Union[str, bytes], was_compressed: bool) -> str:
        """Decompress text if it was compressed."""
        if not was_compressed:
            return data if isinstance(data, str) else data.decode('utf-8')
        
        try:
            if isinstance(data, str):
                data = data.encode('latin-1')
            return gzip.decompress(data).decode('utf-8')
        except Exception:
            # Fallback to original data
            return data if isinstance(data, str) else data.decode('utf-8', errors='ignore')
    
    @staticmethod
    def get_data_size_category(data_size: int) -> DataSize:
        """Categorize data size for optimization decisions."""
        if data_size < 1024:
            return DataSize.SMALL
        elif data_size < 100 * 1024:
            return DataSize.MEDIUM
        elif data_size < 1024 * 1024:
            return DataSize.LARGE
        else:
            return DataSize.HUGE
    
    @staticmethod
    def should_compress(data_size: int, threshold: float = 0.8) -> bool:
        """Determine if data should be compressed based on size."""
        # Only compress if data is large enough and compression is likely beneficial
        return data_size > 1024 and data_size > 10000  # 10KB minimum for compression
    
    @staticmethod
    def get_compression_stats(original_size: int, compressed_size: int) -> dict:
        """Get compression statistics."""
        if original_size == 0:
            return {"ratio": 0.0, "savings": 0, "percentage": 0.0}
        
        ratio = compressed_size / original_size
        savings = original_size - compressed_size
        percentage = (savings / original_size) * 100
        
        return {
            "ratio": ratio,
            "savings": savings,
            "percentage": percentage,
            "original_size": original_size,
            "compressed_size": compressed_size
        } 