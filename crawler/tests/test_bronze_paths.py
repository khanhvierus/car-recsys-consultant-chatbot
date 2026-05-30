from temporal_app.pipeline.bronze import (
    BronzeLoaderConfig,
    _date_from_path,
    _page_from_path,
    _prefixes_for,
)


def test_prefixes_for_a_single_day():
    cfg = BronzeLoaderConfig(bucket="incremental_raw", crawl_date="2026-05-29")
    assert _prefixes_for(cfg) == ["dt=2026-05-29/"]


def test_page_parsed_from_dt_path():
    assert _page_from_path("dt=2026-05-29/1/3.json") == 1


def test_date_parsed_from_dt_path():
    assert _date_from_path("dt=2026-05-29/1/3.json") == "2026-05-29"


def test_date_none_when_absent():
    assert _date_from_path("raw_data/1/3.json") is None
