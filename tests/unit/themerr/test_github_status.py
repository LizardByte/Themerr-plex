"""Verify the persisted GitHub request limit and publication failure behavior."""

# standard imports
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

# lib imports
import pytest
import requests

# local imports
from themerr import github_status, storage

RUN_ID = 123456
PUBLICATION = '2026-10-02T12:00:00Z'


def run(**overrides):
    return {'id': RUN_ID, 'updated_at': PUBLICATION, 'workflow_id': 34813093, 'status': 'completed',
            'conclusion': 'success', **overrides}


def response(payload=None, status=200):
    value = Mock(status_code=status)
    value.json.return_value = payload if payload is not None else {
        'workflow_runs': [run()],
    }
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    return value


def test_hourly_limit_survives_restart_and_server_scopes(configured, monkeypatch):
    clock = Mock(return_value=10000)
    get = Mock(return_value=response())
    monkeypatch.setattr(github_status.time, 'time', clock)
    monkeypatch.setattr(github_status.requests, 'get', get)
    first = github_status.publication_status()
    assert first == {
        'updated_at': '2026-10-02T12:00:00+00:00',
        'url': 'https://github.com/LizardByte/ThemerrDB/actions/runs/' + str(RUN_ID),
        'checked_at': 10000, 'next_check': 13600, 'stale': False,
    }
    get.assert_called_once_with(
        'https://api.github.com/repos/LizardByte/ThemerrDB/actions/workflows/34813093/runs',
        params={'status': 'success', 'per_page': 1},
        headers={'Accept': 'application/vnd.github+json'}, timeout=10, allow_redirects=False,
    )
    storage.close()
    clock.return_value = 13599
    with storage.server_scope('another-server'):
        assert github_status.publication_status() == first
    get.assert_called_once()
    clock.return_value = 13600
    assert github_status.publication_status()['next_check'] == 17200
    assert get.call_count == 2


@pytest.mark.parametrize('failure', [
    requests.ConnectionError(), requests.Timeout(), requests.HTTPError(),
    ValueError('Invalid JSON'), TypeError('Invalid payload'), KeyError('workflow_runs'),
])
def test_failed_check_preserves_publication_and_does_not_retry_early(configured, monkeypatch, failure):
    clock = Mock(return_value=10000)
    get = Mock(return_value=response())
    monkeypatch.setattr(github_status.time, 'time', clock)
    monkeypatch.setattr(github_status.requests, 'get', get)
    first = github_status.publication_status()
    clock.return_value = 13600
    get.side_effect = failure
    failed = github_status.publication_status()
    assert failed['stale'] is True
    assert failed['updated_at'] == first['updated_at'] and failed['url'] == first['url']
    assert failed['next_check'] == 17200
    storage.close()
    clock.return_value = 17199
    assert github_status.publication_status() == failed
    assert get.call_count == 2
    get.side_effect = None
    clock.return_value = 17200
    assert github_status.publication_status()['stale'] is False
    assert get.call_count == 3


@pytest.mark.parametrize('payload, status', [
    ({'workflow_runs': [run()]}, 302),
    ({'workflow_runs': [run(id='bad-link')]}, 200),
    ({'workflow_runs': [run(updated_at='2026-10-02T12:00:00')]}, 200),
    ({'workflow_runs': [run(updated_at='invalid')]}, 200),
    ({'workflow_runs': [run(conclusion='failure')]}, 200),
    ({'workflow_runs': [run(status='in_progress')]}, 200),
    ({'workflow_runs': [run(workflow_id=999)]}, 200),
    ({'workflow_runs': {}}, 200), ({}, 200), ([], 200),
])
def test_invalid_response_is_not_published_or_retried(configured, monkeypatch, payload, status):
    get = Mock(return_value=response(payload, status))
    monkeypatch.setattr(github_status.requests, 'get', get)
    failed = github_status.publication_status()
    assert failed['updated_at'] is None and failed['stale'] is True
    assert failed['url'] == github_status._WORKFLOW_URL
    assert github_status.publication_status() == failed
    get.assert_called_once()


def test_no_successful_deployment_is_unknown_without_a_failure_warning(configured, monkeypatch):
    get = Mock(return_value=response({'workflow_runs': []}))
    monkeypatch.setattr(github_status.requests, 'get', get)
    status = github_status.publication_status()
    assert status['updated_at'] is None and status['stale'] is False
    assert status['url'] == github_status._WORKFLOW_URL
    assert github_status.publication_status() == status
    get.assert_called_once()


def test_concurrent_page_requests_share_one_check(configured, monkeypatch):
    started, release = Event(), Event()

    def request(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return response()

    get = Mock(side_effect=request)
    monkeypatch.setattr(github_status.requests, 'get', get)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(github_status.publication_status)
        assert started.wait(10)
        second = executor.submit(github_status.publication_status)
        release.set()
        assert first.result(timeout=10) == second.result(timeout=10)
    get.assert_called_once()


def test_interrupted_attempt_still_reserves_the_hour(configured, monkeypatch):
    get = Mock(side_effect=KeyboardInterrupt())
    monkeypatch.setattr(github_status.requests, 'get', get)
    with pytest.raises(KeyboardInterrupt):
        github_status.publication_status()
    storage.close()
    assert github_status.publication_status()['stale'] is True
    get.assert_called_once()
