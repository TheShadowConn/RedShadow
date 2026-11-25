"""Hourly scenario reminders (idempotent: each notification is deduplicated per scenario and date)."""

from celery import shared_task

from . import scenarios


@shared_task(name="engagements.scenario_reminders")
def scenario_reminders() -> int:
    return scenarios.remind()
