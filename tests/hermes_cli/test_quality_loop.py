from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


SKILL = "dual-perspective-creation-quality-loop"


@pytest.fixture
def quality_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    skills = home / "skills"
    skills.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    import agent.skill_commands as commands
    import tools.skills_tool as skills_tool
    from hermes_cli import goals
    monkeypatch.setattr(skills_tool, "SKILLS_DIR", skills)
    commands._skill_commands = {}
    commands._skill_commands_platform = None
    goals._DB_CACHE.clear()
    yield home, skills
    commands._skill_commands = {}
    commands._skill_commands_platform = None
    goals._DB_CACHE.clear()


def install_skill(skills):
    root = skills / "quality" / SKILL
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {SKILL}\ndescription: Strict quality loop.\n---\n\n"
        "Inspect the real artifact and verify every fix.\n",
        encoding="utf-8",
    )


def test_registry_contract_controls_and_slack_curation():
    from hermes_cli.commands import (
        COMMANDS_BY_CATEGORY,
        _SLACK_VIA_HERMES_ONLY,
        resolve_command,
        slack_native_slashes,
    )
    from hermes_cli.quality_loop import build_quality_loop_contract, is_quality_loop_control
    assert resolve_command("quality-loop").name == "quality-loop"
    assert resolve_command("ql").name == "quality-loop"
    assert "/quality-loop" in COMMANDS_BY_CATEGORY["Session"]
    _goal, contract = build_quality_loop_contract("Improve /tmp/storefront")
    assert "Consumer score is at least 90" in contract.outcome
    assert "Seller score is at least 90" in contract.outcome
    assert "every applicable dimension is at least 80" in contract.outcome
    assert "primary-job dimension is at least 85" in contract.outcome
    for control in ("status", "show", "pause", "resume", "clear", "stop", "done"):
        assert is_quality_loop_control(control)
    assert not is_quality_loop_control("pause after this fix")
    assert {"quality-loop", "ql"} <= _SLACK_VIA_HERMES_ONLY
    native = {name for name, _d, _h in slack_native_slashes()}
    assert "quality-loop" not in native and "ql" not in native


def test_skill_load_precedes_goal_and_disabled_fails_closed(quality_env, monkeypatch):
    _home, skills = quality_env
    install_skill(skills)
    import agent.skill_utils as skill_utils
    from hermes_cli.goals import GoalManager
    from hermes_cli.quality_loop import QualityLoopUnavailable, start_quality_loop
    mgr = GoalManager("quality-ok", default_max_turns=9)
    state, kickoff = start_quality_loop(mgr, "Improve /tmp/storefront", task_id="quality-ok")
    assert state.max_turns == 9 and state.has_contract()
    assert "full skill content is loaded below" in kickoff
    assert "Inspect the real artifact" in kickoff
    monkeypatch.setattr(
        skill_utils,
        "get_disabled_skill_names",
        lambda platform=None: {SKILL} if platform == "discord" else set(),
    )
    blocked = GoalManager("quality-blocked")
    with pytest.raises(QualityLoopUnavailable, match="disabled for discord"):
        start_quality_loop(blocked, "Improve /tmp/storefront", platform="discord")
    assert not blocked.has_goal()


def test_cli_queue_success_controls_and_failure_rollback(quality_env, monkeypatch):
    _home, skills = quality_env
    install_skill(skills)
    import cli as cli_module
    from hermes_cli.cli_commands_mixin import CLICommandsMixin
    from hermes_cli.goals import GoalManager
    output = []
    monkeypatch.setattr(cli_module, "_cprint", output.append)
    mgr = GoalManager("quality-cli")
    pending = MagicMock()
    delegated = []
    fake = SimpleNamespace(
        session_id="quality-cli",
        _pending_input=pending,
        _get_goal_manager=lambda: mgr,
        _handle_goal_command=lambda command: delegated.append(command),
    )
    CLICommandsMixin._handle_quality_loop_command(fake, "/quality-loop Improve /tmp/storefront")
    pending.put.assert_called_once()
    assert mgr.has_goal() and any("Quality loop set" in line for line in output)
    for control in ("show", "stop", "done"):
        CLICommandsMixin._handle_quality_loop_command(fake, f"/quality-loop {control}")
    assert delegated == ["/goal show", "/goal stop", "/goal done"]
    mgr.clear()
    output.clear()
    pending.reset_mock()
    pending.put.side_effect = RuntimeError("queue closed")
    CLICommandsMixin._handle_quality_loop_command(fake, "/quality-loop Improve /tmp/storefront")
    assert not mgr.has_goal()
    assert any("rolled back" in line for line in output)
    assert not any("Quality loop set" in line for line in output)
