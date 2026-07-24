"""Shared test setup.

008: every run selects an offer profile. Tests that are not *about* profile
selection get the bundled reference profile, so they exercise the behaviour they
were written for rather than the selection prompt. Tests that ARE about
selection (test_profiles.py, and the CLI selection cases) override or delete
this environment variable themselves.
"""

import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def default_profile(monkeypatch):
    monkeypatch.setenv("PROSPECTOR_PROFILE", "duct-cleaning")
    # Profiles resolve relative to the working directory; pin it to the repo so
    # the bundled reference profile is found no matter where pytest was invoked.
    monkeypatch.setenv("PROSPECTOR_PROFILES", os.path.join(REPO_ROOT, "profiles"))
