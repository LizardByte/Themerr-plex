import assert from 'node:assert/strict';
import test from 'node:test';
import { initSettings } from '../../web/js/config.js';
import { initTranslations, _ } from '../../web/js/i18n.js';

class Element {
    isConnected = true;
    listeners = {};
    value = '';
    disabled = false;
    children = [];
    dataset = {};
    attributes = {};
    addEventListener(name, fn) { this.listeners[name] = fn; }
    setAttribute(name, value) { this.attributes[name] = value; }
    removeAttribute() {}
    append(...children) { this.children.push(...children); }
}

function settings(t, request, linkedFields = []) {
    const ids = [
        'configForm',
        'save-button',
        'settings-save-status',
        'General-LOCALE',
        'password-form',
        'toast-region',
        'Themerr-STR_YOUTUBE_COOKIES',
        'cookie-toggle',
        'cookie-clear',
    ];
    const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
    const locale = elements['General-LOCALE'];
    locale.value = 'en';
    locale.id = 'General-LOCALE';
    locale.dataset.settingKey = 'LOCALE';
    locale.getAttribute = name => name === 'category' ? 'General' : 'LOCALE';
    const form = elements.configForm;
    const cookie = elements['Themerr-STR_YOUTUBE_COOKIES'];
    cookie.id = 'Themerr-STR_YOUTUBE_COOKIES';
    cookie.type = 'password';
    cookie.dataset = {
        settingKey: 'STR_YOUTUBE_COOKIES',
        secret: 'true',
        hasSecret: 'true',
    };
    cookie.getAttribute = () => 'Themerr';
    elements['cookie-toggle'].dataset.secretToggle = cookie.id;
    const secretIcons = [
        { dataset: { secretIcon: 'show' }, hidden: false },
        { dataset: { secretIcon: 'hide' }, hidden: true },
    ];
    elements['cookie-toggle'].querySelectorAll = () => secretIcons;
    elements['cookie-clear'].dataset.clearSecret = 'Themerr|STR_YOUTUBE_COOKIES';
    form.reportValidity = () => true;
    form.querySelector = () => elements['cookie-toggle'];
    form.querySelectorAll = selector => {
        if (selector === '[data-secret-toggle]') return [elements['cookie-toggle']];
        if (selector === '[data-clear-secret]') return [elements['cookie-clear']];
        return [
            locale,
            cookie,
        ];
    };
    const previous = { document: globalThis.document, window: globalThis.window,
        IntersectionObserver: globalThis.IntersectionObserver };
    t.after(() => Object.assign(globalThis, previous));
    const events = new EventTarget();
    globalThis.document = { getElementById: id => elements[id], createElement: () => new Element(),
        addEventListener: events.addEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events),
        querySelector: () => ({ content: 'token' }),
        querySelectorAll: selector => selector === '[form="configForm"][category]' ? linkedFields : [] };
    const reload = t.mock.fn();
    globalThis.window = { addEventListener() {}, confirm: t.mock.fn(() => false), location: { reload } };
    globalThis.IntersectionObserver = class { observe() {} disconnect() {} };
    t.mock.method(globalThis, 'setTimeout', () => 0);
    t.mock.method(globalThis, 'fetch', request);
    const controller = new AbortController();
    initSettings(controller.signal);
    const change = value => { locale.value = value; form.listeners.change(); };
    const save = () => form.listeners.submit({ preventDefault() {} });
    return { change, save, reload, elements, events, controller, cookie, secretIcons };
}

test('a saved locale change reloads immediately', async t => {
    const page = settings(t, async () => ({ ok: true, status: 200, json: async () => ({}) }));
    page.change('fr');
    await page.save();
    assert.equal(page.reload.mock.callCount(), 1);
    assert.equal(page.elements['save-button'].disabled, true);
});

test('settings with the same key in Plex and Jellyfin retain their config namespaces', async t => {
    let submitted;
    const page = settings(t, async (url, options) => {
        submitted = options.body;
        return { ok: true, status: 200, json: async () => ({}) };
    });
    page.elements.configForm.querySelectorAll = selector => selector !== '[category]' ? [] : ['Themerr', 'Jellyfin'].map(section => ({
        id: `${section}-BOOL_IGNORE_LOCKED_FIELDS`, type: 'checkbox', checked: section === 'Jellyfin',
        dataset: { settingKey: 'BOOL_IGNORE_LOCKED_FIELDS' },
        getAttribute: name => name === 'category' ? section : 'BOOL_IGNORE_LOCKED_FIELDS',
    }));
    await page.save();
    assert.equal(submitted.get('Themerr|BOOL_IGNORE_LOCKED_FIELDS'), 'false');
    assert.equal(submitted.get('Jellyfin|BOOL_IGNORE_LOCKED_FIELDS'), 'true');
});

