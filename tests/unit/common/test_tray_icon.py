"""System tray behavior with an in-memory pystray backend."""

# standard imports
from types import SimpleNamespace
from unittest.mock import Mock

# lib imports
import pytest

# local imports
import common
from common import tray_icon


class FakeIcon:
    HAS_DEFAULT_ACTION = True
    HAS_MENU = True

    def __init__(self, name):
        self.name = name
        self.visible = True
        self.stopped = False
        self.started = False

    def stop(self):
        self.stopped = True

    def run_detached(self):
        self.started = True


class FakeMenu(tuple):
    SEPARATOR = object()

    def __new__(cls, *items):
        return super().__new__(cls, items)

    def __call__(self, icon):
        return None


def test_initialize_and_browser(configured, monkeypatch):
    monkeypatch.setattr(tray_icon, 'icon_supported', True)
    monkeypatch.setattr(tray_icon, 'Icon', FakeIcon)
    monkeypatch.setattr(tray_icon, 'icon_class', FakeIcon)
    monkeypatch.setattr(tray_icon, 'MenuItem', lambda **kwargs: kwargs)
    monkeypatch.setattr(tray_icon, 'Menu', FakeMenu)
    monkeypatch.setattr(tray_icon.Image, 'open', lambda _: object())
    save = Mock()
    monkeypatch.setattr(tray_icon.config, 'save_config', save)

    icon = tray_icon.tray_initialize()
    assert icon.name == 'themerr-plex'
    assert isinstance(icon.menu, FakeMenu)
    assert callable(icon.menu)
    assert len(icon.menu) > 1
    original = configured['General']['LAUNCH_BROWSER']
    tray_icon.tray_browser()
    assert configured['General']['LAUNCH_BROWSER'] is not original
    save.assert_called_once_with(configured)

    monkeypatch.setattr(FakeIcon, 'HAS_MENU', False)
    minimal_menu = tray_icon.tray_initialize().menu
    assert isinstance(minimal_menu, FakeMenu)
    assert len(minimal_menu) == 1


def test_start_stop_toggle_and_signals(configured, monkeypatch):
    monkeypatch.setattr(tray_icon, 'icon_supported', False)
    assert tray_icon.tray_initialize() is False
    assert tray_icon.tray_run_threaded() is False
    assert tray_icon.tray_toggle() is False

    monkeypatch.setattr(tray_icon, 'icon_supported', True)
    monkeypatch.setattr(tray_icon, 'icon_class', FakeIcon)
    icon = FakeIcon('test')
    monkeypatch.setattr(tray_icon, 'icon_object', icon)
    monkeypatch.setattr(tray_icon, 'icon_running', False)
    monkeypatch.setattr(tray_icon, 'tray_initialize', lambda: icon)
    worker = SimpleNamespace(start=Mock())
    monkeypatch.setattr(tray_icon.threads, 'run_in_thread', lambda **_: worker)
    assert tray_icon.tray_toggle() is True
    worker.start.assert_called_once()
    tray_icon.tray_run()
    assert icon.started
    assert tray_icon.icon_running
    assert tray_icon.tray_toggle() is True
    assert icon.stopped
    assert not icon.visible
    assert not tray_icon.icon_running

    save = Mock()
    monkeypatch.setattr(tray_icon.config, 'save_config', save)
    tray_icon.tray_disable()
    assert configured['General']['SYSTEM_TRAY'] is False
    save.assert_called_once_with(configured)

    tray_icon.tray_quit()
    assert common.SIGNAL == 'shutdown'
    tray_icon.tray_restart()
    assert common.SIGNAL == 'restart'


def test_browser_destinations(monkeypatch):
    opened = []
    monkeypatch.setattr(tray_icon.helpers, 'open_url_in_browser', lambda url: opened.append(url) or True)
    monkeypatch.setattr(tray_icon.webapp, 'URL', 'https://localhost:9494')
    for action in (
        tray_icon.open_webapp, tray_icon.github_releases, tray_icon.donate_github,
        tray_icon.donate_patreon, tray_icon.donate_paypal,
    ):
        assert action()
    assert opened[0] == 'https://localhost:9494'
    assert len(set(opened)) == 5


@pytest.mark.skipif(not hasattr(tray_icon, 'MenuOnLeftClickIcon'), reason='Windows tray backend only')
def test_windows_left_click_opens_menu(monkeypatch):
    notified = []
    monkeypatch.setattr(tray_icon.Icon, '_on_notify', lambda self, wparam, lparam: notified.append(lparam))
    icon = object.__new__(tray_icon.MenuOnLeftClickIcon)
    icon._visible = False
    icon._running = False
    icon._icon_handle = None

    icon._on_notify(0, tray_icon.pystray_win32.WM_LBUTTONUP)
    icon._on_notify(0, tray_icon.pystray_win32.WM_RBUTTONUP)

    assert notified == [tray_icon.pystray_win32.WM_RBUTTONUP] * 2
