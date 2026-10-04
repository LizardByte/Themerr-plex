import { api } from './api.js';
import { _ } from './i18n.js';

export function needsAttention(entry) {
    return ['WARNING', 'ERROR', 'CRITICAL'].includes(entry.level);
}

export function filterLogs(entries, { search = '', source = 'all', level = 'all' } = {}) {
    const needle = search.trim().toLocaleLowerCase();
    return entries.filter(entry => (source === 'all' || source === entry.source)
        && (level === 'all' || (level === 'attention' ? needsAttention(entry) : entry.level === level))
        && (!needle || [entry.message, entry.thread, entry.timestamp, entry.source, entry.level]
            .some(value => value.toLocaleLowerCase().includes(needle))));
}

export function attentionTarget(entries, currentId, direction) {
    const current = entries.findIndex(entry => entry.id === currentId);
    const candidates = entries.map((entry, index) => needsAttention(entry) ? index : -1).filter(index => index >= 0);
    if (!candidates.length) return null;
    const index = direction > 0
        ? (candidates.find(index => index > current) ?? candidates[0])
        : (candidates.findLast(index => index < current) ?? candidates.at(-1));
    return entries[index].id;
}

export function formatLogs(entries) {
    return entries.map(entry => `${entry.timestamp} - ${entry.level} [${entry.source}] ${entry.thread} : ${entry.message}`)
        .join('\n') + (entries.length ? '\n' : '');
}

// Keep log content as text, including HTML-like strings and search highlights.
export function highlightMessage(element, message, search) {
    const needle = search.trim().toLocaleLowerCase();
    if (!needle) { element.textContent = message; return; }
    const lower = message.toLocaleLowerCase();
    let start = 0;
    let match = lower.indexOf(needle);
    while (match >= 0) {
        element.append(element.ownerDocument.createTextNode(message.slice(start, match)));
        const mark = element.ownerDocument.createElement('mark');
        mark.textContent = message.slice(match, match + needle.length);
        element.append(mark);
        start = match + needle.length;
        match = lower.indexOf(needle, start);
    }
    element.append(element.ownerDocument.createTextNode(message.slice(start)));
}

