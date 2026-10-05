import assert from 'node:assert/strict';
import test from 'node:test';
import { initServers } from '../../web/js/servers.js';

class Element {
    constructor(tag = 'div') { this.tag = tag; }
    children = [];
    listeners = {};
    dataset = {};
    disabled = false;
    textContent = '';
    value = '';
    isConnected = true;
    addEventListener(name, listener) { this.listeners[name] = listener; }
    setAttribute() {}
    removeAttribute() {}
    replaceChildren() { this.children = []; this.textContent = ''; }
    append(...elements) {
        elements.forEach((element, index) => { element.nextElementSibling = elements[index + 1]; });
        this.children.push(...elements);
        if (this.tag === 'select' && !this.value) this.value = elements[0].value;
    }
    querySelectorAll(selector) {
        return this.children.flatMap(child => [
            ...(child.tag === 'input' && (selector !== 'input:checked' || child.checked) ? [child] : []),
            ...child.querySelectorAll(selector),
        ]);
    }
    contains(element) { return this === element || this.children.some(child => child.contains(element)); }
    focus() { this.focused = true; }
    click() { return this.listeners.click(); }
}

function serverForm(id, selected) {
    const form = new Element('form');
    form.dataset.serverId = id;
    form.elements = { enabled: { checked: true } };
    const picker = new Element('details');
    const options = new Element();
    selected.forEach(id => {
        const label = new Element('label');
        const input = Object.assign(new Element('input'), { value: id, checked: true });
        const text = Object.assign(new Element('span'), { textContent: `Library ${id}` });
        label.append(input, text);
        options.append(label);
    });
    const summary = new Element('summary');
    const status = new Element('p');
    picker.append(options, summary, status);
    picker.querySelector = selector => ({ '[data-library-options]': options,
        '[data-library-summary]': summary, '[data-library-status]': status, summary })[selector];
    const save = new Element('button');
    form.querySelector = selector => selector === '[data-library-picker]' ? picker : save;
    form.append(picker, save);
    return { form, picker, options, summary, status };
}

function page(context, responses, savedServers = [], jellyfin = {}) {
    const previous = { document: globalThis.document, window: globalThis.window, FormData: globalThis.FormData };
    context.after(() => Object.assign(globalThis, previous));
    const elements = Object.fromEntries(['plex-auth-start', 'plex-auth-status', 'plex-auth-link', 'plex-auth-disconnect',
        'discovery-results', 'manual-server-form', 'toast-region'].map(id => [id, new Element()]));
    const buttons = ['account', 'local'].map(source => Object.assign(new Element('button'), { dataset: { discover: source } }));
    const forms = savedServers.map(({ id, selected = [] }) => serverForm(id, selected));
    if (jellyfin.connect) {
        const form = new Element('form');
        form.values = { url: 'http://jellyfin.example:8096', api_key: 'private-key' };
        form.querySelector = () => new Element('button');
        form.reset = context.mock.fn(() => { form.values.api_key = ''; });
        elements['jellyfin-server-form'] = form;
    }
    const connectors = (jellyfin.servers || []).map(id => {
        const form = new Element('form');
        const status = new Element('output');
        const button = new Element('button');
        form.dataset.serverId = id;
        form.elements = { themerr_url: { value: '' } };
        form.querySelector = selector => selector === '[data-connector-status]' ? status : button;
        return { form, status, button };
    });
    const events = new EventTarget();
    globalThis.document = {
        getElementById: id => elements[id], createElement: tag => new Element(tag),
        querySelectorAll: selector => ({ '[data-discover]': buttons,
            '[data-server-form]': forms.map(({ form }) => form),
            '[data-connector-form]': connectors.map(({ form }) => form) })[selector] || [],
        querySelector: () => ({ content: 'csrf-token' }),
        addEventListener: events.addEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events),
    };
    globalThis.FormData = class {
        constructor(form) { this.form = form; }
        get(name) { return this.form.values?.[name] || this.form.elements?.[name]?.value || ''; }
        getAll() { return this.form.querySelectorAll('input:checked').map(input => input.value); }
    };
    const reload = context.mock.fn();
    globalThis.window = { addEventListener() {}, location: { reload, origin: 'http://themerr.example:9494' } };
    const fetch = context.mock.method(globalThis, 'fetch', async () => {
        const response = responses.shift();
        return { ok: !response.error, status: response.error ? 502 : 200, json: async () => response.body };
    });
    context.mock.method(globalThis, 'setTimeout', () => 0);
    const controller = new AbortController();
    initServers(controller.signal);
    return { elements, buttons, fetch, reload, forms, controller, connectors };
}

