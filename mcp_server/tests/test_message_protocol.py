from mcp_server.core.communication import MessageProtocol


def test_serialize_command_message_has_newline():
    msg = MessageProtocol.create_command_message("version", timeout_ms=5000)
    wire = MessageProtocol.serialize_message(msg)
    assert isinstance(wire, bytes)
    assert wire.endswith(b"\n")


def test_parse_response_success():
    response_bytes = b'{"status":"success","output":"ok"}\n'
    parsed = MessageProtocol.parse_response(response_bytes)
    assert parsed["status"] == "success"
    assert parsed["output"] == "ok"

