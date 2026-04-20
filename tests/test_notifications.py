from quantclaw.notifications.formatter import format_event
from quantclaw.events.types import Event, EventType


def test_format_immediate_event():
    e = Event(type=EventType.MARKET_GAP_DETECTED, payload={"gap": -0.015, "ticker": "SPY"})
    msg = format_event(e, urgency="immediate")
    assert "SPY" in msg
    assert "URGENT" in msg


def test_format_normal_event():
    e = Event(type=EventType.PIPELINE_BACKTEST_DONE, payload={"sharpe": 2.07, "engine": "qlib_b"})
    msg = format_event(e, urgency="normal")
    assert "2.07" in msg
    assert "INFO" in msg


def test_format_no_payload():
    e = Event(type=EventType.SCHEDULE_TRIGGERED, payload={})
    msg = format_event(e, urgency="low")
    assert "LOG" in msg
    assert "no details" in msg
