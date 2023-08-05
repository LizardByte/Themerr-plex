# standard imports
import os
import sys

# lib imports
from plexhints.agent_kit import Agent
import pytest

# add Contents directory to the system path
if os.path.isdir('Contents'):
    sys.path.append('Contents')

    # local imports
    from Code import Themerr
    from Code import webapp
else:
    raise Exception('Contents directory not found')


@pytest.fixture
def agent():
    # type: () -> Agent
    return Themerr()


@pytest.fixture
def test_client(scope='function'):
    """Create a test client for testing webapp endpoints"""
    app = webapp.app
    app.config['TESTING'] = True

    client = app.test_client()

    # Create a test client using the Flask application configured for testing
    with client as test_client:
        # Establish an application context
        with app.app_context():
            yield test_client  # this is where the testing happens!
