from datetime import date

import pytest

from accounts import school_year


@pytest.mark.parametrize(
    "d, expected",
    [
        (date(2026, 6, 30), 2026),
        (date(2026, 7, 1), 2027),
        (date(2026, 11, 6), 2027),
        (date(2027, 1, 15), 2027),
    ],
)
def test_school_year_for(d, expected):
    assert school_year.school_year_for(d) == expected


@pytest.mark.parametrize(
    "grad_year, grade", [(2027, 12), (2028, 11), (2029, 10), (2030, 9), (2031, None), (2026, None)]
)
def test_grade_for(grad_year, grade):
    assert school_year.grade_for(grad_year, date(2026, 11, 6)) == grade


def test_grade_changes_in_july_not_january():
    assert school_year.grade_for(2030, date(2027, 6, 30)) == 9
    assert school_year.grade_for(2030, date(2027, 7, 1)) == 10


def test_bounds_and_label():
    assert school_year.school_year_bounds(2027) == (date(2026, 7, 1), date(2027, 6, 30))
    assert school_year.school_year_label(2027) == "2026-27"


def test_fraction_elapsed():
    assert school_year.fraction_of_year_elapsed(date(2026, 7, 1)) == 0
    assert 0.33 < school_year.fraction_of_year_elapsed(date(2026, 11, 6)) < 0.36
    assert school_year.fraction_of_year_elapsed(date(2027, 6, 30)) == 1