test('Jellyfin connection submits its key with CSRF and clears it after success', async context => {
    const { elements, fetch, reload } = page(context, [{ body: { message: 'Connected' } }], [], { connect: true });
    const form = elements['jellyfin-server-form'];
    form.listeners.submit({ preventDefault() {} });
    await new Promise(setImmediate);
    assert.equal(fetch.mock.calls[0].arguments[0], '/api/jellyfin/servers');
    assert.deepEqual(JSON.parse(fetch.mock.calls[0].arguments[1].body), {
        url: 'http://jellyfin.example:8096', api_key: 'private-key',
    });
    assert.equal(fetch.mock.calls[0].arguments[1].headers['X-CSRFToken'], 'csrf-token');
    assert.equal(form.values.api_key, '');
    assert.equal(form.reset.mock.callCount(), 1);
    assert.equal(reload.mock.callCount(), 1);
});

test('connector status and installation stay scoped to the selected Jellyfin server', async context => {
    const { connectors, fetch } = page(context, [{ body: { message: 'Install the matching connector.' } },
        { body: { message: 'Restart Jellyfin.' } }], [], { servers: ['jellyfin:abc'] });
    await new Promise(setImmediate);
    const { form, status } = connectors[0];
    assert.equal(status.textContent, 'Install the matching connector.');
    assert.equal(form.elements.themerr_url.value, 'http://themerr.example:9494');
    form.elements.themerr_url.value = 'https://trusted.example/themerr';
    form.listeners.submit({ preventDefault() {} });
    await new Promise(setImmediate);
    assert.equal(fetch.mock.calls[1].arguments[0], '/api/jellyfin/servers/jellyfin%3Aabc/connector');
    assert.deepEqual(JSON.parse(fetch.mock.calls[1].arguments[1].body), { themerr_url: 'https://trusted.example/themerr' });
    assert.equal(status.textContent, 'Restart Jellyfin.');
});

test('empty LAN discovery explains GDM and offers account or manual connections', async context => {
    const { elements, buttons } = page(context, [{ body: { servers: [] } }]);
    await buttons[1].click();
    assert.match(elements['discovery-results'].textContent, /No Plex servers responded on LAN/);
    assert.match(elements['discovery-results'].textContent, /GDM/);
    assert.match(elements['discovery-results'].textContent, /account or manual address/);
    assert.equal(buttons[1].disabled, false);
});

test('failed discovery clears its loading state and shows the failure', async context => {
    const { elements, buttons } = page(context, [{ error: true, body: { message: 'Discovery failed.' } }]);
    await buttons[0].click();
    assert.equal(elements['discovery-results'].textContent, 'Discovery failed.');
    assert.equal(buttons[0].disabled, false);
});

test('connection labels show HTTPS and scope, preserve the advertised URI, and allow retry after a timeout', async context => {
    const url = 'https://192-168-1-11.server.plex.direct:32400';
    const { elements, buttons, fetch, reload } = page(context, [{ body: { servers: [{ id: 'one', name: 'Archer',
        connections: [{ url: 'https://relay.example:8443', local: false, relay: true },
            { url, local: true, relay: false }] }] } },
    { error: true, body: { message: 'The Plex connection timed out.' } }]);
    await buttons[0].click();
    const [, addresses, connect] = elements['discovery-results'].children[0].children;
    assert.equal(addresses.children[0].textContent, `Local · HTTPS · ${url}`);
    assert.match(addresses.children[1].textContent, /^Relay · HTTPS/);
    await connect.click();
    assert.deepEqual(JSON.parse(fetch.mock.calls[1].arguments[1].body), { url, resource_id: 'one' });
    assert.equal(elements['toast-region'].children[0].children[0].textContent, 'The Plex connection timed out.');
    assert.equal(connect.disabled, false);
    assert.equal(reload.mock.callCount(), 0);
});

const libraries = (entries, cached = false) => ({ body: { libraries: entries.map(([id, title]) => ({ id, title })), cached } });
const open = async picker => { picker.open = true; await picker.listeners.toggle(); };

test('library dropdowns load lazily for each server and preserve saved and unavailable IDs', async context => {
    const { forms, fetch } = page(context, [libraries([['1', 'Movies'], ['2', '<b>Shows</b>']]),
        libraries([['1', 'Other movies']])], [{ id: 'a/b', selected: ['2', '9'] }, { id: 'b', selected: ['1'] }]);
    assert.equal(fetch.mock.callCount(), 0);
    const [first, second] = forms;
    await open(first.picker);
    assert.equal(fetch.mock.calls[0].arguments[0], '/api/servers/a%2Fb/libraries');
    assert.equal(fetch.mock.calls[0].arguments[1].method, 'GET');
    assert.deepEqual(first.options.querySelectorAll('input:checked').map(input => input.value), ['2', '9']);
    assert.equal(first.options.children[1].children[1].textContent, '<b>Shows</b>');
    assert.equal(first.options.children[2].children[1].textContent, 'Unavailable library (9)');
    assert.equal(first.summary.textContent, '<b>Shows</b>, Unavailable library (9)');
    await open(first.picker);
    assert.equal(fetch.mock.callCount(), 1);
    await open(second.picker);
    assert.equal(fetch.mock.calls[1].arguments[0], '/api/servers/b/libraries');
    assert.equal(second.summary.textContent, 'Other movies');
});

