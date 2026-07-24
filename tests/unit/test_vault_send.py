"""parse_draft + scoped set_status (T008/T009) — the single sanctioned
approved→sent status write must preserve all other content byte-for-byte."""

from prospector import vault

NOTE = """---
company: Boston Air Duct Cleaning
email: info@bostonairduct.com
channel: email
status: approved
name_used: team
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** Free 10-day pilot for Boston Air Duct

Hi Boston Air Duct team,
full body here.

## Research
- Owner name: not found

## Log
-
"""


def test_parse_draft_returns_subject_and_body():
    subject, body = vault.parse_draft(NOTE)
    assert subject == "Free 10-day pilot for Boston Air Duct"
    assert body.startswith("Hi Boston Air Duct team,")
    assert "full body here." in body


def test_parse_draft_none_when_subject_missing():
    text = NOTE.replace("**Subject:** Free 10-day pilot for Boston Air Duct\n\n", "")
    assert vault.parse_draft(text) is None


def test_parse_draft_none_when_body_empty():
    text = NOTE.replace("Hi Boston Air Duct team,\nfull body here.\n", "")
    assert vault.parse_draft(text) is None


def test_set_status_flips_status_and_appends_log(tmp_path):
    path = tmp_path / "note.md"
    path.write_text(NOTE, encoding="utf-8")
    vault.set_status(path, "sent", "2026-07-15 sent via prospector")
    result = path.read_text(encoding="utf-8")
    fm, sections = vault.parse_note(result)
    assert fm["status"] == "sent"
    log_body = dict(sections)["Log"]
    assert "2026-07-15 sent via prospector" in log_body


def test_set_status_preserves_other_content(tmp_path):
    path = tmp_path / "note.md"
    path.write_text(NOTE, encoding="utf-8")
    vault.set_status(path, "sent", "logged")
    result = path.read_text(encoding="utf-8")
    # Draft + Research bodies and all other frontmatter keys are untouched.
    assert "**Subject:** Free 10-day pilot for Boston Air Duct" in result
    assert "Hi Boston Air Duct team," in result
    assert "- Owner name: not found" in result
    assert "company: Boston Air Duct Cleaning" in result
    assert "email: info@bostonairduct.com" in result
    # The only status line now reads sent; "approved" no longer present.
    assert "status: sent" in result
    assert "status: approved" not in result
    # File still ends with a single trailing newline.
    assert result.endswith("\n") and not result.endswith("\n\n")


def test_set_status_replaces_lone_placeholder_not_duplicates(tmp_path):
    path = tmp_path / "note.md"
    path.write_text(NOTE, encoding="utf-8")
    vault.set_status(path, "sent", "first entry")
    result = path.read_text(encoding="utf-8")
    log_body = dict(vault.parse_note(result)[1])["Log"]
    # The placeholder "-" was replaced, not left dangling above the real entry.
    assert log_body.strip() == "- first entry"


def test_set_status_appends_to_existing_log_history(tmp_path):
    note = NOTE.replace("## Log\n-\n", "## Log\n- 2026-07-10 human note\n")
    path = tmp_path / "note.md"
    path.write_text(note, encoding="utf-8")
    vault.set_status(path, "sent", "2026-07-15 sent")
    log_body = dict(vault.parse_note(path.read_text())[1])["Log"]
    assert "- 2026-07-10 human note" in log_body
    assert "- 2026-07-15 sent" in log_body
