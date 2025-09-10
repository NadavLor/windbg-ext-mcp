from mcp_server.tools import get_tool_info


def test_get_tool_info_counts_and_categories():
    info = get_tool_info()
    assert "categories" in info
    assert "total_tools" in info
    # Expect 5 categories and 16 tools total
    assert len(info["categories"]) == 5
    assert info["total_tools"] == sum(len(cat["tools"]) for cat in info["categories"].values())
    assert info["total_tools"] == 16

