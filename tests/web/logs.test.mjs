import assert from 'node:assert/strict';
import test from 'node:test';
import { attentionTarget, filterLogs, formatLogs, highlightMessage, initLogs } from '../../web/js/logs.js';

const entries = [
    { id: 'a', source: 'themerr', timestamp: '2026-10-03 10:00:00', level: 'INFO', thread: 'MainThread', message: 'Léon ready' },
    { id: 'b', source: 'yt-dlp', timestamp: '2026-10-03 10:01:00', level: 'WARNING', thread: 'Worker', message: 'Retry extraction' },
    { id: 'c', source: 'backend', timestamp: '2026-10-03 10:02:00', level: 'ERROR', thread: 'Web', message: 'Request failed\nTraceback:\n  <script>bad()</script>' },
    { id: 'd', source: 'themerr', timestamp: '2026-10-03 10:03:00', level: 'CRITICAL', thread: 'MainThread', message: 'Stopped' },
];

test('search and source/severity filters combine and include multiline and Unicode messages', () => {
    assert.deepEqual(filterLogs(entries, { search: ' LÉON ' }), [entries[0]]);
    assert.deepEqual(filterLogs(entries, { search: 'traceback', source: 'backend', level: 'attention' }), [entries[2]]);
    assert.deepEqual(filterLogs(entries, { search: 'worker', level: 'WARNING' }), [entries[1]]);
    assert.deepEqual(filterLogs(entries, { search: '10:03', source: 'themerr' }), [entries[3]]);
    assert.deepEqual(filterLogs(entries, { source: 'themerr', level: 'ERROR' }), []);
    assert.deepEqual(filterLogs(entries, { level: 'attention' }), entries.slice(1));
});

test('navigation wraps through only visible warnings, errors, and critical errors', () => {
    assert.equal(attentionTarget(entries, null, 1), 'b');
    assert.equal(attentionTarget(entries, null, -1), 'd');
    assert.equal(attentionTarget(entries, 'b', 1), 'c');
    assert.equal(attentionTarget(entries, 'b', -1), 'd');
    assert.equal(attentionTarget(entries, 'd', 1), 'b');
    assert.equal(attentionTarget([entries[0]], null, 1), null);
    assert.equal(attentionTarget([entries[2]], 'c', 1), 'c');
});

class Element extends EventTarget {
    constructor(ownerDocument, tag = 'div') {
        super();
        this.ownerDocument = ownerDocument;
        this.tag = tag;
        this.children = [];
        this.attributes = new Map();
        this.value = '';
        this.checked = false;
        this.hidden = false;
        this.disabled = false;
        this.scrollTop = 0;
        this.scrollHeight = 100;
        this.classList = {
            add: value => { this.className += ` ${value}`; },
            remove: value => { this.className = (this.className || '').replace(` ${value}`, ''); },
        };
    }
    set textContent(value) { this.content = value; this.children = []; }
    get textContent() { return this.content || this.children.map(child => child.textContent).join(''); }
    append(...children) { this.children.push(...children.flatMap(child => child.tag === 'fragment' ? child.children : [child])); }
    replaceChildren(...children) { this.content = ''; this.children = []; this.append(...children); }
    setAttribute(name, value) { this.attributes.set(name, value); }
    removeAttribute(name) { this.attributes.delete(name); }
    focus() { this.focused = true; }
    scrollIntoView() { this.scrolled = true; }
    click() { this.dispatchEvent(new Event('click')); }
    remove() { this.removed = true; }
}

function setup() {
    const root = {
        createElement: tag => new Element(root, tag),
        createDocumentFragment: () => new Element(root, 'fragment'),
        createTextNode: text => ({ tag: 'text', textContent: text }),
        querySelector: selector => fields[selector.slice(5)],
    };
    const fields = Object.fromEntries(['viewer', 'list', 'viewport', 'search', 'source', 'level', 'live', 'follow',
        'limit', 'refresh', 'status', 'error', 'empty', 'history', 'attention-count', 'previous', 'next', 'download',
        'clear-search', 'clear-filters', 'pages', 'page-info', 'older', 'newer'].map(name => [name, new Element(root)]));
    root.body = new Element(root, 'body');
    fields.source.value = fields.level.value = 'all';
    fields.limit.value = '1000';
    fields.live.checked = fields.follow.checked = true;
    const host = new EventTarget();
    host.timers = new Map();
    let id = 0;
    host.setTimeout = callback => { host.timers.set(++id, callback); return id; };
    host.clearTimeout = timer => host.timers.delete(timer);
    return { root, fields, host };
}

