"""Tests for autonomy mode management."""
import pytest

from quantclaw.orchestration.autonomy import AutonomyMode, AutonomyManager


def test_default_mode_is_plan():
    am = AutonomyManager()
    assert am.mode == AutonomyMode.PLAN


def test_switch_to_autopilot():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert am.mode == AutonomyMode.AUTOPILOT


def test_switch_to_interactive():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert am.mode == AutonomyMode.INTERACTIVE


def test_should_show_plan():
    am = AutonomyManager()
    assert am.should_show_plan()  # Plan Mode shows plan
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert not am.should_show_plan()  # Autopilot does not
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert am.should_show_plan()  # Interactive shows plan


def test_should_wait_for_approval():
    am = AutonomyManager()
    assert am.should_wait_for_approval()  # Plan Mode waits
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert not am.should_wait_for_approval()
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert not am.should_wait_for_approval()  # Interactive shows but doesn't block


def test_auto_escalation_overrides_autopilot():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert am.should_escalate_for("live_trade")
    assert not am.should_escalate_for("research")


def test_mode_history():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.AUTOPILOT)
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert len(am.mode_history) == 3  # initial PLAN + 2 switches
