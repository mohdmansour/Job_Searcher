from jobcv.schemas import Country, SearchQuery
from jobcv.sources.location import resolve_location


def test_country_only_searches_whole_country():
    q = SearchQuery(title="QA", country=Country.GERMANY)
    assert resolve_location(q) == {"locations": ["Germany"]}


def test_cities_are_qualified_with_country():
    q = SearchQuery(title="QA", country=Country.UAE, cities=["Dubai", "Abu Dhabi"])
    assert resolve_location(q) == {"locations": ["Dubai, United Arab Emirates",
                                                 "Abu Dhabi, United Arab Emirates"]}


def test_duplicate_cities_are_collapsed_case_insensitively():
    q = SearchQuery(title="QA", country=Country.UAE, cities=["Dubai", "dubai "])
    assert resolve_location(q)["locations"] == ["Dubai, United Arab Emirates"]


def test_remote_adds_remote_work_type_code():
    q = SearchQuery(title="QA", country=Country.GERMANY, remote=True)
    assert resolve_location(q) == {"locations": ["Germany"], "workTypes": ["2"]}
