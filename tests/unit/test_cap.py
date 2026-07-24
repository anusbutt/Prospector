"""CapSchedule ramp math (T018) — the safety-critical daily-cap logic."""

from datetime import date

from prospector.send import CapSchedule


def test_empty_ledger_uses_week0_cap():
    sched = CapSchedule([15, 30, 60, 100])
    assert sched.cap_for(date(2026, 7, 16), None) == 15


def test_week_index_from_first_send():
    sched = CapSchedule([15, 30, 60, 100])
    first = date(2026, 7, 1)
    assert sched.cap_for(date(2026, 7, 1), first) == 15   # day 0 → week 0
    assert sched.cap_for(date(2026, 7, 7), first) == 15   # day 6 → week 0
    assert sched.cap_for(date(2026, 7, 8), first) == 30   # day 7 → week 1
    assert sched.cap_for(date(2026, 7, 15), first) == 60  # day 14 → week 2
    assert sched.cap_for(date(2026, 7, 22), first) == 100 # day 21 → week 3


def test_last_value_applies_to_all_later_weeks():
    sched = CapSchedule([15, 30, 60, 100])
    first = date(2026, 1, 1)
    assert sched.cap_for(date(2026, 6, 1), first) == 100  # far future → capped at last


def test_remaining_subtracts_todays_sends():
    sched = CapSchedule([15])
    first = date(2026, 7, 16)
    assert sched.remaining(date(2026, 7, 16), first, sent_today=10) == 5
    assert sched.remaining(date(2026, 7, 16), first, sent_today=15) == 0
    assert sched.remaining(date(2026, 7, 16), first, sent_today=99) == 0  # never negative


def test_single_step_schedule():
    sched = CapSchedule([25])
    assert sched.cap_for(date(2026, 7, 16), date(2026, 1, 1)) == 25
