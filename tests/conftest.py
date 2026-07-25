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

# The reference profile ships inside the package, so it resolves through the
# search path's packaged tier no matter what the working directory is. Tests
# still pin the env var explicitly rather than relying on that tier, so a test
# that chdirs into a tmp_path cannot accidentally pick up a stray ./profiles/.
BUNDLED_PROFILES = os.path.join(REPO_ROOT, "prospector", "profiles")


@pytest.fixture(autouse=True)
def default_profile(monkeypatch):
    monkeypatch.setenv("PROSPECTOR_PROFILE", "duct-cleaning")
    monkeypatch.setenv("PROSPECTOR_PROFILES", BUNDLED_PROFILES)


@pytest.fixture
def duct_profile():
    """The bundled reference profile, for tests that exercise drafting.

    008: the offer lives in the profile, so anything that assembles or
    validates copy needs one. Loading the real reference profile (rather than a
    stub) keeps these tests honest about the copy that actually ships."""
    from prospector.profiles import load

    return load("duct-cleaning")