test('multiple checked libraries save as IDs and clearing all choices saves an empty string', async context => {
    const { forms, fetch } = page(context, [libraries([['1', 'Movies'], ['2', 'Shows']]),
        { body: { message: 'Saved' } }, { body: { message: 'Saved' } }], [{ id: 'a' }]);
    const { form, picker, options, summary } = forms[0];
    await open(picker);
    options.querySelectorAll('input').forEach(input => { input.checked = true; });
    options.listeners.change();
    assert.equal(summary.textContent, 'Movies, Shows');
    await form.listeners.submit({ preventDefault() {} });
    assert.deepEqual(JSON.parse(fetch.mock.calls[1].arguments[1].body), {
        enabled: true, data_directory: '', ignored_libraries: '1,2',
    });
    options.querySelectorAll('input').forEach(input => { input.checked = false; });
    options.listeners.change();
    assert.equal(summary.textContent, 'Select libraries to ignore');
    await form.listeners.submit({ preventDefault() {} });
    assert.equal(JSON.parse(fetch.mock.calls[2].arguments[1].body).ignored_libraries, '');
});

test('only string FormData entries are saved as ignored library IDs', async context => {
    const { forms, fetch } = page(context, [{ body: { message: 'Saved' } }], [{ id: 'a' }]);
    context.mock.method(globalThis.FormData.prototype, 'getAll', () => ['1', new File(['data'], 'upload.txt'), '2']);
    await forms[0].form.listeners.submit({ preventDefault() {} });
    assert.equal(JSON.parse(fetch.mock.calls[0].arguments[1].body).ignored_libraries, '1,2');
});

test('failed and cached library loads retain selections and can be retried', async context => {
    const { forms } = page(context, [{ error: true, body: { message: 'Unavailable' } },
        libraries([['1', 'Cached movies']], true), libraries([['1', 'Movies'], ['2', 'Shows']])],
    [{ id: 'a', selected: ['1'] }]);
    const { picker, options, status } = forms[0];
    await open(picker);
    assert.match(status.textContent, /Unable to load libraries/);
    assert.equal(options.querySelectorAll('input:checked')[0].value, '1');
    await open(picker);
    assert.match(status.textContent, /Showing cached libraries/);
    await open(picker);
    assert.equal(status.textContent, '');
    assert.equal(options.children.length, 2);
    assert.equal(options.querySelectorAll('input:checked')[0].value, '1');
});

test('empty library lists explain the state and the dropdown closes with Escape or an outside click', async context => {
    const { forms, controller } = page(context, [libraries([])], [{ id: 'a' }]);
    const { picker, summary, status } = forms[0];
    await open(picker);
    assert.equal(status.textContent, 'This server has no libraries.');
    picker.listeners.keydown({ key: 'Escape' });
    assert.equal(picker.open, false);
    assert.equal(summary.focused, true);
    picker.open = true;
    document.dispatchEvent(new Event('click'));
    assert.equal(picker.open, false);
    controller.abort();
    picker.open = true;
    document.dispatchEvent(new Event('click'));
    assert.equal(picker.open, true);
});

test('a pending library response preserves edits made while loading', async context => {
    const { forms } = page(context, [], [{ id: 'a', selected: ['1'] }]);
    let release;
    context.mock.method(globalThis, 'fetch', () => new Promise(resolve => { release = resolve; }));
    const { picker, options, summary } = forms[0];
    const pending = open(picker);
    options.querySelectorAll('input:checked')[0].checked = false;
    release({ ok: true, status: 200, json: async () => libraries([['1', 'Movies']]).body });
    await pending;
    assert.equal(options.querySelectorAll('input:checked').length, 0);
    assert.equal(summary.textContent, 'Select libraries to ignore');
});

test('library loading does not replace controls after page navigation', async context => {
    const { forms, controller } = page(context, [], [{ id: 'a', selected: ['1'] }]);
    let release;
    context.mock.method(globalThis, 'fetch', () => new Promise(resolve => { release = resolve; }));
    const { picker, summary, options } = forms[0];
    const pending = open(picker);
    controller.abort();
    release({ ok: true, status: 200, json: async () => libraries([['1', 'Movies']]).body });
    await pending;
    assert.equal(summary.textContent, 'Library 1');
    assert.equal(options.children[0].children[1].textContent, 'Library 1');
});
