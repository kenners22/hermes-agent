import importlib
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tui_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    import agent.skill_commands as commands
    import tools.skills_tool as skills_tool
    from hermes_cli import goals
    skills = home / "skills"
    skills.mkdir()
    monkeypatch.setattr(skills_tool, "SKILLS_DIR", skills)
    root = skills / "quality" / "dual-perspective-creation-quality-loop"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: dual-perspective-creation-quality-loop\n"
        "description: Strict quality loop.\n---\n\nVerify every fix.\n",
        encoding="utf-8",
    )
    commands._skill_commands = {}
    commands._skill_commands_platform = None
    goals._DB_CACHE.clear()
    with patch.dict(
        "sys.modules",
        {"hermes_cli.env_loader": MagicMock(), "hermes_cli.banner": MagicMock()},
    ):
        server = importlib.import_module("tui_gateway.server")
        sid = "quality-tui"
        session_key = "quality-tui-session"
        server._sessions[sid] = {
            "session_key": session_key,
            "history": [],
            "history_lock": threading.Lock(),
            "history_version": 0,
            "running": False,
            "attached_images": [],
            "cols": 120,
        }
        yield server, sid, session_key
        server._sessions.clear()
        server._pending.clear()
        server._answers.clear()
    commands._skill_commands = {}
    commands._skill_commands_platform = None
    goals._DB_CACHE.clear()


def call(server, name, arg, sid):
    return server._methods["command.dispatch"](
        1, {"name": name, "arg": arg, "session_id": sid}
    )


def test_tui_quality_loop_alias_show_stop_done_and_routing(tui_env):
    server, sid, session_key = tui_env
    result = call(server, "ql", "Improve /tmp/storefront", sid)["result"]
    assert result["type"] == "send"
    assert "Quality loop set" in result["notice"]
    assert "full skill content is loaded below" in result["message"]
    shown = call(server, "quality-loop", "show", sid)["result"]["output"]
    assert "Completion contract:" in shown
    assert "Consumer score is at least 90" in shown
    stopped = call(server, "quality-loop", "stop", sid)["result"]["output"]
    assert "cleared" in stopped.lower()
    from hermes_cli.goals import GoalManager
    assert not GoalManager(session_key).has_goal()
    call(server, "quality-loop", "Improve /tmp/storefront", sid)
    done = call(server, "quality-loop", "done", sid)["result"]["output"]
    assert "cleared" in done.lower()
    assert not GoalManager(session_key).has_goal()
    assert "quality-loop" in server._PENDING_INPUT_COMMANDS
    assert "ql" in server._PENDING_INPUT_COMMANDS
