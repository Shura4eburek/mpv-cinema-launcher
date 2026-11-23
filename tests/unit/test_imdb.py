"""Поиск id IMDb: принимается только однозначное совпадение названия, года и типа."""

from unittest import mock

import pytest
import requests

from mpv_launcher import imdb

PAYLOAD = {"d": [
    {"id": "tt0133093", "l": "The Matrix", "qid": "movie", "y": 1999},
    {"id": "in0000304", "l": "The Matrix", "s": "Franchise"},
    {"id": "tt0234215", "l": "The Matrix Reloaded", "qid": "movie", "y": 2003},
    {"id": "tt14190592", "l": "The Lazarus Project", "qid": "tvSeries", "y": 2022},
]}


def test_exact_match():
    assert imdb.pick(PAYLOAD, "The Matrix", "1999", "film") == "tt0133093"


@pytest.mark.parametrize("title, year, kind", [
    ("The Matrix", "2000", "film"),
    ("The Matrix", "1999", "series"),
    ("Matrix", "1999", "film"),
])
def test_mismatch_gives_none(title, year, kind):
    assert imdb.pick(PAYLOAD, title, year, kind) is None


def test_series_year_may_differ_by_one():
    assert imdb.pick(PAYLOAD, "The Lazarus Project", "2023", "series") == "tt14190592"
    assert imdb.pick(PAYLOAD, "The Lazarus Project", "2024", "series") is None


def test_two_candidates_give_none():
    payload = {"d": [*PAYLOAD["d"], {"id": "tt9999999", "l": "The Matrix", "qid": "movie", "y": 1999}]}
    assert imdb.pick(payload, "The Matrix", "1999", "film") is None


def test_unexpected_payload_is_unavailable():
    with pytest.raises(imdb.Unavailable):
        imdb.pick({"x": 1}, "The Matrix", "1999", "film")


def test_network_failure_is_unavailable():
    with mock.patch.object(imdb.requests, "get", side_effect=requests.ConnectionError()):
        with pytest.raises(imdb.Unavailable):
            imdb.find_id("The Matrix", "1999", "film")


def test_find_id_queries_normalized_name():
    response = mock.Mock(ok=True, json=mock.Mock(return_value=PAYLOAD))
    with mock.patch.object(imdb.requests, "get", return_value=response) as get:
        assert imdb.find_id("The Matrix", "1999", "film") == "tt0133093"
    assert get.call_args.args[0].endswith("/the%20matrix.json")
