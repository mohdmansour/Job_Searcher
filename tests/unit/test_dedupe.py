from datetime import UTC, datetime, timedelta

from jobcv.jobs.dedupe import canonical_url, dedupe, fuzzy_key
from jobcv.schemas import Job

T0 = datetime(2026, 11, 8, tzinfo=UTC)


def job(id="linkedin:1", title="QA Engineer", company="Acme", location="Dubai, United Arab Emirates",
        url="https://www.linkedin.com/jobs/view/1", description="short", fetched=T0, source="linkedin"):
    return Job(id=id, source=source, title=title, company=company, location=location, remote=False,
               description=description, url=url, posted_at=None, fetched_at=fetched, language="en")


def test_canonical_url_strips_query_slash_and_country_subdomain():
    assert canonical_url("https://ae.linkedin.com/jobs/view/1/?trk=abc#x") == \
        "https://www.linkedin.com/jobs/view/1"
    assert canonical_url("HTTPS://Example.com/Job/2/") == "https://example.com/Job/2"


def test_exact_duplicate_by_id():
    assert len(dedupe([job(), job(url="https://other/1")])) == 1


def test_exact_duplicate_by_url_with_different_ids():
    a = job(id="linkedin:1", url="https://www.linkedin.com/jobs/view/1?x=1")
    b = job(id="bayt:99", source="bayt", title="Totally different", url="https://ae.linkedin.com/jobs/view/1/")
    assert len(dedupe([a, b])) == 1


def test_fuzzy_duplicate_across_sources():
    a = job(id="linkedin:1", title="QA Engineer", company="Acme LLC", location="Dubai, UAE")
    b = job(id="bayt:7", source="bayt", title="qa  engineer!", company="ACME", location="Dubai",
            url="https://bayt.com/job/7")
    assert fuzzy_key(a) == fuzzy_key(b)
    assert len(dedupe([a, b])) == 1


def test_fuzzy_key_normalizes_arabic():
    a = job(title="مهندس جودة", company="شركة أكمي")
    b = job(title="مُهندس جوده", company="شركة اكمي")
    assert fuzzy_key(a) == fuzzy_key(b)


def test_same_title_different_city_is_not_a_duplicate():
    a = job(id="linkedin:1", location="Dubai, United Arab Emirates")
    b = job(id="linkedin:2", url="https://www.linkedin.com/jobs/view/2",
            location="Abu Dhabi, United Arab Emirates")
    assert len(dedupe([a, b])) == 2


def test_merge_keeps_newest_fetch_and_longest_description():
    old = job(description="a much longer description " * 5, fetched=T0)
    new = job(description="short", fetched=T0 + timedelta(hours=3))
    (merged,) = dedupe([old, new])
    assert merged.fetched_at == new.fetched_at
    assert merged.description.startswith("a much longer")


def test_order_of_first_appearance_is_kept():
    jobs = [job(id=f"linkedin:{i}", url=f"https://www.linkedin.com/jobs/view/{i}",
                title=f"Role {i}") for i in range(3)]
    assert [j.id for j in dedupe(jobs)] == ["linkedin:0", "linkedin:1", "linkedin:2"]
