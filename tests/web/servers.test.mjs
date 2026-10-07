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
    attributes = {};
    isConnected = true;
    addEventListener(name, listener) { this.listeners[name] = listener; }
    setAttribute(name, value) { this.attributes[name] = value; }
    getAttribute(name) { return this.attributes[name]; }
    removeAttribute(name) { delete this.attributes[name]; }
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

function page(context, responses, savedServers = [], jellyfin = {}, sshServers = []) {
    const previous = { document: globalThis.document, window: globalThis.window, FormData: globalThis.FormData };
    context.after(() => Object.assign(globalThis, previous));
    const elements = Object.fromEntries(['plex-auth-start', 'plex-auth-status', 'plex-auth-link', 'plex-auth-disconnect',
        'discovery-results', 'manual-server-form', 'toast-region'].map(id => [id, new Element()]));
    const buttons = ['account', 'local'].map(source => Object.assign(new Element('button'), { dataset: { discover: source } }));
    const forms = savedServers.map(({ id, selected = [] }) => serverForm(id, selected));
    if (jellyfin.connect) {
        const form = new Element('form');
        form.values = { url: 'http://jellyfin.example:8096', api_key: 'private-key' };
        form.elements = { url: new Element('input'), api_key: new Element('input') };
        form.querySelector = () => new Element('button');
        form.reset = context.mock.fn(() => { form.values.api_key = ''; });
        elements['jellyfin-server-form'] = form;
    }
    if (jellyfin.discover) {
        elements['jellyfin-discover'] = new Element('button');
        elements['jellyfin-discovery-results'] = new Element('div');
    }
    if (jellyfin.tabs) {
        const tabs = ['plex', 'jellyfin'].map(kind => {
            const tab = new Element('button');
            tab.id = `add-${kind}-tab`;
            tab.setAttribute('aria-controls', `add-${kind}-panel`);
            elements[tab.id] = tab;
            elements[`add-${kind}-panel`] = new Element();
            return tab;
        });
        const tablist = new Element();
        tablist.querySelectorAll = () => tabs;
        elements['add-server-tabs'] = tablist;
    }
    const connectors = (jellyfin.servers || []).map(id => {
        const form = new Element('form');
        const status = new Element('output');
        const button = new Element('button');
        const restart = new Element('button');
        const card = new Element('article');
        card.querySelector = selector => selector === '[data-restart-server]' ? restart : undefined;
        form.closest = selector => selector === '.server-card' ? card : undefined;
        form.dataset.serverId = id;
        form.dataset.autoUpdate = String(Boolean(jellyfin.automatic));
        form.elements = { themerr_url: { value: '' } };
        form.querySelector = selector => ({ '[data-connector-status]': status,
            'button[type="submit"]': button })[selector];
        return { form, status, button, restart };
    });
    const sshForms = sshServers.map(id => {
        const form = new Element('form');
        form.dataset.serverId = id;
        form.dataset.configured = 'false';
        form.elements = Object.fromEntries(Object.entries({
            host: 'plex.example',
            port: '22',
            username: 'cleanup',
            data_directory: '/plex',
            host_fingerprint: 'SHA256:verified',
            auth_type: 'password',
            private_key: '',
            passphrase: '',
            password: 'private-password',
        }).map(([name, value]) => [
            name,
            Object.assign(new Element('input'), { value }),
        ]));
        const status = new Element('output');
        const button = new Element('button');
        const check = new Element('button');
        const remove = new Element('button');
        const keyFields = new Element();
        const passwordFields = new Element();
        form.querySelector = selector => ({
            '[data-ssh-status]': status,
            '[data-check-ssh]': check,
            '[data-remove-ssh]': remove,
            '[data-ssh-key-fields]': keyFields,
            '[data-ssh-password-fields]': passwordFields,
            'button[type="submit"]': button,
        })[selector];
        return {
            form,
            status,
            button,
            check,
            remove,
            keyFields,
            passwordFields,
        };
    });
    const events = new EventTarget();
    globalThis.document = {
        getElementById: id => elements[id], createElement: tag => new Element(tag),
        querySelectorAll: selector => ({ '[data-discover]': buttons,
            '[data-server-form]': forms.map(({ form }) => form),
            '[data-connector-form]': connectors.map(({ form }) => form),
            '[data-plex-ssh-form]': sshForms.map(({ form }) => form) })[selector] || [],
        querySelector: () => ({ content: 'csrf-token' }),
        addEventListener: events.addEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events),
    };
    globalThis.FormData = class {
        constructor(form) { this.form = form; }
        get(name) { return this.form.values?.[name] || this.form.elements?.[name]?.value || ''; }
        getAll() { return this.form.querySelectorAll('input:checked').map(input => input.value); }
    };
    const reload = context.mock.fn();
    globalThis.window = { addEventListener() {}, confirm: context.mock.fn(() => true),
        location: { reload, origin: 'http://themerr.example:9494' } };
    const fetch = context.mock.method(globalThis, 'fetch', async () => {
        const response = responses.shift();
        return { ok: !response.error, status: response.error ? 502 : 200, json: async () => response.body };
    });
    context.mock.method(globalThis, 'setTimeout', () => 0);
    const controller = new AbortController();
    initServers(controller.signal);
    return { elements, buttons, fetch, reload, forms, controller, connectors, sshForms };
}

