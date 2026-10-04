import { api } from './api.js';

export function publicationAge(date, now = Date.now(), locale = undefined) {
    const seconds = (new Date(date).getTime() - now) / 1000;
    if (!date || !Number.isFinite(seconds)) return null;
    const absolute = Math.abs(seconds);
    const [unit, divisor] = [['day', 86400], ['hour', 3600], ['minute', 60], ['second', 1]]
        .find(([, duration]) => absolute >= duration) ?? ['second', 1];
    return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(Math.round(seconds / divisor), unit);
}

export function initDatabaseStatus(root = document, query = () => api('/api/themerrdb', { method: 'GET' }), signal) {
    const status = root.querySelector('[data-database-status]');
    if (!status) return;
    const time = status.querySelector('[data-database-time]');
    const link = status.querySelector('[data-database-link]');
    const warning = status.querySelector('[data-database-stale]');
    let snapshot;
    let pollTimer;
    let active = true;
    function render() {
        const locale = root.documentElement?.lang || undefined;
        const age = publicationAge(snapshot?.updated_at, Date.now(), locale);
        time.textContent = age ?? status.dataset.unknownLabel;
        if (age) {
            const date = new Date(snapshot.updated_at);
            time.dateTime = date.toISOString();
            time.title = date.toLocaleString(locale, { dateStyle: 'full', timeStyle: 'long' });
        }
        warning.hidden = !snapshot?.stale;
        warning.title = status.dataset.staleLabel;
        if (snapshot?.url) link.href = snapshot.url;
    }
    async function update() {
        let delay = 3600000;
        try {
            snapshot = await query();
            if (Number.isFinite(snapshot.next_check)) delay = Math.max(60000, snapshot.next_check * 1000 - Date.now());
        } catch {
            snapshot = { ...snapshot, stale: true };
        } finally {
            if (active) {
                render();
                pollTimer = setTimeout(update, delay);
            }
        }
    }
    const ageTimer = setInterval(() => { if (snapshot) render(); }, 60000);
    const stop = () => {
        active = false;
        clearTimeout(pollTimer);
        clearInterval(ageTimer);
    };
    window.addEventListener('pagehide', stop, { once: true, signal });
    signal?.addEventListener('abort', stop, { once: true });
    void update();
}
