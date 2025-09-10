import pytest

from mcp_server.core.execution.timeout_resolver import TimeoutResolver, TimeoutCategory


def test_quick_commands():
    r = TimeoutResolver()
    assert r.get_category("version") == TimeoutCategory.QUICK
    assert r.get_category("r") == TimeoutCategory.QUICK
    assert r.get_category("help") == TimeoutCategory.QUICK


def test_symbol_and_extended():
    r = TimeoutResolver()
    assert r.get_category(".symfix") == TimeoutCategory.SYMBOLS
    assert r.get_category(".reload /f") == TimeoutCategory.EXTENDED


def test_streaming_and_bulk():
    r = TimeoutResolver()
    assert r.get_category("!for_each_module .echo") == TimeoutCategory.STREAMING
    assert r.get_category("!process 0 0") == TimeoutCategory.PROCESS_LIST
    assert r.get_category("lm") == TimeoutCategory.BULK


def test_execution_and_memory():
    r = TimeoutResolver()
    assert r.get_category("g") == TimeoutCategory.EXECUTION
    assert r.get_category("bp nt!NtCreateFile") == TimeoutCategory.EXECUTION
    assert r.get_category("dd 0x1000") == TimeoutCategory.MEMORY

