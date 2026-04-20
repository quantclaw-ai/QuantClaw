"""Tests for goal and autonomy mode persistence."""
import asyncio
import pytest
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.playbook import Playbook, EntryType


def test_autonomy_mode_persists(tmp_path):
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    am = AutonomyManager(playbook=pb)

    async def _run():
        await am.set_mode_persistent(AutonomyMode.AUTOPILOT)
        assert am.mode == AutonomyMode.AUTOPILOT

        am2 = await AutonomyManager.from_playbook(pb)
        assert am2.mode == AutonomyMode.AUTOPILOT

    asyncio.run(_run())


def test_goal_persists(tmp_path):
    pb = Playbook(str(tmp_path / "playbook.jsonl"))

    async def _run():
        await pb.add(EntryType.CEO_PREFERENCE, {"goal": "find momentum"})

        entries = await pb.query(entry_type=EntryType.CEO_PREFERENCE)
        goals = [e for e in entries if "goal" in e.content]
        assert len(goals) == 1
        assert goals[-1].content["goal"] == "find momentum"

    asyncio.run(_run())


def test_autonomy_default_without_playbook():
    am = AutonomyManager()
    assert am.mode == AutonomyMode.PLAN


def test_goal_restore_from_playbook(tmp_path):
    pb = Playbook(str(tmp_path / "playbook.jsonl"))

    async def _run():
        from quantclaw.orchestration.ooda import OODALoop
        await pb.add(EntryType.CEO_PREFERENCE, {"goal": "find alpha"})
        goal = await OODALoop.restore_goal(pb)
        assert goal == "find alpha"

    asyncio.run(_run())


def test_goal_restore_empty_playbook(tmp_path):
    pb = Playbook(str(tmp_path / "playbook.jsonl"))

    async def _run():
        from quantclaw.orchestration.ooda import OODALoop
        goal = await OODALoop.restore_goal(pb)
        assert goal == ""

    asyncio.run(_run())
