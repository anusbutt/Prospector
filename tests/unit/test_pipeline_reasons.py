"""008 FR-010: an unreachable company is explained by what research found, not
by what the input row looked like. The three reasons separate a sourcing problem
(listings with no websites) from a vertical that publishes no addresses.
"""

from prospector.models import ResearchResult
from prospector.pipeline import _no_email_reason


class TestNoEmailReason:
    def test_no_website_resolved(self):
        assert _no_email_reason(ResearchResult()) == "no website could be resolved"

    def test_website_resolved_but_unreadable(self):
        research = ResearchResult(website="https://acmeduct.com", pages_fetched=0)
        assert _no_email_reason(research) == "no page could be fetched from https://acmeduct.com"

    def test_pages_read_but_nothing_published(self):
        research = ResearchResult(website="https://acmeduct.com", pages_fetched=3)
        assert _no_email_reason(research) == "no published address on any fetched page"