test('MCP HTTP settings outside the settings form participate in dirty tracking and saving', async t => {
    const field = new Element();
    field.id = 'Network-MCP_HTTP';
    field.dataset.settingKey = 'MCP_HTTP';
    field.type = 'checkbox';
    field.getAttribute = () => 'Network';
    let submitted;
    const page = settings(t, async (url, options) => {
        submitted = options.body;
        return {
            ok: true,
            status: 200,
            json: async () => ({}),
        };
    }, [field]);
    field.checked = true;
    field.listeners.change();
    assert.equal(page.elements['save-button'].disabled, false);
    assert.equal(page.elements['settings-save-status'].textContent, 'Unsaved changes');
    await page.save();
    assert.equal(submitted.get('Network|MCP_HTTP'), 'true');
    assert.equal(page.elements['save-button'].disabled, true);
    field.checked = false;
    field.listeners.change();
    await page.save();
    assert.equal(submitted.get('Network|MCP_HTTP'), 'false');
});

test('cookies reveal on demand and can be masked again without resubmitting the saved value', async t => {
    const requests = [];
    const page = settings(t, async (url, options) => {
        requests.push({ url, options });
        return { ok: true, status: 200, json: async () => ({ value: 'private-cookie' }) };
    });
    assert.equal(requests.length, 0);
    const button = page.elements['cookie-toggle'];
    await button.listeners.click();
    assert.equal(requests[0].url, '/api/settings/youtube-cookies');
    assert.equal(requests[0].options.headers['X-CSRFToken'], 'token');
    assert.equal(page.cookie.value, 'private-cookie');
    assert.equal(page.cookie.type, 'text');
    assert.equal(button.attributes['aria-label'], 'Hide cookies');
    assert.equal(button.title, 'Hide cookies');
    assert.equal(button.attributes['aria-pressed'], 'true');
    assert.equal(page.secretIcons[0].hidden, true);
    assert.equal(page.secretIcons[1].hidden, false);
    await button.listeners.click();
    assert.equal(page.cookie.type, 'password');
    assert.equal(button.attributes['aria-label'], 'Show cookies');
    assert.equal(button.title, 'Show cookies');
    assert.equal(button.attributes['aria-pressed'], 'false');
    assert.equal(page.secretIcons[0].hidden, false);
    assert.equal(page.secretIcons[1].hidden, true);
    await page.save();
    assert.equal(requests[1].options.body.has('Themerr|STR_YOUTUBE_COOKIES'), false);
});

test('newly entered cookies toggle locally and leave the field after a successful save', async t => {
    let submitted;
    const page = settings(t, async (url, options) => {
        assert.equal(url, '/api/settings');
        submitted = options.body;
        return { ok: true, status: 200, json: async () => ({}) };
    });
    page.cookie.value = 'new-cookie';
    await page.elements['cookie-toggle'].listeners.click();
    assert.equal(page.cookie.type, 'text');
    await page.save();
    assert.equal(submitted.get('Themerr|STR_YOUTUBE_COOKIES'), 'new-cookie');
    assert.equal(page.cookie.value, '');
    assert.equal(page.cookie.type, 'password');
    assert.equal(page.elements['cookie-toggle'].attributes['aria-label'], 'Show cookies');
    assert.equal(page.secretIcons[0].hidden, false);
    assert.equal(page.secretIcons[1].hidden, true);
    assert.equal(page.cookie.dataset.hasSecret, 'true');
});

