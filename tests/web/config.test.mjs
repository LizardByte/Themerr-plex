import assert from 'node:assert/strict';
import test from 'node:test';
import { initSettings } from '../../web/js/config.js';
import { initTranslations, _ } from '../../web/js/i18n.js';

class Element {
    listeners = {};
    value = '';
    disabled = false;
    children = [];
    addEventListener(name, fn) { this.listeners[name] = fn; }
    setAttribute() {}
    removeAttribute() {}
    append(...children) { this.children.push(...children); }
}

function settings(t, request) {
    const ids = ['configForm', 'save-button', 'settings-save-status', 'LOCALE', 'password-form', 'toast-region'];
    const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
    const locale = elements.LOCALE;
    locale.value = 'en';
    locale.id = 'LOCALE';
    locale.getAttribute = () => 'General';
    const form = elements.configForm;
    form.reportValidity = () => true;
    form.querySelectorAll = () => [locale];
    const previous = { document: globalThis.document, window: globalThis.window,
        IntersectionObserver: globalThis.IntersectionObserver };
    t.after(() => Object.assign(globalThis, previous));
    globalThis.document = { getElementById: id => elements[id], createElement: () => new Element(),
        querySelector: () => ({ content: 'token' }), querySelectorAll: () => [] };
    const reload = t.mock.fn();
    globalThis.window = { addEventListener() {}, location: { reload } };
    globalThis.IntersectionObserver = class { observe() {} };
    t.mock.method(globalThis, 'setTimeout', () => 0);
    t.mock.method(globalThis, 'fetch', request);
    initSettings();
    const change = value => { locale.value = value; form.listeners.change(); };
    const save = () => form.listeners.submit({ preventDefault() {} });
    return { change, save, reload, elements };
}

test('a saved locale change reloads immediately', async t => {
    const page = settings(t, async () => ({ ok: true, status: 200, json: async () => ({}) }));
    page.change('fr');
    await page.save();
    assert.equal(page.reload.mock.callCount(), 1);
    assert.equal(page.elements['save-button'].disabled, true);
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
