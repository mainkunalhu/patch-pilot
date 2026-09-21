from dateutil.parser import parse


def parse_day(s: str) -> int:
    # BUG: returns the month instead of the day
    return parse(s).month