export function initLogs(root = document, request = api, host = window, signal) {
    const viewer = root.querySelector('#log-viewer');
    if (!viewer) return;
    const field = name => root.querySelector(`#log-${name}`);
    const list = field('list');
    const viewport = field('viewport');
    const search = field('search');
    const source = field('source');
    const level = field('level');
    const live = field('live');
    const follow = field('follow');
    const limit = field('limit');
    let entries = [];
    let visible = [];
    let selected = null;
    let timer;
    let active = true;
    let loading = false;
    let reload = false;
    let snapshot = '';
    let metadata = '';
    let loadedSelection = '';
    let cursor = 0;
    let page = 0;
    const rows = new Map();

    function select(id) {
        rows.get(selected)?.classList.remove('selected');
        selected = id;
        rows.get(id)?.classList.add('selected');
    }

    function render() {
        const scrollTop = viewport.scrollTop;
        visible = filterLogs(entries, { search: search.value, source: source.value, level: level.value });
        const pageSize = limit.value === 'startup' ? 500 : 2000;
        const pages = Math.max(1, Math.ceil(visible.length / pageSize));
        page = follow.checked ? pages - 1 : Math.min(page, pages - 1);
        field('pages').hidden = pages === 1;
        field('page-info').textContent = `${page + 1} / ${pages}`;
        field('older').disabled = page === 0;
        field('newer').disabled = page === pages - 1;
        rows.clear();
        const fragment = root.createDocumentFragment();
        for (const entry of visible.slice(page * pageSize, (page + 1) * pageSize)) {
            const row = root.createElement('article');
            row.className = `log-entry log-${entry.level.toLowerCase()}`;
            row.tabIndex = -1;
            const header = root.createElement('div');
            header.className = 'log-entry-meta';
            for (const [className, value] of [['log-time', entry.timestamp], ['log-severity', entry.level],
                ['log-channel', entry.source], ['log-thread', entry.thread]]) {
                const text = root.createElement('span');
                text.className = className;
                text.textContent = value;
                header.append(text);
            }
            const message = root.createElement('pre');
            highlightMessage(message, entry.message, search.value);
            row.append(header, message);
            row.addEventListener('click', () => select(entry.id));
            if (entry.id === selected) row.classList.add('selected');
            rows.set(entry.id, row);
            fragment.append(row);
        }
        if (!rows.has(selected)) selected = null;
        list.replaceChildren(fragment);
        field('empty').hidden = visible.length > 0;
        field('empty').textContent = entries.length ? _('No records match your filters.') : _('No log records yet.');
        field('status').textContent = `${visible.length} / ${entries.length} ${_('records')} · ${metadata}`;
        const count = visible.filter(needsAttention).length;
        field('attention-count').textContent = `${count} ${_('warnings and errors')}`;
        field('previous').disabled = field('next').disabled = count === 0;
        field('download').disabled = visible.length === 0;
        field('clear-search').hidden = !search.value;
        field('history').textContent = limit.value === 'startup'
            ? _('Search, filters, warning navigation, and download cover all loaded records since startup.')
            : _('Filters and search apply to the loaded records. Older history remains in the log directory.');
        viewport.scrollTop = follow.checked ? viewport.scrollHeight : scrollTop;
    }

    function schedule() {
        host.clearTimeout(timer);
        if (active && live.checked) timer = host.setTimeout(update, 3000);
    }

    function updateHistory(result, session, fresh, requestedCursor) {
        if (!session) {
            const next = JSON.stringify(result.entries);
            const changed = fresh || next !== snapshot;
            snapshot = next;
            entries = result.entries;
            cursor = 0;
            return changed;
        }
        if (result.has_more && result.cursor <= requestedCursor) throw new Error(_('Session log loading stalled.'));
        if (fresh) { entries = []; page = 0; }
        entries.push(...result.entries);
        cursor = result.cursor;
        if (result.has_more) reload = true;
        return fresh || result.entries.length > 0;
    }

    function showResult(result, session, changed) {
        metadata = live.checked ? _('Live') : _('Paused');
        if (session) metadata += ` · ${_('Since startup')}`;
        if (session && result.has_more) metadata += ` · ${_('Loading history…')}`;
        if (result.truncated) metadata += ` · ${_('Showing recent history')}`;
        field('error').hidden = !result.unavailable.length;
        field('error').textContent = result.unavailable.length
            ? `${_('Unable to read log sources:')} ${result.unavailable.join(', ')}` : '';
        if (changed) render();
        else field('status').textContent = `${visible.length} / ${entries.length} ${_('records')} · ${metadata}`;
    }

    async function update() {
        if (loading) { reload = true; return; }
        loading = true;
        const requested = `${source.value}:${limit.value}`;
        const session = limit.value === 'startup';
        const fresh = requested !== loadedSelection;
        const requestedCursor = fresh ? 0 : cursor;
        field('refresh').disabled = true;
        viewer.setAttribute('aria-busy', 'true');
        host.clearTimeout(timer);
        try {
            const query = session ? `scope=startup&limit=1000&cursor=${requestedCursor}` : `limit=${limit.value}`;
            const result = await request(`/api/logs?source=${encodeURIComponent(source.value)}&${query}`, { method: 'GET' });
            if (!active || requested !== `${source.value}:${limit.value}`) return;
            const changed = updateHistory(result, session, fresh, requestedCursor);
            loadedSelection = requested;
            showResult(result, session, changed);
        } catch (error) {
            if (active) {
                field('error').hidden = false;
                field('error').textContent = error.message;
                field('status').textContent = _('Refresh failed. Showing the last loaded records.');
            }
        } finally {
            loading = false;
            field('refresh').disabled = false;
            viewer.removeAttribute('aria-busy');
            if (active && reload) { reload = false; void update(); }
            else schedule();
        }
    }

    search.addEventListener('input', () => { page = 0; render(); });
    level.addEventListener('change', () => { page = 0; render(); });
    source.addEventListener('change', () => { page = 0; render(); void update(); });
    limit.addEventListener('change', () => { void update(); });
    field('clear-search').addEventListener('click', () => { search.value = ''; render(); search.focus(); });
    field('clear-filters').addEventListener('click', () => {
        search.value = ''; source.value = level.value = 'all'; render(); search.focus(); void update();
    });
    field('refresh').addEventListener('click', () => { void update(); });
    live.addEventListener('change', () => {
        metadata = live.checked ? _('Live') : _('Paused');
        if (limit.value === 'startup') metadata += ` · ${_('Since startup')}`;
        if (live.checked) void update();
        else { host.clearTimeout(timer); render(); }
    });
    follow.addEventListener('change', render);
    for (const [name, direction] of [['previous', -1], ['next', 1]]) {
        field(name).addEventListener('click', () => {
            const target = attentionTarget(visible, selected, direction);
            if (target === null) return;
            follow.checked = false;
            const pageSize = limit.value === 'startup' ? 500 : 2000;
            page = Math.floor(visible.findIndex(entry => entry.id === target) / pageSize);
            render();
            select(target);
            rows.get(target).focus({ preventScroll: true });
            rows.get(target).scrollIntoView({ block: 'nearest' });
        });
    }
    for (const [name, direction] of [['older', -1], ['newer', 1]]) {
        field(name).addEventListener('click', () => {
            follow.checked = false;
            page = Math.max(0, page + direction);
            render();
            viewport.scrollTop = 0;
        });
    }
    field('download').addEventListener('click', () => {
        const url = host.URL.createObjectURL(new Blob([formatLogs(visible)], { type: 'text/plain;charset=utf-8' }));
        const link = root.createElement('a');
        link.href = url;
        link.download = 'themerr-logs.txt';
        root.body.append(link);
        link.click();
        link.remove();
        host.setTimeout(() => host.URL.revokeObjectURL(url), 1000);
    });
    const stop = () => { active = false; host.clearTimeout(timer); };
    host.addEventListener('pagehide', stop, { signal });
    host.addEventListener('pageshow', () => { if (!active) { active = true; void update(); } }, { signal });
    signal?.addEventListener('abort', stop, { once: true });
    void update();
}
