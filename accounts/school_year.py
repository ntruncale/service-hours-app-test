"""School-year math in one place, so it is easy to test.

A school year is named by the calendar year it ends in: Aug 2026 - Jun 2027 is 2027.
"""

from datetime import date

from django.conf import settings
from django.utils import timezone


def today() -> date:
    return timezone.localdate()


def school_year_for(d: date) -> int:
    start_month = settings.SCHOOL_YEAR_START_MONTH
    return d.year + 1 if d.month >= start_month else d.year


def current_school_year() -> int:
    return school_year_for(today())


def school_year_label(year: int) -> str:
    return f"{year - 1}-{str(year)[-2:]}"


def school_year_bounds(year: int) -> tuple[date, date]:
    """First and last day of a school year."""
    start_month = settings.SCHOOL_YEAR_START_MONTH
    start = date(year - 1, start_month, 1)
    end = date(year, start_month, 1)
    return start, date.fromordinal(end.toordinal() - 1)


def grade_for(graduation_year: int, on: date | None = None) -> int | None:
    """Grade level (9-12) for a graduating class, or None if not in high school then."""
    year = school_year_for(on or today())
    grade = 12 - (graduation_year - year)
    return grade if 9 <= grade <= 12 else None


def graduation_year_for_grade(grade: int, on: date | None = None) -> int:
    return school_year_for(on or today()) + (12 - grade)


def fraction_of_year_elapsed(on: date | None = None) -> float:
    """0.0 on the first day of the school year, 1.0 on the last. Used for 'behind pace'."""
    on = on or today()
    start, end = school_year_bounds(school_year_for(on))
    total = (end - start).days or 1
    return max(0.0, min(1.0, (on - start).days / total))
