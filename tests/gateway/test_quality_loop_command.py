from unittest.mock import MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource
from hermes_cli import goals


class Entry:
    session_id = "quality-gateway-session"


class Store:
    def get_or_create_session(self, source):
        return Entry()

    def _generate_session_key(self, source):
        return "agent:main:discord:channel:quality"


def event(text, message_id="quality-message"):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=Platform.DISCORD,
            chat_id="quality-chat",
            chat_type="channel",
            user_id="quality-user",
        ),
        message_id=message_id,
    )


@pytest.fixture
def quality_gateway(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    skills = home / "skills"
    root = skills / "quality" / "dual-perspective-creation-quality-loop"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: dual-perspective-creation-quality-loop\n"
        "description: Strict quality loop.\n---\n\nVerify every fix.\n",
        encoding="utf-8",
    )
    (home / "config.yaml").write_text("goals:\n  max_turns: 7\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    import agent.skill_commands as commands
    import tools.skills_tool as skills_tool
    monkeypatch.setattr(skills_tool, "SKILLS_DIR", skills)
    commands._skill_commands = {}
    commands._skill_commands_platform = None
    goals._DB_CACHE.clear()
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.DISCORD: PlatformConfig(enabled=True, token="token")}
    )
    runner.session_store = Store()
    adapter = object()
    runner.adapters = {Platform.DISCORD: adapter}
    runner._queued_events = {}
    runner._session_key_for_source = MagicMock(return_value="quality-queue-key")
    runner._enqueue_fifo = MagicMock()
    yield runner, adapter
    commands._skill_commands = {}
    commands._skill_commands_platform = None
    goals._DB_CACHE.clear()


@pytest.mark.asyncio
async def test_gateway_queues_skill_contract_and_stop_done_controls(quality_gateway):
    runner, adapter = quality_gateway
    response = await GatewayRunner._handle_quality_loop_command(
        runner, event("/quality-loop Improve /tmp/storefront")
    )
    assert "Quality loop set (7-turn budget)" in response
    runner._enqueue_fifo.assert_called_once()
    key, queued, queued_adapter = runner._enqueue_fifo.call_args.args
    assert key == "quality-queue-key" and queued_adapter is adapter
    assert "full skill content is loaded below" in queued.text
    manager = goals.GoalManager("quality-gateway-session")
    original = manager.state.goal
    assert manager.state.has_contract()
    stopped = await GatewayRunner._handle_quality_loop_command(
        runner, event("/quality-loop stop", "stop")
    )
    assert "cleared" in stopped.lower()
    assert not goals.GoalManager("quality-gateway-session").has_goal()
    assert original != "stop"
    runner._enqueue_fifo.reset_mock()
    await GatewayRunner._handle_quality_loop_command(
        runner, event("/quality-loop Improve /tmp/storefront", "again")
    )
    done = await GatewayRunner._handle_quality_loop_command(
        runner, event("/quality-loop done", "done")
    )
    assert "cleared" in done.lower()
    assert not goals.GoalManager("quality-gateway-session").has_goal()


@pytest.mark.asyncio
async def test_gateway_enqueue_failure_rolls_back(quality_gateway):
    runner, _adapter = quality_gateway
    runner._enqueue_fifo.side_effect = RuntimeError("queue closed")
    response = await GatewayRunner._handle_quality_loop_command(
        runner, event("/quality-loop Improve /tmp/storefront")
    )
    assert "not started" in response.lower()
    assert "rolled back" in response.lower()
    assert not goals.GoalManager("quality-gateway-session").has_goal()
