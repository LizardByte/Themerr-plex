import assert from 'node:assert/strict';
import test from 'node:test';
import { workspaceLink, initWorkspaceNavigation } from '../../web/js/workspace_navigation.js';

const origin = 'http://localhost';
function link(path) {
    const attributes = new Map([['href', path]]);
    return { href: origin + path, target: '', classList: { toggle() {}, contains: () => false },
        getAttribute: name => attributes.get(name), hasAttribute: name => attributes.has(name),
        setAttribute: (name, value) => attributes.set(name, value),
        removeAttribute: name => attributes.delete(name), querySelector: () => null };
}
function click(anchor, overrides = {}) {
    return { target: { closest: () => anchor }, button: 0, ...overrides };
}

test('only ordinary same-origin workspace links are intercepted', () => {
    const current = origin + '/settings/';
    const paths = new Set(['/settings/', '/servers']);
    assert.equal(workspaceLink(click(link('/servers')), current, paths).pathname, '/servers');
    for (const modifier of ['ctrlKey', 'metaKey', 'shiftKey', 'altKey', 'defaultPrevented']) {
        assert.equal(workspaceLink(click(link('/servers'), { [modifier]: true }), current, paths), undefined);
    }
    assert.equal(workspaceLink(click(link('/servers'), { button: 1 }), current, paths), undefined);
    const external = link('/servers');
    external.href = 'https://plex.example/servers';
    assert.equal(workspaceLink(click(external), current, paths), undefined);
    const blank = link('/servers');
    blank.target = '_blank';
    assert.equal(workspaceLink(click(blank), current, paths), undefined);
    const download = link('/servers');
    download.setAttribute('download', 'file');
    assert.equal(workspaceLink(click(download), current, paths), undefined);
    assert.equal(workspaceLink(click(link('/settings/#security')), current, paths), undefined);
    assert.equal(workspaceLink(click(link('/login')), current, paths), undefined);
    assert.equal(workspaceLink({ target: { closest: () => null } }, current, paths), undefined);
});

