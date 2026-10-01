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
    addEventListener(name, listener) { this.listeners[name] = listener; }
    setAttribute() {}
    removeAttribute() {}
    replaceChildren() { this.children = []; this.textContent = ''; }
    append(...elements) {
        this.children.push(...elements);
        if (this.tag === 'select' && !this.value) this.value = elements[0].value;
    }
    click() { return this.listeners.click(); }
}

function page(context, responses) {
    const previous = { document: globalThis.document, window: globalThis.window };
    context.after(() => Object.assign(globalThis, previous));
    const elements = Object.fromEntries(['plex-auth-start', 'plex-auth-status', 'plex-auth-link', 'plex-auth-disconnect',
        'discovery-results', 'manual-server-form', 'toast-region'].map(id => [id, new Element()]));
    const buttons = ['account', 'local'].map(source => Object.assign(new Element('button'), { dataset: { discover: source } }));
    globalThis.document = {
        getElementById: id => elements[id], createElement: tag => new Element(tag),
        querySelectorAll: selector => selector === '[data-discover]' ? buttons : [],
        querySelector: () => ({ content: 'csrf-token' }),
    };
    const reload = context.mock.fn();
    globalThis.window = { addEventListener() {}, location: { reload } };
    const fetch = context.mock.method(globalThis, 'fetch', async () => {
        const response = responses.shift();
        return { ok: !response.error, status: response.error ? 502 : 200, json: async () => response.body };
    });
    context.mock.method(globalThis, 'setTimeout', () => 0);
    initServers();
    return { elements, buttons, fetch, reload };
}

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
