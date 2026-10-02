"""Ensure public validation errors cannot contain arbitrary exception text."""

# lib imports
import pytest

# local imports
from common.validation import ValidationError


@pytest.mark.parametrize('reason', ['private token', None, object()])
def test_public_errors_reject_unknown_messages(reason):
    with pytest.raises(TypeError, match='Validation errors require a catalog message'):
        ValidationError(reason)
