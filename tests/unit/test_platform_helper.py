# -*- coding: utf-8 -*-

# local imports
from Code import platform_helper


def test_get_os_architecture():
    os_architecture = platform_helper.get_os_architecture()
    assert os_architecture in ['x86_64', 'x86', 'aarch64']


def test_architecture():
    assert platform_helper.architecture in ['x86_64', 'x86', 'aarch64']


def test_os_system():
    assert platform_helper.os_system in ['windows', 'linux', 'darwin']