test('SSH settings submit with CSRF, clear sent credentials and enable verification', async context => {
    const { sshForms, fetch } = page(context, [{ body: {
        message: 'Saved',
        settings: { data_directory: '/canonical-plex' },
    } }], [], {}, ['plex/server']);
    const { form, check, remove, keyFields, passwordFields } = sshForms[0];
    assert.equal(keyFields.hidden, true);
    assert.equal(passwordFields.hidden, false);
    form.listeners.submit({ preventDefault() {} });
    await new Promise(setImmediate);
    assert.equal(fetch.mock.calls[0].arguments[0], '/api/plex/servers/plex%2Fserver/ssh');
    const options = fetch.mock.calls[0].arguments[1];
    assert.equal(options.method, 'PUT');
    assert.equal(options.headers['X-CSRFToken'], 'csrf-token');
    assert.equal(JSON.parse(options.body).password, 'private-password');
    assert.equal(JSON.parse(options.body).port, 22);
    assert.equal(form.elements.password.value, '');
    assert.equal(form.elements.data_directory.value, '/canonical-plex');
    assert.equal(check.disabled, false);
    assert.equal(remove.disabled, false);
});

test('SSH connection checks and disabling use the saved server without sending secrets', async context => {
    const { sshForms, fetch } = page(context, [
        { body: { message: 'Ready' } },
        { body: { message: 'Disabled' } },
    ], [], {}, ['server']);
    const { form, check, remove, status } = sshForms[0];
    form.dataset.configured = 'true';
    await check.click();
    assert.equal(fetch.mock.calls[0].arguments[0], '/api/plex/servers/server/ssh/check');
    assert.equal(fetch.mock.calls[0].arguments[1].body, undefined);
    await remove.click();
    assert.equal(fetch.mock.calls[1].arguments[1].method, 'DELETE');
    assert.equal(form.dataset.configured, 'false');
    assert.equal(form.elements.password.value, '');
    assert.equal(check.disabled, true);
    assert.equal(remove.disabled, true);
    assert.equal(status.textContent, 'Disabled');
});

test('failed SSH saves report failure and do not erase newer secret edits', async context => {
    const { sshForms } = page(context, [{
        error: true,
        body: { message: 'Fingerprint mismatch' },
    }], [], {}, ['server']);
    const { form, status } = sshForms[0];
    form.listeners.submit({ preventDefault() {} });
    form.elements.password.value = 'newer-password';
    await new Promise(setImmediate);
    assert.equal(status.textContent, 'Fingerprint mismatch');
    assert.equal(form.dataset.configured, 'false');
    assert.equal(form.elements.password.value, 'newer-password');
    form.elements.auth_type.value = 'key';
    form.elements.auth_type.listeners.change();
    assert.equal(sshForms[0].keyFields.hidden, false);
    assert.equal(sshForms[0].passwordFields.hidden, true);
});

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

