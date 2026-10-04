import { api, busy, toast } from './api.js';
import { refreshPage } from './workspace_navigation.js';
import { _ } from './i18n.js';

function initLibraryPicker(form, signal) {
    const picker = form.querySelector('[data-library-picker]');
    const options = picker.querySelector('[data-library-options]');
    const summary = picker.querySelector('[data-library-summary]');
    const status = picker.querySelector('[data-library-status]');
    const selected = () => Array.from(options.querySelectorAll('input:checked'));
    const updateSummary = () => {
        summary.textContent = selected().map(input => input.nextElementSibling.textContent).join(', ') ||
            _('Select libraries to ignore');
    };
    updateSummary();
    options.addEventListener('change', updateSummary, { signal });
    let loaded = false;
    let loading = false;
    picker.addEventListener('toggle', async () => {
        if (!picker.open || loaded || loading) return;
        loading = true;
        status.textContent = _('Loading libraries…');
        try {
            const result = await api(`/api/servers/${encodeURIComponent(form.dataset.serverId)}/libraries`, { method: 'GET' });
            if (signal?.aborted || !picker.isConnected) return;
            const checked = new Set(selected().map(input => input.value));
            const libraries = new Map(result.libraries.map(library => [library.id, library.title]));
            checked.forEach(id => {
                if (!libraries.has(id)) libraries.set(id, `${_('Unavailable library')} (${id})`);
            });
            options.replaceChildren();
            libraries.forEach((title, id) => {
                const label = document.createElement('label');
                label.className = 'library-choice';
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.name = 'ignored_libraries';
                input.value = id;
                input.checked = checked.has(id);
                const text = document.createElement('span');
                text.textContent = title;
                label.append(input, text);
                options.append(label);
            });
            if (result.cached) {
                status.textContent = _('Showing cached libraries. Enable or reconnect this server to load its current libraries.');
            } else {
                status.textContent = libraries.size ? '' : _('This server has no libraries.');
            }
            updateSummary();
            loaded = !result.cached;
        } catch {
            if (!signal?.aborted && picker.isConnected) {
                status.textContent = _('Unable to load libraries. Your selections are kept. Close and reopen the list to retry.');
            }
        } finally {
            loading = false;
        }
    }, { signal });
    picker.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            picker.open = false;
            picker.querySelector('summary').focus();
        }
    }, { signal });
    document.addEventListener('click', event => {
        if (!picker.contains(event.target)) picker.open = false;
    }, { signal });
}

function connectionOption(connection) {
    const option = document.createElement('option');
    option.value = connection.url;
    let location = connection.local ? 'Local' : 'Remote';
    if (connection.relay) location = 'Relay';
    const protocol = connection.url.startsWith('https:') ? 'HTTPS' : 'HTTP';
    option.textContent = `${location} · ${protocol} · ${connection.url}`;
    return option;
}

function connectionOrder(a, b) {
    return Number(b.local) - Number(a.local) || Number(a.relay) - Number(b.relay) ||
        Number(b.url.startsWith('https:')) - Number(a.url.startsWith('https:'));
}

function discoveredServer(resource, source) {
    const row = document.createElement('div');
    row.className = 'discovered-server';
    const name = document.createElement('strong');
    name.textContent = resource.name;
    const addresses = document.createElement('select');
    addresses.className = 'form-select';
    addresses.setAttribute('aria-label', `Address for ${resource.name}`);
    addresses.append(...[...resource.connections].sort(connectionOrder).map(connectionOption));
    const connect = document.createElement('button');
    connect.type = 'button';
    connect.className = 'btn btn-primary btn-sm';
    connect.textContent = 'Connect';
    connect.disabled = !resource.connections.length;
    connect.addEventListener('click', () => busy(connect, async () => {
        await api('/api/servers', { body: { url: addresses.value,
            resource_id: source === 'account' ? resource.id : undefined } });
        if (connect.isConnected) await refreshPage();
    }));
    row.append(name, addresses, connect);
    return row;
}

