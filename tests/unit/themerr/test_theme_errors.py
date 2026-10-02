"""Per-item theme errors survive a dashboard refresh and clear after success."""

# lib imports
import pytest

# local imports
from themerr import theme_errors


def test_error_round_trip(configured):
    theme_errors.set_error(42, 'Video unavailable')
    assert theme_errors.get_errors() == {'42': 'Video unavailable'}
    theme_errors.set_error(42, None)
    assert theme_errors.get_errors() == {}


def test_failure_reason_is_normalized(configured):
    theme_errors.set_error(42, 'Video unavailable at https://youtube.example/watch?v=1\nPlease retry')
    assert theme_errors.get_errors() == {'42': 'Video unavailable at [URL] Please retry'}


@pytest.mark.parametrize(('reason', 'editable'), [
    (None, False), ('Video unavailable', True), ('This video is not available', True),
    ('Private video. Sign in to view it.', True), ('Video has been removed', True),
    ('Sign in to confirm your age', True), ('Video blocked due to copyright', True),
    ('Video unavailable in your country', False), ('Geo-restricted video', False),
    ('Video unavailable in the United States', True),
    ('Unable to download webpage: connection timed out', False), ('Theme upload failed: HTTP 406', False),
    ('Sign in to confirm you are not a bot', False), ('HTTP Error 403: Forbidden', False),
])
def test_edit_action_only_for_source_video_issues(reason, editable):
    assert theme_errors.is_video_issue(reason) is editable