test('blank cookie fields preserve saved cookies and clearing is explicit', async t => {
    const bodies = [];
    const page = settings(t, async (url, options) => {
        bodies.push(options.body);
        return { ok: true, status: 200, json: async () => ({}) };
    });
    await page.save();
    assert.equal(bodies[0].has('Themerr|STR_YOUTUBE_COOKIES'), false);
    page.cookie.value = 'will-be-cleared';
    page.elements['cookie-clear'].checked = true;
    await page.save();
    assert.equal(bodies[1].has('Themerr|STR_YOUTUBE_COOKIES'), false);
    assert.equal(bodies[1].get('Themerr|STR_YOUTUBE_COOKIES|clear'), 'true');
    assert.equal(page.cookie.dataset.hasSecret, 'false');
    assert.equal(page.cookie.value, '');
    assert.equal(page.elements['cookie-clear'].checked, false);
});

test('cookie reveal errors keep the field masked and edits made during reveal are preserved', async t => {
    let release;
    let failed = true;
    const page = settings(t, () => {
        if (failed) return Promise.resolve({ ok: false, status: 500, json: async () => ({ message: 'Vault unavailable' }) });
        return new Promise(resolve => { release = resolve; });
    });
    const button = page.elements['cookie-toggle'];
    await button.listeners.click();
    assert.equal(page.cookie.type, 'password');
    assert.equal(page.cookie.value, '');
    assert.equal(button.disabled, false);
    failed = false;
    const pending = button.listeners.click();
    page.cookie.value = 'edited-cookie';
    page.elements.configForm.listeners.input();
    release({ ok: true, status: 200, json: async () => ({ value: 'stored-cookie' }) });
    await pending;
    assert.equal(page.cookie.value, 'edited-cookie');
    assert.equal(page.cookie.type, 'password');
});

test('cookie save failures keep edits and successful pending saves keep newer edits', async t => {
    let release;
    let failed = true;
    const page = settings(t, () => {
        if (failed) return Promise.resolve({ ok: false, status: 500, json: async () => ({ message: 'Vault unavailable' }) });
        return new Promise(resolve => { release = resolve; });
    });
    page.cookie.value = 'original-cookie';
    await page.save();
    assert.equal(page.cookie.value, 'original-cookie');
    failed = false;
    const pending = page.save();
    page.cookie.value = 'newer-cookie';
    page.elements.configForm.listeners.input();
    release({ ok: true, status: 200, json: async () => ({}) });
    await pending;
    assert.equal(page.cookie.value, 'newer-cookie');
    assert.equal(page.elements['save-button'].disabled, false);
});

test('failed locale saves keep the page and edits', async t => {
    const page = settings(t, async () => ({ ok: false, status: 400, json: async () => ({ message: 'Invalid locale' }) }));
    page.change('fr');
    await page.save();
    assert.equal(page.reload.mock.callCount(), 0);
    assert.equal(page.elements['save-button'].disabled, false);
});

test('edits made during a locale save are preserved, then the next successful save reloads', async t => {
    let release;
    const response = { ok: true, status: 200, json: async () => ({}) };
    let first = true;
    const page = settings(t, () => {
        if (!first) return Promise.resolve(response);
        first = false;
        return new Promise(resolve => { release = resolve; });
    });
    page.change('fr');
    const pending = page.save();
    page.elements.configForm.listeners.input();
    release(response);
    await pending;
    assert.equal(page.reload.mock.callCount(), 0);
    assert.equal(page.elements['save-button'].disabled, false);
    await page.save();
    assert.equal(page.reload.mock.callCount(), 1);
});

test('browser translations use the catalog and fall back for missing or empty messages', async () => {
    const root = { body: { classList: { contains: () => true } }, documentElement: { lang: 'fr' } };
    await initTranslations(root, async path => {
        assert.equal(path, '/translations');
        return { ok: true, json: async () => ({ 'All changes saved.': 'Modifications enregistrées.', Empty: '' }) };
    });
    assert.equal(_('All changes saved.'), 'Modifications enregistrées.');
    assert.equal(_('Empty'), 'Empty');
    assert.equal(_('Missing'), 'Missing');
});

test('unsaved settings can block navigation and their guard is removed on page disposal', async t => {
    const page = settings(t, async () => ({ ok: true, status: 200, json: async () => ({}) }));
    page.change('fr');
    assert.equal(page.events.dispatchEvent(new Event('themerr:before-navigate', { cancelable: true })), false);
    window.confirm = () => true;
    assert.equal(page.events.dispatchEvent(new Event('themerr:before-navigate', { cancelable: true })), true);
    window.confirm = () => false;
    page.controller.abort();
    assert.equal(page.events.dispatchEvent(new Event('themerr:before-navigate', { cancelable: true })), true);
});
