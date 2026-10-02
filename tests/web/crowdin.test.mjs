import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../../docs/source/_static/js/crowdin.js', import.meta.url), 'utf8');

function fixture(address, helperAvailable = true) {
    const links = ['es-ES', 'en'].map(language => ({ dataset: { langCode: language }, href: '',
        classList: { contains: () => false } }));
    const button = { href: '', dataset: {}, classList: { contains: name => name === 'cr-picker-button' } };
    const location = { href: address, assign: value => { location.assigned = value; } };
    const handlers = new Map();
    let observed, initialize;
    const document = {
        documentElement: {}, querySelectorAll: () => links, querySelector: () => button,
        addEventListener: (event, handler, capture) => { handlers.set(event, handler); assert.equal(capture, true); },
    };
    const context = { URL, document, location, MutationObserver: class {
        constructor(callback) { observed = callback; }
        observe() {}
    } };
    if (helperAvailable) context.initCrowdIn = (...args) => { initialize = args; };
    vm.runInNewContext(source, context);
    function click(link, options = {}) {
        const event = { target: { closest: () => link }, button: 0,
            preventDefault() { this.prevented = true; },
            stopImmediatePropagation() { this.stopped = true; }, ...options };
        handlers.get('click')(event);
        return event;
    }
    return { links, button, location, click, observed, initialize };
}

test('the bundled language picker retains HTTPS, port, page, other queries and fragment', () => {
    const address = 'https://127.0.0.1:9494/docs/about/usage.html?example=1#theme-format';
    const { links, location, click, observed, initialize } = fixture(address);
    assert.deepEqual(initialize, ['LizardByte-docs', 'dockle']);
    const expected = 'https://127.0.0.1:9494/docs/about/usage.html?example=1&lng=es-ES#theme-format';
    assert.equal(links[0].href, expected);
    links[0].href = 'https://127.0.0.1/docs/?lng=es-ES';
    observed();
    assert.equal(links[0].href, expected);
    const event = click(links[0]);
    assert.equal(event.stopped, true);
    assert.equal(event.prevented, true);
    assert.equal(location.assigned, expected);
});

test('returning to English removes only the language query and supports IPv6 and HTTP ports', () => {
    const { links, click, location } = fixture('http://[::1]:9494/docs/?lng=es-ES&example=1');
    click(links[1]);
    assert.equal(location.assigned, 'http://[::1]:9494/docs/?example=1');
    assert.equal(links[1].href, location.assigned);
});

test('opening the menu preserves its toggle handler and modified clicks keep normal tab navigation', () => {
    const { links, button, click, location } = fixture('https://localhost:9494/docs/');
    const toggle = click(button);
    assert.equal(toggle.prevented, true);
    assert.equal(toggle.stopped, undefined);
    const modified = click(links[0], { ctrlKey: true });
    assert.equal(modified.stopped, true);
    assert.equal(modified.prevented, undefined);
    assert.equal(location.assigned, undefined);
    assert.equal(links[0].href, 'https://localhost:9494/docs/?lng=es-ES');
    assert.equal(click(null).prevented, undefined);
});

test('optional helper failure leaves documentation navigation usable', () => {
    const { click, links, location } = fixture('https://localhost:9494/docs/', false);
    click(links[0]);
    assert.equal(location.assigned, 'https://localhost:9494/docs/?lng=es-ES');
});
