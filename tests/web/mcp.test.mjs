import assert from 'node:assert/strict';
import test from 'node:test';
import { initMcpTokens } from '../../web/js/mcp.js';

class Element {
    isConnected = true;
    listeners = {};
    children = [];
    dataset = {};
    disabled = false;
    hidden = false;
    value = '';
    textContent = '';
    attributes = {};
    addEventListener(name, fn) { this.listeners[name] = fn; }
    setAttribute(name, value) { this.attributes[name] = value; }
    removeAttribute(name) { delete this.attributes[name]; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    contains(node) { return this.children.some(child => child === node || child.contains(node)); }
    focus() { this.focused = true; }
    select() { this.selected = true; }
    remove() {}
}

function page(t, request) {
    const ids = [
        'mcp',
        'mcp-token-form',
        'mcp-token-list',
        'mcp-token-reveal',
        'mcp-new-token',
        'mcp-endpoint',
        'mcp-copy-endpoint',
        'mcp-toggle-token',
        'mcp-show-token-icon',
        'mcp-mask-token-icon',
        'mcp-token-name',
        'mcp-token-scope',
        'mcp-create-token',
        'mcp-revoke-all',
        'mcp-copy-token',
        'mcp-hide-token',
        'toast-region',
    ];
    const elements = Object.fromEntries(ids.map(id => [
        id,
        new Element(),
    ]));
    elements['mcp-token-form'].reportValidity = () => true;
    elements['mcp-token-name'].value = 'My assistant';
    elements['mcp-token-scope'].value = 'read';
    elements['mcp-revoke-all'].disabled = true;
    elements['mcp-token-reveal'].hidden = true;
    elements['mcp-endpoint'].textContent = 'https://127.0.0.1:9494/mcp';
    elements['mcp-mask-token-icon'].hidden = true;
    elements.mcp.querySelectorAll = () => [
        elements['mcp-create-token'],
        elements['mcp-revoke-all'],
    ];
    const previous = {
        document: globalThis.document,
        window: globalThis.window,
    };
    t.after(() => Object.assign(globalThis, previous));
    const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
    const clipboard = { writeText: t.mock.fn(async () => {}) };
    Object.defineProperty(globalThis, 'navigator', {
        configurable: true,
        value: { clipboard },
    });
    t.after(() => {
        if (navigatorDescriptor) Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
        else delete globalThis.navigator;
    });
    globalThis.document = {
        getElementById: id => elements[id],
        createElement: () => new Element(),
        querySelector: () => ({ content: 'signed-csrf-token' }),
        createRange: () => ({ selectNodeContents: element => { element.selected = true; } }),
    };
    globalThis.window = {
        confirm: t.mock.fn(() => true),
        getSelection: () => ({
            removeAllRanges() {},
            addRange() {},
        }),
    };
    t.mock.method(globalThis, 'setTimeout', () => 0);
    t.mock.method(globalThis, 'fetch', request);
    const controller = new AbortController();
    initMcpTokens(controller.signal);
    return {
        elements,
        controller,
        clipboard,
        submit: () => elements['mcp-token-form'].listeners.submit({ preventDefault() {} }),
    };
}

const tokenMetadata = {
    id: 'management-id',
    name: '<script>client</script>',
    scope: 'read',
    created: '2026-10-09T12:00:00Z',
    active: true,
};

function response(data) {
    return {
        ok: true,
        status: 200,
        json: async () => data,
    };
}

test('token creation uses browser CSRF and displays a one-time credential with safe labels', async t => {
    let submitted;
    const view = page(t, async (path, options) => {
        submitted = {
            path,
            options,
        };
        return response({
            token: 'tmcp_new',
            tokens: [tokenMetadata],
        });
    });
    await view.submit();
    assert.equal(submitted.path, '/api/mcp/tokens');
    assert.equal(submitted.options.headers['X-CSRFToken'], 'signed-csrf-token');
    assert.deepEqual(JSON.parse(submitted.options.body), {
        name: 'My assistant',
        scope: 'read',
    });
    assert.equal(view.elements['mcp-new-token'].textContent, '•'.repeat(32));
    assert.equal(view.elements['mcp-toggle-token'].attributes['aria-pressed'], 'false');
    assert.equal(view.elements['mcp-toggle-token'].attributes['aria-label'], 'Show token');
    assert.equal(view.elements['mcp-token-reveal'].hidden, false);
    assert.equal(view.elements['mcp-revoke-all'].disabled, false);
    assert.equal(view.elements['mcp-token-list'].children[0].children[0].children[0].textContent, tokenMetadata.name);
    view.elements['mcp-hide-token'].listeners.click();
    assert.equal(view.elements['mcp-new-token'].textContent, '');
    assert.equal(view.elements['mcp-token-reveal'].hidden, true);
});

test('revoking one client clears the revealed credential and updates the list', async t => {
    const requests = [];
    const view = page(t, async (path, options) => {
        requests.push({
            path,
            method: options.method,
        });
        return response(requests.length === 1
            ? {
                token: 'tmcp_new',
                tokens: [tokenMetadata],
            }
            : {
                tokens: [],
                message: 'MCP token revoked.',
            });
    });
    await view.submit();
    const button = view.elements['mcp-token-list'].children[0].children[1];
    button.closest = () => button;
    await view.elements['mcp-token-list'].listeners.click({ target: button });
    assert.deepEqual(requests[1], {
        path: '/api/mcp/tokens/management-id',
        method: 'DELETE',
    });
    assert.equal(view.elements['mcp-new-token'].textContent, '');
    assert.equal(view.elements['mcp-revoke-all'].disabled, true);
});

test('revoke-all requires the selected confirmation and sends a DELETE', async t => {
    const request = t.mock.fn(async () => response({
        tokens: [],
        message: 'All MCP tokens revoked.',
    }));
    const view = page(t, request);
    globalThis.window.confirm = () => false;
    await view.elements['mcp-revoke-all'].listeners.click();
    assert.equal(request.mock.callCount(), 0);
    globalThis.window.confirm = () => true;
    await view.elements['mcp-revoke-all'].listeners.click();
    assert.equal(request.mock.calls[0].arguments[1].method, 'DELETE');
    assert.equal(view.elements['mcp-revoke-all'].disabled, true);
});

test('pending requests prevent duplicate token creation and detached pages never reveal tokens', async t => {
    let finish;
    const request = t.mock.fn(() => new Promise(resolve => { finish = resolve; }));
    const view = page(t, request);
    const pending = view.submit();
    await view.submit();
    assert.equal(request.mock.callCount(), 1);
    assert.equal(view.elements['mcp-create-token'].disabled, true);
    view.controller.abort();
    finish(response({
        token: 'tmcp_new',
        tokens: [tokenMetadata],
    }));
    await pending;
    assert.equal(view.elements['mcp-new-token'].textContent, '');
    assert.equal(view.elements['mcp-token-reveal'].hidden, true);
    assert.equal(view.elements['mcp-create-token'].disabled, false);
});

test('request failures leave the form usable and do not reveal a credential', async t => {
    const view = page(t, async () => ({
        ok: false,
        status: 400,
        json: async () => ({ message: 'Invalid scope.' }),
    }));
    await view.submit();
    assert.equal(view.elements['mcp-create-token'].disabled, false);
    assert.equal(view.elements['mcp-token-reveal'].hidden, true);
    assert.equal(view.elements['toast-region'].children[0].children[0].textContent, 'Invalid scope.');
});

test('copying the endpoint uses its displayed URL and offers manual selection on failure', async t => {
    const view = page(t, async () => response({ tokens: [] }));
    await view.elements['mcp-copy-endpoint'].listeners.click();
    assert.equal(view.clipboard.writeText.mock.calls[0].arguments[0], 'https://127.0.0.1:9494/mcp');
    view.clipboard.writeText = async () => { throw new Error('Clipboard unavailable'); };
    await view.elements['mcp-copy-endpoint'].listeners.click();
    assert.equal(view.elements['mcp-endpoint'].selected, true);
    assert.equal(view.elements['mcp-endpoint'].focused, true);
});

test('copying a masked token copies the credential and visibility controls reset after creation and disposal', async t => {
    const view = page(t, async () => response({
        token: 'tmcp_new',
        tokens: [tokenMetadata],
    }));
    await view.submit();
    await view.elements['mcp-copy-token'].listeners.click();
    assert.equal(view.clipboard.writeText.mock.calls[0].arguments[0], 'tmcp_new');
    assert.equal(view.elements['mcp-new-token'].textContent, '•'.repeat(32));
    const toggle = view.elements['mcp-toggle-token'];
    toggle.listeners.click();
    assert.equal(view.elements['mcp-new-token'].textContent, 'tmcp_new');
    assert.equal(toggle.attributes['aria-label'], 'Mask token');
    assert.equal(toggle.attributes['aria-pressed'], 'true');
    assert.equal(view.elements['mcp-show-token-icon'].hidden, true);
    assert.equal(view.elements['mcp-mask-token-icon'].hidden, false);
    toggle.listeners.click();
    assert.equal(view.elements['mcp-new-token'].textContent, '•'.repeat(32));
    assert.equal(toggle.attributes['aria-pressed'], 'false');
    toggle.listeners.click();
    await view.submit();
    assert.equal(view.elements['mcp-new-token'].textContent, '•'.repeat(32));
    assert.equal(toggle.attributes['aria-pressed'], 'false');
    toggle.listeners.click();
    view.controller.abort();
    assert.equal(view.elements['mcp-new-token'].textContent, '');
    assert.equal(toggle.attributes['aria-pressed'], 'false');
    toggle.listeners.click();
    await view.elements['mcp-copy-token'].listeners.click();
    assert.equal(view.elements['mcp-new-token'].textContent, '');
    assert.equal(view.clipboard.writeText.mock.callCount(), 1);
});

test('a failed clipboard operation preserves masking until the user chooses to show the token', async t => {
    const view = page(t, async () => response({
        token: 'tmcp_new',
        tokens: [tokenMetadata],
    }));
    await view.submit();
    view.clipboard.writeText = async () => { throw new Error('Clipboard unavailable'); };
    await view.elements['mcp-copy-token'].listeners.click();
    assert.equal(view.elements['mcp-new-token'].textContent, '•'.repeat(32));
    assert.equal(view.elements['mcp-toggle-token'].focused, true);
    assert.equal(view.elements['mcp-new-token'].selected, undefined);
    view.elements['mcp-toggle-token'].listeners.click();
    await view.elements['mcp-copy-token'].listeners.click();
    assert.equal(view.elements['mcp-new-token'].textContent, 'tmcp_new');
    assert.equal(view.elements['mcp-new-token'].selected, true);
});

test('a clipboard failure after Done cannot prompt the user to reveal a cleared token', async t => {
    const view = page(t, async () => response({
        token: 'tmcp_new',
        tokens: [tokenMetadata],
    }));
    await view.submit();
    const toastCount = view.elements['toast-region'].children.length;
    let fail;
    view.clipboard.writeText = () => new Promise((resolve, reject) => { fail = reject; });
    const copying = view.elements['mcp-copy-token'].listeners.click();
    view.elements['mcp-hide-token'].listeners.click();
    fail(new Error('Clipboard unavailable'));
    await copying;
    assert.equal(view.elements['mcp-new-token'].textContent, '');
    assert.equal(view.elements['mcp-token-reveal'].hidden, true);
    assert.equal(view.elements['toast-region'].children.length, toastCount);
});
