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
else:
    raise Exception('Contents directory not found')


@pytest.fixture
def agent():
    # type: () -> Agent
    return Themerr()
