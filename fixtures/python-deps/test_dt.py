from dt import parse_day


def test_parse_day():
    assert parse_day("2024-03-15") == 15
