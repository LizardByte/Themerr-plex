import assert from 'node:assert/strict';
import test from 'node:test';
import { initColorTheme } from '../../web/js/color_theme.js';

const storageKey = 'themerr-color-theme';

function fixture({ saved = null, dark = false, loading = false, blocked = false } = {}) {
    const browser = new EventTarget();
    const systemTheme = new EventTarget();
    systemTheme.matches = dark;
    browser.matchMedia = query => {
        assert.equal(query, '(prefers-color-scheme: dark)');
        return systemTheme;
    };
    const storage = new Map(saved === null ? [] : [[storageKey, saved]]);
    Object.defineProperty(browser, 'localStorage', { get() {
        if (blocked) throw new Error('Storage disabled');
        return { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
    } });
    const button = new EventTarget();
    button.dataset = { autoLabel: 'Automatic; switch to light', lightLabel: 'Light; switch to dark',
        darkLabel: 'Dark; switch to automatic' };
    button.setAttribute = (name, value) => { button[name] = value; };
    const icons = ['auto', 'light', 'dark'].map(themeIcon => ({ dataset: { themeIcon }, hidden: false }));
    button.querySelectorAll = () => icons;
    const classes = new Set();
    const root = new EventTarget();
    root.readyState = loading ? 'loading' : 'complete';
    root.documentElement = { dataset: {}, classList: { toggle(name, active) {
        if (active) classes.add(name);
        else classes.delete(name);
    } } };
    const meta = { setAttribute(name, value) { this[name] = value; } };
    root.querySelector = () => meta;
    root.querySelectorAll = () => root.readyState === 'loading' ? [] : [button];
    initColorTheme(root, browser);
    return {
        root, browser, button, storage, meta, classes,
        get theme() { return root.documentElement.dataset.bsTheme; },
        get mode() { return root.documentElement.dataset.themeMode; },
        get visibleIcons() { return icons.filter(icon => !icon.hidden).map(icon => icon.dataset.themeIcon); },
        click() { button.dispatchEvent(new Event('click')); },
        system(dark) { systemTheme.matches = dark; systemTheme.dispatchEvent(new Event('change')); },
        stored(value, key = storageKey) {
            const event = new Event('storage');
            Object.assign(event, { key, newValue: value });
            browser.dispatchEvent(event);
        },
    };
}

test('automatic mode follows the system before controls exist and responds to system changes', () => {
    const page = fixture({ dark: true, loading: true });
    assert.equal(page.theme, 'dark');
    assert.equal(page.mode, 'auto');
    assert.equal(page.meta.content, 'dark');
    assert.ok(page.classes.has('dark-mode'));
    page.root.readyState = 'interactive';
    page.root.dispatchEvent(new Event('DOMContentLoaded'));
    assert.deepEqual(page.visibleIcons, ['auto']);
    assert.equal(page.button['aria-label'], page.button.dataset.autoLabel);
    page.system(false);
    assert.equal(page.theme, 'light');
    assert.equal(page.meta.content, 'light');
    assert.ok(!page.classes.has('dark-mode'));
    assert.deepEqual(page.visibleIcons, ['auto']);
    assert.equal(page.storage.size, 0);
});

test('clicks cycle automatic, light, and dark with saved preferences and accessible icon labels', () => {
    const page = fixture();
    page.click();
    assert.equal(page.mode, 'light');
    assert.equal(page.storage.get(storageKey), 'light');
    assert.deepEqual(page.visibleIcons, ['light']);
    assert.equal(page.button['aria-label'], page.button.dataset.lightLabel);
    const reloaded = fixture({ saved: page.storage.get(storageKey), dark: true });
    assert.equal(reloaded.theme, 'light');
    assert.deepEqual(reloaded.visibleIcons, ['light']);
    page.system(true);
    assert.equal(page.theme, 'light');
    page.click();
    assert.equal(page.mode, 'dark');
    assert.equal(page.storage.get(storageKey), 'dark');
    assert.deepEqual(page.visibleIcons, ['dark']);
    assert.equal(page.button['aria-label'], page.button.dataset.darkLabel);
    page.system(false);
    assert.equal(page.theme, 'dark');
    page.click();
    assert.equal(page.mode, 'auto');
    assert.equal(page.theme, 'light');
    assert.equal(page.storage.get(storageKey), 'auto');
    assert.deepEqual(page.visibleIcons, ['auto']);
    page.system(true);
    assert.equal(page.theme, 'dark');
});

test('changes in other tabs update the icon, accessible label, and Swagger palette', () => {
    const page = fixture({ saved: 'light', dark: true });
    assert.equal(page.theme, 'light');
    assert.deepEqual(page.visibleIcons, ['light']);
    page.stored('dark', 'unrelated');
    assert.equal(page.theme, 'light');
    page.stored('dark');
    assert.equal(page.theme, 'dark');
    assert.deepEqual(page.visibleIcons, ['dark']);
    assert.equal(page.button['aria-label'], page.button.dataset.darkLabel);
    assert.ok(page.classes.has('dark-mode'));
    page.stored(null);
    assert.equal(page.mode, 'auto');
    page.stored('light');
    page.stored(null, null);
    assert.deepEqual(page.visibleIcons, ['auto']);
    assert.equal(page.theme, 'dark');
});

test('invalid preferences fall back to automatic and unavailable storage does not disable switching', () => {
    const invalid = fixture({ saved: 'invalid', dark: true });
    assert.equal(invalid.mode, 'auto');
    assert.equal(invalid.theme, 'dark');
    invalid.stored('invalid');
    assert.deepEqual(invalid.visibleIcons, ['auto']);
    const page = fixture({ blocked: true });
    assert.equal(page.theme, 'light');
    page.click();
    page.click();
    assert.equal(page.theme, 'dark');
    page.system(false);
    assert.equal(page.theme, 'dark');
    page.click();
    assert.equal(page.theme, 'light');
});
