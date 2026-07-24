"""Frozen notes cost nothing (006 US3, FR-326).

The status read happens BEFORE drafting, so an approved or sent note must not
produce a single outbound LLM request. Checking after the call would satisfy
"don't rewrite" while still billing for every frozen company on every run.
"""

import httpx
import pytest
import respx

from prospector.config import Settings
from prospector.pipeline import run_batch
from prospector.vault import parse_note

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

NOTE = """---
company: Acme Duct
email: scott@acmeduct.com
channel: email
status: {status}
name_used: team
name_confidence: none
name_candidate:
hook: 22 years in business
website: acmeduct.com
angle: offer-led
fb_signal: none
duplicate_of:
needs_review: false
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** THE APPROVED SUBJECT

THE APPROVED BODY the human actually read.

## Research
- Owner name: not found

## Log
- 2026-07-19 approved by hand
"""


class StubFetch:
    """Fetcher stand-in returning a benign page.

    It must SUCCEED, not raise: a raising fetcher trips per-company isolation,
    which skips drafting for its own reason and would make a `call_count == 0`
    assertion pass without the freeze doing any work at all."""

    def fetch(self, url, *, check_robots=False):
        return httpx.Response(
            200,
            html="<html><body><p>Serving Boston for 22 years.</p></body></html>",
            request=httpx.Request("GET", url),
        )


@pytest.fixture
def settings(tmp_path):
    return Settings(
        openrouter_key="test-key",
        openrouter_model="test/model",
        places_key=None,
        hunter_key=None,
        vault_dir=tmp_path / "vault",
    )


def write_csv(tmp_path, rows: str) -> "object":
    path = tmp_path / "in.csv"
    path.write_text("company,email,website\n" + rows, encoding="utf-8")
    return path


def seed(vault_dir, slug: str, status: str) -> None:
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / f"{slug}.md").write_text(NOTE.format(status=status), encoding="utf-8")


def section(note: str, heading: str) -> str:
    return dict(parse_note(note)[1])[heading]


@pytest.mark.parametrize("status", ["approved", "sent", "hold"])
@respx.mock
def test_no_llm_call_for_frozen(tmp_path, settings, status):
    """The load-bearing assertion: zero outbound requests for a frozen note."""
    route = respx.post(OPENROUTER).mock(return_value=httpx.Response(200, json={}))
    vault_dir = tmp_path / "vault"
    seed(vault_dir, "acme-duct", status)
    csv = write_csv(tmp_path, "Acme Duct,scott@acmeduct.com,https://acmeduct.com\n")

    run_batch(csv, settings, vault_dir=vault_dir, fetcher=StubFetch())

    assert route.call_count == 0, f"{status!r} note must not trigger a drafting call"


@pytest.mark.parametrize("status", ["approved", "sent", "hold"])
@respx.mock
def test_frozen_draft_bytes_unchanged(tmp_path, settings, status):
    respx.post(OPENROUTER).mock(return_value=httpx.Response(200, json={}))
    vault_dir = tmp_path / "vault"
    seed(vault_dir, "acme-duct", status)
    before = (vault_dir / "acme-duct.md").read_text(encoding="utf-8")
    csv = write_csv(tmp_path, "Acme Duct,scott@acmeduct.com,https://acmeduct.com\n")

    run_batch(csv, settings, vault_dir=vault_dir, fetcher=StubFetch())

    after = (vault_dir / "acme-duct.md").read_text(encoding="utf-8")
    assert section(after, "Draft") == section(before, "Draft")
    assert "THE APPROVED BODY" in after


@respx.mock
def test_frozen_status_is_preserved(tmp_path, settings):
    respx.post(OPENROUTER).mock(return_value=httpx.Response(200, json={}))
    vault_dir = tmp_path / "vault"
    seed(vault_dir, "acme-duct", "sent")
    csv = write_csv(tmp_path, "Acme Duct,scott@acmeduct.com,https://acmeduct.com\n")

    run_batch(csv, settings, vault_dir=vault_dir, fetcher=StubFetch())

    frontmatter, _ = parse_note((vault_dir / "acme-duct.md").read_text(encoding="utf-8"))
    assert frontmatter["status"] == "sent"


@respx.mock
def test_to_send_note_is_redrafted_in_the_same_run(tmp_path, settings):
    """The freeze must be surgical: awaiting-review notes still refresh."""
    respx.post(OPENROUTER).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"greeting_name": "Acme Duct team", "subject_company": "Acme Duct"}'}}
                ]
            },
        )
    )
    vault_dir = tmp_path / "vault"
    seed(vault_dir, "acme-duct", "to-send")
    csv = write_csv(tmp_path, "Acme Duct,scott@acmeduct.com,https://acmeduct.com\n")

    run_batch(csv, settings, vault_dir=vault_dir, fetcher=StubFetch())

    after = (vault_dir / "acme-duct.md").read_text(encoding="utf-8")
    assert "THE APPROVED BODY" not in after, "to-send copy should have been regenerated"


@respx.mock
def test_mixed_vault_freezes_only_the_frozen(tmp_path, settings):
    """One run, two companies: the sent one is untouched, the other re-drafts."""
    route = respx.post(OPENROUTER).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"greeting_name": "Bravo Vents team", "subject_company": "Bravo Vents"}'}}
                ]
            },
        )
    )
    vault_dir = tmp_path / "vault"
    seed(vault_dir, "acme-duct", "sent")
    seed(vault_dir, "bravo-vents", "to-send")
    csv = write_csv(
        tmp_path,
        "Acme Duct,scott@acmeduct.com,https://acmeduct.com\n"
        "Bravo Vents,info@bravovents.com,https://bravovents.com\n",
    )

    run_batch(csv, settings, vault_dir=vault_dir, fetcher=StubFetch())

    assert route.call_count == 1, "exactly one company was draftable"
    assert "THE APPROVED BODY" in (vault_dir / "acme-duct.md").read_text(encoding="utf-8")
    assert "THE APPROVED BODY" not in (vault_dir / "bravo-vents.md").read_text(encoding="utf-8")
