import pytest

from prospector.ingest import IngestError, load_companies, mark_duplicates
from prospector.models import Channel, Company
from prospector.vault import assign_slugs


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestCsvParsing:
    def test_minimal_csv(self, tmp_path):
        path = write(tmp_path, "list.csv", "company,email\nAcme Duct,info@acme.com\n")
        companies, warnings = load_companies(path)
        assert len(companies) == 1
        c = companies[0]
        assert c.company == "Acme Duct"
        assert c.email == "info@acme.com"
        assert c.channel is Channel.EMAIL
        assert c.row_num == 2

    def test_headers_case_insensitive_and_optionals(self, tmp_path):
        path = write(
            tmp_path,
            "list.csv",
            "Company,Email,Website,Facebook_URL,City,Owner_Name,Notes\n"
            "Acme,INFO@Acme.com,acme.com,https://facebook.com/acme,Boston,Scott,note\n",
        )
        companies, _ = load_companies(path)
        c = companies[0]
        assert c.email == "info@acme.com"  # lowercased
        assert c.website == "https://acme.com"  # scheme added
        assert c.facebook_url == "https://facebook.com/acme"  # stored, never fetched
        assert c.city == "Boston"
        assert c.owner_name == "Scott"

    def test_unknown_column_warned_not_fatal(self, tmp_path):
        path = write(tmp_path, "list.csv", "company,email,phone\nAcme,info@acme.com,555\n")
        companies, warnings = load_companies(path)
        assert len(companies) == 1
        assert any("unknown column 'phone'" in w for w in warnings)

    def test_missing_required_column_fatal(self, tmp_path):
        path = write(tmp_path, "list.csv", "company,website\nAcme,acme.com\n")
        with pytest.raises(IngestError, match="missing required column 'email'"):
            load_companies(path)

    def test_missing_file_fatal(self, tmp_path):
        with pytest.raises(IngestError, match="not found"):
            load_companies(tmp_path / "nope.csv")

    def test_malformed_row_skipped_with_row_number(self, tmp_path):
        path = write(tmp_path, "list.csv", "company,email\n,orphan@x.com\nAcme,info@acme.com\n")
        companies, warnings = load_companies(path)
        assert [c.company for c in companies] == ["Acme"]
        assert any("row 2" in w and "missing company" in w for w in warnings)


class TestMarkdownParsing:
    def test_markdown_table(self, tmp_path):
        path = write(
            tmp_path,
            "list.md",
            "# My list\n\n| company | email |\n|---|---|\n| Acme Duct | info@acme.com |\n| Beta Air | messenger |\n",
        )
        companies, _ = load_companies(path)
        assert len(companies) == 2
        assert companies[0].company == "Acme Duct"
        assert companies[1].channel is Channel.MESSENGER

    def test_no_table_fatal(self, tmp_path):
        path = write(tmp_path, "list.md", "just prose, no table\n")
        with pytest.raises(IngestError, match="no markdown table"):
            load_companies(path)


class TestBucketing:
    @pytest.mark.parametrize(
        "email_value,channel,needs_review",
        [
            ("info@acme.com", Channel.EMAIL, False),
            ("", Channel.MESSENGER, False),
            ("messenger", Channel.MESSENGER, False),
            ("Messenger", Channel.MESSENGER, False),
            ("https://facebook.com/acmeduct", Channel.MESSENGER, False),
            ("www.fb.com/acmeduct", Channel.MESSENGER, False),
            ("not-an-email", Channel.MESSENGER, True),
        ],
    )
    def test_bucketing_matrix(self, tmp_path, email_value, channel, needs_review):
        path = write(tmp_path, "list.csv", f'company,email\nAcme,"{email_value}"\n')
        companies, warnings = load_companies(path)
        c = companies[0]
        assert c.channel is channel
        assert c.needs_review is needs_review
        assert c.raw_email_field == email_value
        if needs_review:
            assert any("unrecognized email field" in w for w in warnings)

    def test_messenger_rows_have_no_email(self, tmp_path):
        path = write(tmp_path, "list.csv", "company,email\nAcme,https://facebook.com/acme\n")
        companies, _ = load_companies(path)
        assert companies[0].email is None
        assert companies[0].bucket_reason == "facebook url in email field"


def company(name, email, city=None):
    return Company(company=name, email=email, raw_email_field=email or "", city=city)


def deduped(*companies_args):
    companies = list(companies_args)
    assign_slugs(companies)
    mark_duplicates(companies)
    return companies


class TestDedupe:
    def test_same_email_groups_first_is_primary(self):
        a, b = deduped(
            company("Acme Duct", "info@shared.com"),
            company("Beta Air", "info@shared.com"),
        )
        assert a.duplicate_of is None
        assert b.duplicate_of == "acme-duct"
        assert b.needs_review

    def test_same_custom_domain_groups(self):
        a, b = deduped(
            company("Acme Duct", "info@acmegroup.com"),
            company("Acme Duct South", "sales@acmegroup.com"),
        )
        assert a.duplicate_of is None
        assert b.duplicate_of == "acme-duct"

    def test_same_free_provider_domain_does_not_group(self):
        a, b = deduped(
            company("Acme Duct", "acmeduct@gmail.com"),
            company("Beta Air", "betaair@gmail.com"),
        )
        assert a.duplicate_of is None
        assert b.duplicate_of is None

    def test_identical_free_provider_email_still_groups(self):
        a, b = deduped(
            company("Acme Duct", "sharedinbox@gmail.com"),
            company("Beta Air", "sharedinbox@gmail.com"),
        )
        assert b.duplicate_of == "acme-duct"

    def test_three_way_group_references_single_primary(self):
        a, b, c = deduped(
            company("Acme Duct", "info@acme.com"),
            company("Acme Two", "info@acme.com"),
            company("Acme Three", "office@acme.com"),
        )
        assert a.duplicate_of is None
        assert b.duplicate_of == "acme-duct"
        assert c.duplicate_of == "acme-duct"

    def test_messenger_rows_never_group(self):
        a, b = deduped(company("Acme Duct", None), company("Beta Air", None))
        assert a.duplicate_of is None and b.duplicate_of is None