export function initServers(signal) {
    const authStart = document.getElementById('plex-auth-start');
    if (!authStart) return;
    const status = document.getElementById('plex-auth-status');
    const link = document.getElementById('plex-auth-link');
    let pollTimer;
    let active = true;
    const stop = () => { active = false; clearTimeout(pollTimer); };
    window.addEventListener('pagehide', stop, { once: true, signal });
    signal?.addEventListener('abort', stop, { once: true });
    async function pollLogin() {
        try {
            const result = await api('/api/plex/auth/check');
            if (!active) return;
            if (result.connected) {
                await refreshPage();
                return;
            }
            pollTimer = setTimeout(pollLogin, 2000);
        } catch (error) {
            toast(error.message, true);
            authStart.disabled = false;
            authStart.removeAttribute('aria-busy');
            status.textContent = 'Plex sign-in did not complete. Please try again.';
        }
    }
    authStart.addEventListener('click', async () => {
        const popup = window.open('', '_blank');
        authStart.disabled = true;
        authStart.setAttribute('aria-busy', 'true');
        try {
            const result = await api('/api/plex/auth/start');
            if (!active) {
                if (popup) popup.close();
                return;
            }
            link.href = result.auth_url;
            link.classList.remove('d-none');
            if (popup) { popup.opener = null; popup.location.assign(result.auth_url); }
            status.textContent = 'Waiting for Plex sign-in… Complete the sign-in in the Plex tab.';
            pollTimer = setTimeout(pollLogin, 2000);
        } catch (error) {
            if (popup) popup.close();
            authStart.disabled = false;
            authStart.removeAttribute('aria-busy');
            toast(error.message, true);
        }
    });
    const disconnect = document.getElementById('plex-auth-disconnect');
    disconnect.addEventListener('click', () => {
        if (!window.confirm('Disconnect Plex and pause all saved servers? Your local theme history will be kept.')) return;
        void busy(disconnect, async () => {
            await api('/api/plex/auth/disconnect');
            if (active) await refreshPage();
        });
    });
    const results = document.getElementById('discovery-results');
    document.querySelectorAll('[data-discover]').forEach(button => button.addEventListener('click', () => busy(button, async () => {
        results.textContent = 'Looking for Plex servers…';
        let response;
        try {
            response = await api('/api/servers/discover', { body: { source: button.dataset.discover } });
        } catch (error) {
            results.textContent = error.message;
            throw error;
        }
        results.replaceChildren();
        if (!response.servers.length) {
            results.textContent = button.dataset.discover === 'local'
                ? 'No Plex servers responded on LAN. Check that local network discovery (GDM) is enabled in Plex ' +
                  'and multicast can reach this machine. You can use an account or manual address instead.'
                : 'No servers are advertised for this Plex account. Check account access or enter an address manually.';
            return;
        }
        response.servers.forEach(resource => results.append(discoveredServer(resource, button.dataset.discover)));
    })));
    document.getElementById('manual-server-form').addEventListener('submit', event => {
        event.preventDefault();
        void busy(event.target.querySelector('button[type="submit"]'), async () => {
            await api('/api/servers', { body: { url: new FormData(event.target).get('url') } });
            if (active) await refreshPage();
        });
    });
    document.querySelectorAll('[data-server-form]').forEach(form => {
        initLibraryPicker(form, signal);
        form.addEventListener('submit', event => {
            event.preventDefault();
            return busy(form.querySelector('button[type="submit"]'), async () => {
                const data = new FormData(form);
                const ignoredLibraries = data.getAll('ignored_libraries').filter(value => typeof value === 'string');
                const result = await api(`/api/servers/${encodeURIComponent(form.dataset.serverId)}`, { body: {
                    enabled: form.elements.enabled.checked, data_directory: data.get('data_directory'),
                    ignored_libraries: ignoredLibraries.join(','),
                } });
                toast(result.message);
                if (active) await refreshPage();
            });
        });
    });
    document.querySelectorAll('[data-remove-server]').forEach(button => button.addEventListener('click', () => {
        if (!window.confirm('Remove this server and its local theme history? Plex media will stay on the server.')) return;
        void busy(button, async () => {
            await api(`/api/servers/${encodeURIComponent(button.dataset.removeServer)}`, { method: 'DELETE' });
            if (active) await refreshPage();
        });
    }));
}