function fixture(t, customLoad) {
    const root = new EventTarget();
    const host = new EventTarget();
    host.location = { href: origin + '/home', origin, assign: t.mock.fn(), reload: t.mock.fn() };
    host.scrollX = 0;
    host.scrollY = 120;
    host.scrollTo = t.mock.fn();
    host.history = { state: null, go: t.mock.fn(),
        replaceState(state, unused, url) { this.state = state; host.location.href = url; },
        pushState(state, unused, url) { this.state = state; host.location.href = url; } };
    const enter = t.mock.fn();
    const leave = t.mock.fn();
    const reportError = t.mock.fn();
    const audio = { paused: false, currentTime: 17 };
    const widget = {};
    const breadcrumb = {};
    const meta = { content: 'old-token' };
    const logout = { value: 'old-token' };
    const nav = [link('/home'), link('/servers'), link('/logs')];
    const main = { setAttribute() {}, removeAttribute() {}, focus: t.mock.fn() };
    let content;
    let modals;
    function page(name) {
        const incoming = {
            title: name, documentElement: { lang: 'en' },
            querySelectorAll: selector => selector === '[data-workspace-link]' ? nav.map(anchor => {
                const copy = link(anchor.getAttribute('href'));
                if (copy.getAttribute('href') === name && !anchor.classList.contains('brand')) copy.setAttribute('aria-current', 'page');
                return copy;
            }) : [],
        };
        const body = { name, replaceWith(next) { content = next; } };
        const dialogs = { name, replaceWith(next) { modals = next; } };
        incoming.querySelector = selector => ({ '#theme-widget': widget, '#page-content': body,
            '#page-modals': dialogs, '.workspace-breadcrumb strong': { textContent: name },
            'meta[name="csrf-token"]': { content: 'new-token' },
            'script[type="module"][src]': { getAttribute: () => '/assets/app.js?v=1' } })[selector];
        return incoming;
    }
    const original = page('/home');
    content = original.querySelector('#page-content');
    modals = original.querySelector('#page-modals');
    root.documentElement = { lang: 'en' };
    root.body = { classList: { remove() {} } };
    root.querySelector = selector => ({ '#theme-player': audio, '#theme-widget': widget,
        '#main-content': main, '#page-content': content, '#page-modals': modals,
        '.workspace-breadcrumb strong': breadcrumb, 'meta[name="csrf-token"]': meta,
        '.mobile-menu': { setAttribute() {} },
        'script[type="module"][src]': { getAttribute: () => '/assets/app.js?v=1' } })[selector];
    root.querySelectorAll = selector => ({ '[data-workspace-link]': nav,
        '.logout-form [name="csrf_token"]': [logout], 'link[rel="stylesheet"]': [] })[selector] || [];
    const load = customLoad || t.mock.fn(async url => ({ ok: true, url, text: async () => new URL(url).pathname }));
    const controller = initWorkspaceNavigation({ enter, leave, reportError }, root, host, load, page);
    return { root, host, audio, widget, enter, leave, reportError, meta, logout, nav, load, controller, page };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('page changes and refreshes preserve the player, update history, navigation and CSRF tokens', async t => {
    const f = fixture(t);
    await f.controller.navigate(origin + '/servers');
    assert.equal(f.root.querySelector('#page-content').name, '/servers');
    assert.equal(f.root.querySelector('#theme-player'), f.audio);
    assert.equal(f.root.querySelector('#theme-widget'), f.widget);
    assert.equal(f.audio.paused, false);
    assert.equal(f.audio.currentTime, 17);
    assert.equal(f.root.title, '/servers');
    assert.equal(f.nav[1].getAttribute('aria-current'), 'page');
    assert.equal(f.host.history.state.workspacePosition, 1);
    assert.equal(f.meta.content, 'new-token');
    assert.equal(f.logout.value, 'new-token');
    await f.controller.navigate(origin + '/servers', { replace: true });
    assert.equal(f.host.history.state.workspacePosition, 1);
    assert.equal(f.enter.mock.callCount(), 2);
    assert.equal(f.leave.mock.callCount(), 2);
});

test('Back restores workspace content and saved scroll without interrupting playback', async t => {
    const f = fixture(t);
    await f.controller.navigate(origin + '/servers');
    f.host.location.href = origin + '/home';
    const event = new Event('popstate');
    event.state = { workspacePosition: 0, scroll: [0, 120] };
    f.host.dispatchEvent(event);
    await flush();
    assert.equal(f.root.querySelector('#page-content').name, '/home');
    assert.deepEqual(f.host.scrollTo.mock.calls.at(-1).arguments, [0, 120]);
    assert.equal(f.audio.paused, false);
    assert.equal(f.host.history.state.workspacePosition, 1); // popstate does not push another entry.
});

test('cancelled navigation preserves the current page and reverses a cancelled Back action', async t => {
    const f = fixture(t);
    await f.controller.navigate(origin + '/servers');
    f.root.addEventListener('themerr:before-navigate', event => event.preventDefault());
    await f.controller.navigate(origin + '/logs');
    assert.equal(f.load.mock.callCount(), 1);
    f.host.location.href = origin + '/home';
    const event = new Event('popstate');
    event.state = { workspacePosition: 0 };
    f.host.dispatchEvent(event);
    assert.deepEqual(f.host.history.go.mock.calls[0].arguments, [1]);
    assert.equal(f.root.querySelector('#page-content').name, '/servers');
});

test('a slower navigation response cannot replace the newer page', async t => {
    const pending = [];
    const f = fixture(t, (url, options) => new Promise(resolve => pending.push({ url, options, resolve })));
    const first = f.controller.navigate(origin + '/servers');
    const second = f.controller.navigate(origin + '/logs');
    assert.equal(pending[0].options.signal.aborted, true);
    pending[1].resolve({ ok: true, text: async () => '/logs' });
    await second;
    pending[0].resolve({ ok: true, text: async () => '/servers' });
    await first;
    assert.equal(f.root.title, '/logs');
    assert.equal(f.enter.mock.callCount(), 1);
    assert.equal(f.host.location.assign.mock.callCount(), 0);
});

test('authentication redirects open login and failed fetches retain the page and player', async t => {
    let response = { ok: true, redirected: true, url: origin + '/login' };
    const f = fixture(t, async () => response);
    await f.controller.navigate(origin + '/servers');
    assert.equal(f.host.location.assign.mock.calls[0].arguments[0], origin + '/login');
    response = { ok: true, text: async () => { throw new Error('Network error'); } };
    await f.controller.navigate(origin + '/servers');
    assert.equal(f.host.location.assign.mock.callCount(), 1);
    assert.equal(f.reportError.mock.callCount(), 1);
    assert.equal(f.audio.paused, false);
    assert.equal(f.audio.currentTime, 17);
    assert.equal(f.root.querySelector('#page-content').name, '/home');
    assert.equal(f.leave.mock.callCount(), 0);
});

test('Overview is active even when the brand links to the same page', async t => {
    const f = fixture(t);
    const brand = link('/home');
    brand.classList.contains = name => name === 'brand';
    f.nav.unshift(brand);
    await f.controller.navigate(origin + '/servers');
    await f.controller.navigate(origin + '/home');
    assert.equal(f.nav[1].getAttribute('aria-current'), 'page');
    assert.equal(brand.getAttribute('aria-current'), undefined);
});

test('expired API-page sessions return to the login form', async t => {
    const f = fixture(t, async () => ({ ok: false, status: 401 }));
    await f.controller.navigate(origin + '/api/docs');
    assert.equal(f.host.location.assign.mock.calls[0].arguments[0], '/login?next=%2Fapi%2Fdocs');
    assert.equal(f.leave.mock.callCount(), 0);
});

test('rebuilt asset fingerprints do not reload the document or discard playback', async t => {
    const f = fixture(t);
    const oldPage = f.page('/servers');
    const originalSelector = oldPage.querySelector;
    oldPage.querySelector = selector => selector === 'script[type="module"][src]'
        ? { getAttribute: () => '/assets/app.js?v=rebuilt' } : originalSelector(selector);
    const controller = initWorkspaceNavigation({ enter: f.enter, leave: f.leave }, f.root, f.host,
        async () => ({ ok: true, text: async () => '' }), () => oldPage);
    await controller.navigate(origin + '/servers');
    assert.equal(f.root.title, '/servers');
    assert.equal(f.audio.paused, false);
    assert.equal(f.audio.currentTime, 17);
    assert.equal(f.host.location.assign.mock.callCount(), 0);
});

test('temporary page errors and malformed responses preserve the player and allow retry', async t => {
    let result = { ok: false, status: 503 };
    const f = fixture(t, async () => result);
    await f.controller.navigate(origin + '/servers');
    assert.equal(f.reportError.mock.callCount(), 1);
    result = { ok: true, text: async () => 'malformed' };
    const broken = initWorkspaceNavigation({ enter: f.enter, leave: f.leave, reportError: f.reportError },
        f.root, f.host, async () => result, () => ({ querySelector: () => null }));
    await broken.navigate(origin + '/servers');
    assert.equal(f.reportError.mock.callCount(), 2);
    assert.equal(f.root.querySelector('#page-content').name, '/home');
    assert.equal(f.audio.paused, false);
    assert.equal(f.host.location.assign.mock.callCount(), 0);
    result = { ok: true, text: async () => '/servers' };
    await f.controller.navigate(origin + '/servers');
    assert.equal(f.root.querySelector('#page-content').name, '/servers');
});

test('a failed Back request restores its history entry while audio continues', async t => {
    let fail = false;
    const f = fixture(t, async url => ({ ok: !fail, url, text: async () => new URL(url).pathname }));
    await f.controller.navigate(origin + '/servers');
    fail = true;
    f.host.location.href = origin + '/home';
    const event = new Event('popstate');
    event.state = { workspacePosition: 0 };
    f.host.dispatchEvent(event);
    await flush();
    assert.deepEqual(f.host.history.go.mock.calls[0].arguments, [1]);
    assert.equal(f.root.querySelector('#page-content').name, '/servers');
    assert.equal(f.audio.paused, false);
});

test('canonical workspace redirects use soft navigation and keep the player', async t => {
    const f = fixture(t, async () => ({ ok: true, redirected: true, url: origin + '/servers',
        text: async () => '/servers' }));
    await f.controller.navigate(origin + '/home');
    assert.equal(f.host.location.href, origin + '/servers');
    assert.equal(f.root.querySelector('#page-content').name, '/servers');
    assert.equal(f.audio.paused, false);
    assert.equal(f.host.location.assign.mock.callCount(), 0);
});
