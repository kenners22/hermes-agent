"""Runtime-context scoping for MCP server startup."""


def test_detects_gateway_and_cli_runtime_contexts(monkeypatch):
    import sys

    from tools.mcp_tool import _detect_mcp_runtime_context

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "/venv/bin/python",
            "-m",
            "hermes_cli.main",
            "--profile",
            "elon",
            "gateway",
            "run",
            "--replace",
        ],
    )
    assert _detect_mcp_runtime_context() == "gateway"

    monkeypatch.setattr(sys, "argv", ["hermes", "chat", "-q", "hello"])
    assert _detect_mcp_runtime_context() == "cli"


def test_context_filter_preserves_unscoped_servers():
    from tools.mcp_tool import _filter_mcp_servers_for_runtime_context

    servers = {
        "profile_bus": {"command": "python3", "args": ["profile_bus.py"]},
        "xcode": {
            "command": "xcrun",
            "args": ["mcpbridge"],
            "runtime_contexts": ["gateway"],
        },
    }

    assert set(_filter_mcp_servers_for_runtime_context(servers, "gateway")) == {
        "profile_bus",
        "xcode",
    }
    assert set(_filter_mcp_servers_for_runtime_context(servers, "cli")) == {
        "profile_bus",
    }


def test_context_filter_accepts_string_and_wildcard():
    from tools.mcp_tool import _filter_mcp_servers_for_runtime_context

    servers = {
        "gateway_only": {"command": "one", "runtime_contexts": "gateway"},
        "all_contexts": {"command": "two", "runtime_contexts": ["*"]},
    }

    assert set(_filter_mcp_servers_for_runtime_context(servers, "gateway")) == {
        "gateway_only",
        "all_contexts",
    }
    assert set(_filter_mcp_servers_for_runtime_context(servers, "cli")) == {
        "all_contexts",
    }


def test_discovery_does_not_register_server_outside_runtime_context(monkeypatch):
    import tools.mcp_tool as mcp_tool

    servers = {
        "profile_bus": {"command": "python3", "args": ["profile_bus.py"]},
        "xcode": {
            "command": "xcrun",
            "args": ["mcpbridge"],
            "runtime_contexts": ["gateway"],
        },
    }
    captured = {}

    monkeypatch.setattr(mcp_tool, "_MCP_AVAILABLE", True)
    monkeypatch.setattr(mcp_tool, "_load_mcp_config", lambda: servers)
    monkeypatch.setattr(mcp_tool, "_detect_mcp_runtime_context", lambda: "cli")
    monkeypatch.setattr(
        mcp_tool,
        "register_mcp_servers",
        lambda scoped: captured.update(scoped) or ["mcp__profile_bus__state"],
    )
    with mcp_tool._lock:
        saved_servers = dict(mcp_tool._servers)
        mcp_tool._servers.clear()
    try:
        assert mcp_tool.discover_mcp_tools() == ["mcp__profile_bus__state"]
    finally:
        with mcp_tool._lock:
            mcp_tool._servers.clear()
            mcp_tool._servers.update(saved_servers)

    assert set(captured) == {"profile_bus"}


def test_empty_and_invalid_explicit_contexts_fail_closed(caplog):
    from tools.mcp_tool import _filter_mcp_servers_for_runtime_context

    servers = {
        "empty": {"command": "one", "runtime_contexts": []},
        "whitespace": {"command": "two", "runtime_contexts": ["  "]},
        "invalid": {"command": "three", "runtime_contexts": 123},
    }

    assert _filter_mcp_servers_for_runtime_context(servers, "gateway") == {}
    assert any("must be a string or list" in record.getMessage() for record in caplog.records)


def test_direct_registration_honors_runtime_context_scope(monkeypatch):
    import tools.mcp_tool as mcp_tool

    captured = {}
    servers = {
        "profile_bus": {"command": "python3", "args": ["profile_bus.py"]},
        "xcode": {
            "command": "xcrun",
            "args": ["mcpbridge"],
            "runtime_contexts": ["gateway"],
        },
    }

    real_filter = mcp_tool._filter_mcp_servers_for_runtime_context

    def capture_filter(scoped, context):
        result = real_filter(scoped, context)
        captured.update(result)
        return result

    monkeypatch.setattr(mcp_tool, "_MCP_AVAILABLE", True)
    monkeypatch.setattr(mcp_tool, "_detect_mcp_runtime_context", lambda: "cli")
    monkeypatch.setattr(mcp_tool, "_filter_mcp_servers_for_runtime_context", capture_filter)
    monkeypatch.setattr(mcp_tool, "_ensure_mcp_loop", lambda: None)
    monkeypatch.setattr(mcp_tool, "_run_on_mcp_loop", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mcp_tool, "_existing_tool_names", lambda: [])
    with mcp_tool._lock:
        saved_servers = dict(mcp_tool._servers)
        mcp_tool._servers.clear()
    try:
        assert mcp_tool.register_mcp_servers(servers) == []
    finally:
        with mcp_tool._lock:
            mcp_tool._servers.clear()
            mcp_tool._servers.update(saved_servers)

    assert set(captured) == {"profile_bus"}
