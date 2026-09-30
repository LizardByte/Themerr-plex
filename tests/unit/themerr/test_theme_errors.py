"""Per-item theme errors survive a dashboard refresh and clear after success."""

from themerr import theme_errors


def test_error_round_trip(configured):
    theme_errors.set_error(42, 'Video unavailable')
    assert theme_errors.get_errors() == {'42': 'Video unavailable'}
    theme_errors.set_error(42, None)
    assert theme_errors.get_errors() == {}


def test_failure_reason_is_normalized(configured):
    theme_errors.set_error(42, 'Video unavailable at https://youtube.example/watch?v=1\nPlease retry')
    assert theme_errors.get_errors() == {'42': 'Video unavailable at [URL] Please retry'}