const settle = () => new Promise(resolve => setImmediate(resolve));
const result = data => ({ entries: data, unavailable: [], truncated: false });

test('highlights literal search text without treating log messages as HTML', () => {
    const { root } = setup();
    const element = root.createElement('pre');
    highlightMessage(element, '<script>Bad()</script> BAD', 'bad');
    assert.equal(element.textContent, '<script>Bad()</script> BAD');
    assert.deepEqual(element.children.filter(child => child.tag === 'mark').map(child => child.textContent), ['Bad', 'BAD']);
    assert.equal(element.children.some(child => child.tag === 'script'), false);
    assert.ok(formatLogs([entries[2]]).includes('Traceback:\n  <script>bad()</script>'));
});

test('viewer searches, clears filters, navigates, pauses, and preserves scroll during refresh', async () => {
    const { root, fields, host } = setup();
    let data = entries;
    initLogs(root, async () => result(data), host);
    await settle();
    assert.equal(fields.list.children.length, 4);
    assert.equal(fields.viewport.scrollTop, 100);
    assert.equal(fields['attention-count'].textContent, '3 warnings and errors');
    fields.next.click();
    assert.equal(fields.follow.checked, false);
    assert.equal(fields.list.children[1].focused, true);
    fields.next.click();
    assert.equal(fields.list.children[2].scrolled, true);
    fields.search.value = 'traceback';
    fields.search.dispatchEvent(new Event('input'));
    assert.equal(fields.list.children.length, 1);
    assert.equal(fields['clear-search'].hidden, false);
    fields['clear-search'].click();
    assert.equal(fields.list.children.length, 4);
    assert.equal(fields.search.focused, true);
    fields.level.value = 'WARNING';
    fields.level.dispatchEvent(new Event('change'));
    assert.equal(fields.list.children.length, 1);
    fields['clear-filters'].click();
    await settle();
    assert.equal(fields.list.children.length, 4);
    fields.viewport.scrollTop = 24;
    data = [...entries, { ...entries[0], id: 'new', message: 'new message' }];
    fields.refresh.click();
    await settle();
    assert.equal(fields.list.children.length, 5);
    assert.equal(fields.viewport.scrollTop, 24);
    fields.live.checked = false;
    fields.live.dispatchEvent(new Event('change'));
    assert.equal(host.timers.size, 0);
    assert.ok(fields.status.textContent.includes('Paused'));
    fields.live.checked = true;
    fields.live.dispatchEvent(new Event('change'));
    await settle();
    assert.equal(host.timers.size, 1);
    host.dispatchEvent(new Event('pagehide'));
    assert.equal(host.timers.size, 0);
});

test('refresh failures retain useful records and a later success clears the error', async () => {
    const { root, fields, host } = setup();
    let failure = false;
    initLogs(root, async () => { if (failure) throw new Error('Connection failed'); return result(entries); }, host);
    await settle();
    failure = true;
    fields.refresh.click();
    await settle();
    assert.equal(fields.error.hidden, false);
    assert.equal(fields.error.textContent, 'Connection failed');
    assert.equal(fields.list.children.length, 4);
    failure = false;
    fields.refresh.click();
    await settle();
    assert.equal(fields.error.hidden, true);
    assert.equal(fields.refresh.disabled, false);
    assert.equal(host.timers.size, 1);
});

test('source changes during a pending refresh discard its response and load the new source', async () => {
    const { root, fields, host } = setup();
    const pending = [];
    const paths = [];
    initLogs(root, path => { paths.push(path); return new Promise(resolve => pending.push(resolve)); }, host);
    fields.source.value = 'backend';
    fields.source.dispatchEvent(new Event('change'));
    pending.shift()(result(entries));
    await settle();
    assert.equal(fields.list.children.length, 0);
    assert.equal(paths.length, 2);
    assert.ok(paths[1].includes('source=backend'));
    pending.shift()(result([entries[2]]));
    await settle();
    assert.equal(fields.list.children.length, 1);
    assert.equal(fields.error.hidden, true);
});

