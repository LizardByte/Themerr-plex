"""Per-item theme errors survive a dashboard refresh and clear after success."""

from pathlib import Path

from themerr import theme_errors


def test_error_round_trip(configured):
    theme_errors.set_error(42, 'Video unavailable')
    assert theme_errors.get_errors() == {'42': 'Video unavailable'}
    theme_errors.set_error(42, None)
    assert theme_errors.get_errors() == {}


def test_invalid_error_record_does_not_break_dashboard(configured):
    Path(theme_errors._path()).write_text('{invalid', encoding='utf-8')
    assert theme_errors.get_errors() == {}
    theme_errors.set_error(42, 'Video unavailable')
    assert theme_errors.get_errors() == {'42': 'Video unavailable'}
