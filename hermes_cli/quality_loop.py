"""Persistent quality-loop preset built on Hermes' existing /goal engine.

The command does not implement another loop. It creates a normal persistent
GoalManager goal with a strict dual-perspective completion contract, then uses
the installed ``dual-perspective-creation-quality-loop`` skill as the kickoff
turn so the full rubric is present in conversation history.
"""

from __future__ import annotations

from typing import Any

from hermes_cli.goals import GoalContract

QUALITY_LOOP_SKILL = "dual-perspective-creation-quality-loop"
QUALITY_LOOP_SKILL_COMMAND = f"/{QUALITY_LOOP_SKILL}"
# Engine-level exit floors intentionally mirror the installed skill's release
# gate. Update both together: the skill supplies the detailed rubric while this
# contract prevents the persistent judge from accepting a weaker self-score.
QUALITY_LOOP_CONTROLS = frozenset(
    {
        "status",
        "show",
        "pause",
        "resume",
        "clear",
        "stop",
        "done",
    }
)


class QualityLoopUnavailable(RuntimeError):
    """Raised when the required quality skill cannot be loaded safely."""


def is_quality_loop_control(raw_args: str) -> bool:
    """Return True when *raw_args* is an exact control delegated to ``/goal``."""
    arg = (raw_args or "").strip().lower()
    return arg in QUALITY_LOOP_CONTROLS


def build_quality_loop_contract(request: str) -> tuple[str, GoalContract]:
    """Build the persistent goal headline and non-gameable completion contract."""
    target = (request or "").strip()
    if not target:
        raise ValueError(
            "quality-loop requires an artifact, path, URL, product or objective"
        )

    goal_text = (
        f'Apply the installed "{QUALITY_LOOP_SKILL}" skill to: {target}'
    )
    contract = GoalContract(
        outcome=(
            "The real artifact is materially improved and release-ready: Consumer "
            "score is at least 90; Seller score is at least 90; every applicable "
            "dimension is at least 80; every primary-job dimension is at least 85; "
            "no unresolved Critical or High issue remains; and every applicable hard "
            "gate passes. If an approval or external blocker prevents that result, "
            "finish every safe in-scope improvement and return an honest HOLD with the "
            "achieved scores and exact blocker instead of claiming a pass."
        ),
        verification=(
            "Inspect the real revised artifact in its intended consumer and seller "
            "context. Show baseline and final Consumer, Seller and lower-overall "
            "scores; a criticism/action ledger; changes actually completed; and fresh "
            "before/after evidence appropriate to the medium, such as screenshots, "
            "real browser/device journeys, builds, tests, measurements, exports or "
            "source readback. Re-test changed and adjacent surfaces."
        ),
        constraints=(
            "Follow the loaded quality skill and applicable specialist skills. Do not "
            "change weights, lower thresholds, redefine the audience, misuse N/A, "
            "average away a weak perspective, round up a borderline score, count one "
            "defect repeatedly, fabricate proof, award points for intended work, or "
            "use cosmetic polish to conceal weak trust, usability, reliability, "
            "economics or claim integrity. Preserve approved content and unrelated "
            "working behaviour."
        ),
        boundaries=(
            "Work on the supplied artifact and the supporting files, assets, flows and "
            "tests needed to improve and verify it. Safe private edits and verification "
            "are in scope. Public release, deployment, publication, outbound messages, "
            "purchases or spend, credential changes and destructive actions remain "
            "approval-gated."
        ),
        stop_when=(
            "A fresh approval, credential or MFA step, purchase or spend, deployment or "
            "publication, destructive action, inaccessible external evidence, or an "
            "external owner's action is required; or the configured goal-turn budget "
            "is exhausted. Report the exact blocker, owner and next action."
        ),
    )
    return goal_text, contract


def start_quality_loop(
    manager: Any,
    request: str,
    *,
    task_id: str | None = None,
    platform: str | None = None,
):
    """Load the quality skill, then atomically create the persistent goal.

    The skill kickoff is built before mutating goal state. A missing or disabled
    skill therefore fails closed without leaving an active goal that cannot
    follow the intended rubric.
    """
    goal_text, contract = build_quality_loop_contract(request)

    if platform:
        try:
            from agent.skill_utils import get_disabled_skill_names

            if QUALITY_LOOP_SKILL in get_disabled_skill_names(platform=platform):
                raise QualityLoopUnavailable(
                    f'The required "{QUALITY_LOOP_SKILL}" skill is disabled for '
                    f"{platform}. Enable it before starting /quality-loop."
                )
        except QualityLoopUnavailable:
            raise
        except Exception:
            # The normal skill builder remains the authoritative availability check.
            pass

    from agent.skill_commands import build_skill_invocation_message

    kickoff = build_skill_invocation_message(
        QUALITY_LOOP_SKILL_COMMAND,
        user_instruction=(
            f"{goal_text}\n\n"
            "This is the kickoff turn of a persistent evidence-driven quality loop. "
            "Inspect the real artifact, record the baseline, complete every safe "
            "high-impact fix, verify it, re-score it, and continue until the standing "
            "goal contract passes or a genuine stop condition is reached."
        ),
        task_id=task_id,
        runtime_note=(
            "Persistent /quality-loop completion contract:\n"
            f"{contract.render_block()}"
        ),
    )
    if not kickoff:
        raise QualityLoopUnavailable(
            f'The required "{QUALITY_LOOP_SKILL}" skill is missing or disabled. '
            "Install or enable it, then retry /quality-loop."
        )

    state = manager.set(goal_text, contract=contract)
    return state, kickoff


def quality_loop_usage() -> str:
    return (
        "Usage: /quality-loop <artifact, path, URL, product or objective>\n"
        "Starts the real persistent /goal loop with the dual-perspective quality "
        "skill and a strict 90+ evidence contract. Controls: /quality-loop status · "
        "show · pause · resume · clear."
    )