test('server tabs support clicks and keyboard navigation while retaining the form and selected tab', context => {
    const { elements, controller } = page(context, [], [], { connect: true, tabs: true });
    const plex = elements['add-plex-tab'];
    const jellyfin = elements['add-jellyfin-tab'];
    const form = elements['jellyfin-server-form'];
    assert.equal(plex.getAttribute('aria-selected'), 'true');
    assert.equal(elements['add-jellyfin-panel'].hidden, true);
    jellyfin.click();
    assert.equal(elements['add-plex-panel'].hidden, true);
    assert.equal(elements['add-jellyfin-panel'].hidden, false);
    assert.equal(jellyfin.tabIndex, 0);
    assert.equal(plex.tabIndex, -1);
    const preventDefault = context.mock.fn();
    jellyfin.listeners.keydown({ key: 'ArrowRight', preventDefault });
    assert.equal(plex.focused, true);
    assert.equal(plex.getAttribute('aria-selected'), 'true');
    plex.listeners.keydown({ key: 'ArrowLeft', preventDefault });
    assert.equal(jellyfin.getAttribute('aria-selected'), 'true');
    jellyfin.listeners.keydown({ key: 'Home', preventDefault });
    plex.listeners.keydown({ key: 'End', preventDefault });
    assert.equal(preventDefault.mock.callCount(), 4);
    assert.equal(form.values.api_key, 'private-key');
    assert.equal(form.reset.mock.callCount(), 0);
    initServers(controller.signal);
    assert.equal(jellyfin.getAttribute('aria-selected'), 'true');
    plex.click();
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

test('connector suggestions preserve reverse proxy paths and use the HTTP fallback for local TLS', async context => {
    const { connectors } = page(context, [
        { body: { repository_url: 'https://trusted.example/themerr', http_port: 9495 } },
        { body: { http_port: 9495 } },
    ], [], { servers: ['jellyfin:a', 'jellyfin:b'] });
    await new Promise(setImmediate);
    assert.equal(connectors[0].form.elements.themerr_url.value, 'https://trusted.example/themerr');
    assert.equal(connectors[1].form.elements.themerr_url.value, 'http://themerr.example:9495');
});

test('Jellyfin discovery selects an address safely without transmitting credentials', async context => {
    const { elements, fetch } = page(context, [{ body: { servers: [{
        name: '<script>untrusted</script>', url: 'http://jellyfin.example:8096',
    }] } }], [], { connect: true, discover: true });
    await elements['jellyfin-discover'].click();
    const [name, address, choose] = elements['jellyfin-discovery-results'].children[0].children;
    assert.equal(name.textContent, '<script>untrusted</script>');
    assert.equal(address.textContent, 'http://jellyfin.example:8096');
    await choose.click();
    assert.equal(elements['jellyfin-server-form'].elements.url.value, address.textContent);
    assert.equal(elements['jellyfin-server-form'].elements.api_key.focused, true);
    assert.equal(fetch.mock.calls[0].arguments[0], '/api/jellyfin/discover');
    assert.equal(fetch.mock.calls[0].arguments[1].body, undefined);
});

test('empty LAN discovery explains GDM and offers account or manual connections', async context => {
    const { elements, buttons } = page(context, [{ body: { servers: [] } }]);
    await buttons[1].click();
    assert.match(elements['discovery-results'].textContent, /No Plex servers responded on LAN/);
    assert.match(elements['discovery-results'].textContent, /GDM/);
    assert.match(elements['discovery-results'].textContent, /account or manual address/);
    assert.equal(buttons[1].disabled, false);
});

test('Jellyfin discovery retains connected addresses but prevents selecting them', async context => {
    const { elements, fetch } = page(context, [{ body: { servers: [
        { id: 'one', name: 'Saved', url: 'http://127.0.0.1:8096', connected: true },
        { id: 'one', name: 'Saved', url: 'http://192.168.1.205:8096', connected: true },
        { id: 'two', name: 'Saved', url: 'http://new.example:8096', connected: false },
    ] } }], [], { connect: true, discover: true });
    await elements['jellyfin-discover'].click();
    const form = elements['jellyfin-server-form'];
    const buttons = elements['jellyfin-discovery-results'].children.map(row => row.children[2]);
    for (const button of buttons.slice(0, 2)) {
        assert.equal(button.textContent, 'Connected');
        assert.equal(button.disabled, true);
        await button.click();
        assert.equal(form.elements.url.value, '');
        assert.equal(form.elements.api_key.focused, undefined);
    }
    assert.equal(buttons[2].disabled, false);
    await buttons[2].click();
    assert.equal(form.elements.url.value, 'http://new.example:8096');
    assert.equal(form.elements.api_key.focused, true);
    assert.equal(fetch.mock.callCount(), 1);
});

for (const [index, source] of ['account', 'local'].entries()) {
    test(`Plex ${source} discovery disables connected servers while allowing new connections`, async context => {
        const connections = [{ url: 'http://plex.example:32400', local: true, relay: false }];
        const { elements, buttons, fetch } = page(context, [{ body: { servers: [
            { id: 'one', name: 'Same name', connections, connected: true },
            { id: 'two', name: 'Same name', connections, connected: false },
        ] } }, { body: { message: 'Connected' } }]);
        await buttons[index].click();
        const [saved, fresh] = elements['discovery-results'].children.map(row => row.children[2]);
        assert.equal(saved.textContent, 'Connected');
        assert.equal(saved.disabled, true);
        await saved.click();
        assert.equal(saved.disabled, true);
        assert.equal(fetch.mock.callCount(), 1);
        assert.equal(fresh.textContent, 'Connect');
        assert.equal(fresh.disabled, false);
        await fresh.click();
        const payload = JSON.parse(fetch.mock.calls[1].arguments[1].body);
        assert.equal(payload.url, 'http://plex.example:32400');
        assert.equal(payload.resource_id, source === 'account' ? 'two' : undefined);
    });
}

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

for (const [automatic, installed, hidden] of [[true, false, false], [true, true, false],
    [false, true, true], [false, false, false]]) {
    test(`connector controls honor automatic=${automatic} and installed=${installed}`, async context => {
        const { connectors } = page(context, [{ body: { auto_update: automatic, installed,
            can_restart: true, message: 'Checked' } }], [], { servers: ['jellyfin:a'] });
        await new Promise(setImmediate);
        assert.equal(connectors[0].button.hidden, hidden);
        assert.equal(connectors[0].button.textContent, automatic ? 'Save connector address' : 'Install matching connector');
        assert.equal(connectors[0].restart.disabled, false);
    });
}

test('automatic connector mode saves the address without manually installing', async context => {
    const { connectors, fetch } = page(context, [{ body: { auto_update: true } },
        { body: { message: 'Saved' } }], [], { servers: ['jellyfin:a'] });
    await new Promise(setImmediate);
    connectors[0].form.listeners.submit({ preventDefault() {} });
    await new Promise(setImmediate);
    assert.equal(fetch.mock.calls[1].arguments[1].method, 'PUT');
    assert.equal(fetch.mock.calls[1].arguments[1].headers['X-CSRFToken'], 'csrf-token');
});

test('automatic mode also saves safely before the initial status response', async context => {
    const { connectors, fetch } = page(context, [{ body: { auto_update: true } },
        { body: { message: 'Saved' } }], [], { servers: ['jellyfin:a'], automatic: true });
    connectors[0].form.listeners.submit({ preventDefault() {} });
    await new Promise(setImmediate);
    assert.equal(fetch.mock.calls[1].arguments[1].method, 'PUT');
});

test('force restart warns about playback and targets the selected server', async context => {
    const { connectors, fetch } = page(context, [{ body: { can_restart: true } },
        { body: { message: 'Restarting' } }], [], { servers: ['jellyfin:a'] });
    await new Promise(setImmediate);
    connectors[0].restart.click();
    await new Promise(setImmediate);
    assert.match(window.confirm.mock.calls[0].arguments[0], /Active playback will be interrupted/);
    assert.equal(fetch.mock.calls[1].arguments[0], '/api/jellyfin/servers/jellyfin%3Aa/restart');
    assert.equal(fetch.mock.calls[1].arguments[1].headers['X-CSRFToken'], 'csrf-token');
});

test('restart controls outside connector forms remain scoped to their own cards', async context => {
    const { connectors, fetch } = page(context, [
        { body: { can_restart: true, message: 'First server ready' } },
        { body: { can_restart: true, message: 'Second server ready' } },
        { body: { message: 'Second server restarting' } },
    ], [], { servers: [
        'jellyfin:a',
        'jellyfin:b',
    ] });
    await new Promise(setImmediate);
    connectors[1].restart.click();
    await new Promise(setImmediate);
    assert.equal(fetch.mock.calls[2].arguments[0], '/api/jellyfin/servers/jellyfin%3Ab/restart');
    assert.equal(connectors[0].status.textContent, 'First server ready');
    assert.equal(connectors[1].status.textContent, 'Second server restarting');
});

test('unsupported servers disable restart and cancellation sends no request', async context => {
    const { connectors, fetch } = page(context, [{ body: { can_restart: false } }], [], { servers: ['jellyfin:a'] });
    await new Promise(setImmediate);
    assert.equal(connectors[0].restart.disabled, true);
    assert.match(connectors[0].restart.title, /service or container/);
    window.confirm = () => false;
    connectors[0].restart.click();
    await new Promise(setImmediate);
    assert.equal(fetch.mock.callCount(), 1);
});