test('download contains only the filtered records and releases its object URL', async () => {
    const { root, fields, host } = setup();
    let blob;
    let revoked;
    host.URL = {
        createObjectURL: value => { blob = value; return 'blob:download'; },
        revokeObjectURL: value => { revoked = value; },
    };
    initLogs(root, async () => result(entries), host);
    await settle();
    fields.source.value = 'backend';
    fields.source.dispatchEvent(new Event('change'));
    await settle();
    fields.download.click();
    assert.equal(await blob.text(), formatLogs([entries[2]]));
    const link = root.body.children[0];
    assert.equal(link.download, 'themerr-logs.txt');
    assert.equal(link.removed, true);
    [...host.timers.values()].at(-1)();
    assert.equal(revoked, 'blob:download');
});

test('since-startup history loads all batches, polls incrementally, and navigates across pages', async () => {
    const { root, fields, host } = setup();
    fields.limit.value = 'startup';
    const history = Array.from({ length: 2105 }, (_, index) => ({
        ...entries[0], id: `startup:${index}`, message: `Session message ${index}`,
        level: [0, 1600].includes(index) ? 'ERROR' : 'INFO',
    }));
    const paths = [];
    const request = async path => {
        paths.push(path);
        const cursor = Number(new URL(path, 'http://localhost').searchParams.get('cursor'));
        const batch = history.slice(cursor, cursor + 1000);
        return { ...result(batch), cursor: cursor + batch.length, has_more: cursor + batch.length < history.length };
    };
    initLogs(root, request, host);
    await settle();
    assert.equal(paths.length, 3);
    assert.equal(fields.list.children.length, 105);
    assert.equal(fields['page-info'].textContent, '5 / 5');
    assert.equal(fields['attention-count'].textContent, '2 warnings and errors');
    assert.ok(fields.status.textContent.startsWith('2105 / 2105'));
    fields.next.click();
    assert.equal(fields['page-info'].textContent, '1 / 5');
    assert.equal(fields.list.children[0].focused, true);
    fields.next.click();
    assert.equal(fields['page-info'].textContent, '4 / 5');
    assert.equal(fields.list.children[100].focused, true);
    fields.older.click();
    assert.equal(fields['page-info'].textContent, '3 / 5');
    fields.newer.click();
    assert.equal(fields['page-info'].textContent, '4 / 5');
    fields.follow.checked = true;
    fields.follow.dispatchEvent(new Event('change'));
    assert.equal(fields['page-info'].textContent, '5 / 5');
    assert.equal(fields.list.children.length, 105);
    fields.follow.checked = false;
    fields.follow.dispatchEvent(new Event('change'));
    history.push({ ...entries[0], id: 'startup:2105', message: 'Appended after initial load' });
    fields.refresh.click();
    await settle();
    assert.ok(paths.at(-1).endsWith('cursor=2105'));
    assert.ok(fields.status.textContent.startsWith('2106 / 2106'));
    fields.search.value = 'Session message 0';
    fields.search.dispatchEvent(new Event('input'));
    assert.equal(fields.list.children.length, 1);
    assert.equal(fields.pages.hidden, true);
    assert.equal(fields.list.children[0].textContent.includes('Session message 0'), true);
    fields.limit.value = '1000';
    fields.limit.dispatchEvent(new Event('change'));
    await settle();
    fields.limit.value = 'startup';
    fields.limit.dispatchEvent(new Event('change'));
    await settle();
    assert.ok(paths.slice(-3)[0].endsWith('cursor=0'));
    assert.ok(fields.status.textContent.includes('/ 2106 records'));
    assert.equal(host.timers.size, 1);
});

test('a stalled startup cursor reports an error and does not start a tight request loop', async () => {
    const { root, fields, host } = setup();
    fields.limit.value = 'startup';
    let calls = 0;
    initLogs(root, async () => { calls += 1; return { ...result(entries), cursor: 0, has_more: true }; }, host);
    await settle();
    assert.equal(calls, 1);
    assert.equal(fields.error.hidden, false);
    assert.equal(host.timers.size, 1);
});
