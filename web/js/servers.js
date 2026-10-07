import { api, busy, toast } from './api.js';
import { refreshPage } from './workspace_navigation.js';
import { _ } from './i18n.js';

let selectedServerTab = 'add-plex-tab';

function initPlexSsh(signal) {
    document.querySelectorAll('[data-plex-ssh-form]').forEach(form => {
        const status = form.querySelector('[data-ssh-status]');
        const check = form.querySelector('[data-check-ssh]');
        const remove = form.querySelector('[data-remove-ssh]');
        const endpoint = `/api/plex/servers/${encodeURIComponent(form.dataset.serverId)}/ssh`;
        const clearSecrets = sent => {
            [
                'private_key',
                'passphrase',
                'password',
            ].forEach(name => {
                if (!sent || form.elements[name].value === sent[name]) form.elements[name].value = '';
            });
        };
        const setAuthFields = () => {
            const key = form.elements.auth_type.value === 'key';
            form.querySelector('[data-ssh-key-fields]').hidden = !key;
            form.querySelector('[data-ssh-password-fields]').hidden = key;
        };
        setAuthFields();
        form.elements.auth_type.addEventListener('change', setAuthFields, { signal });
        form.addEventListener('submit', event => {
            event.preventDefault();
            void busy(form.querySelector('button[type="submit"]'), async () => {
                status.textContent = _('Verifying SSH connection…');
                const data = new FormData(form);
                const body = { port: Number(data.get('port')) };
                [
                    'host',
                    'username',
                    'data_directory',
                    'host_fingerprint',
                    'auth_type',
                    'private_key',
                    'passphrase',
                    'password',
                ].forEach(name => { body[name] = data.get(name); });
                try {
                    const result = await api(endpoint, {
                        method: 'PUT',
                        body,
                    });
                    form.dataset.configured = 'true';
                    form.elements.data_directory.value = result.settings.data_directory;
                    check.disabled = false;
                    remove.disabled = false;
                    status.textContent = _(result.message);
                } catch (error) {
                    status.textContent = _(error.message);
                    throw error;
                } finally {
                    clearSecrets(body);
                }
            });
        }, { signal });
        check.addEventListener('click', () => busy(check, async () => {
            status.textContent = _('Checking SSH connection…');
            const result = await api(`${endpoint}/check`);
            status.textContent = _(result.message);
        }), { signal });
        remove.addEventListener('click', () => busy(remove, async () => {
            const result = await api(endpoint, { method: 'DELETE' });
            form.dataset.configured = 'false';
            clearSecrets();
            check.disabled = true;
            status.textContent = _(result.message);
        }).finally(() => { remove.disabled = form.dataset.configured !== 'true'; }), { signal });
    });
}

function initServerTabs(signal) {
    const tablist = document.getElementById('add-server-tabs');
    if (!tablist) return;
    const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
    const select = selected => {
        selectedServerTab = selected.id;
        tabs.forEach(tab => {
            const active = tab === selected;
            tab.setAttribute('aria-selected', String(active));
            tab.tabIndex = active ? 0 : -1;
            document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
        });
    };
    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => select(tab), { signal });
        tab.addEventListener('keydown', event => {
            let next;
            if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
            else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
            else if (event.key === 'Home') next = 0;
            else if (event.key === 'End') next = tabs.length - 1;
            else return;
            event.preventDefault();
            select(tabs[next]);
            tabs[next].focus();
        }, { signal });
    });
    select(tabs.find(tab => tab.id === selectedServerTab) || tabs[0]);
}

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
    connect.textContent = resource.connected ? _('Connected') : _('Connect');
    connect.disabled = Boolean(resource.connected) || !resource.connections.length;
    connect.addEventListener('click', () => {
        if (resource.connected) return;
        return busy(connect, async () => {
            await api('/api/servers', { body: { url: addresses.value,
                resource_id: source === 'account' ? resource.id : undefined } });
            if (connect.isConnected) await refreshPage();
        });
    });
    row.append(name, addresses, connect);
    return row;
}

export function initServers(signal) {
    initServerTabs(signal);
    initJellyfin(signal);
    initPlexSsh(signal);
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
        if (!window.confirm('Disconnect Plex and pause all saved Plex servers? Your local theme history will be kept.')) return;
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
                ? 'No Plex servers responded on LAN. Check that local network discovery (GDM) is enabled in Plex and multicast can reach this machine. You can use an account or manual address instead.'
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
        if (!window.confirm('Remove this server and its local theme history? Media will stay on the server.')) return;
        void busy(button, async () => {
            await api(`/api/servers/${encodeURIComponent(button.dataset.removeServer)}`, { method: 'DELETE' });
            if (active) await refreshPage();
        });
    }));
}

function connectorAddress(result) {
    const address = new URL(result.repository_url || window.location.origin);
    if (result.http_port && (!result.repository_url ||
        (address.hostname === window.location.hostname && address.port === window.location.port))) {
        address.protocol = 'http:';
        address.port = String(result.http_port);
        address.pathname = '/';
    }
    return address.href.replace(/\/$/, '');
}

function initJellyfin(signal) {
    const form = document.getElementById('jellyfin-server-form');
    form?.addEventListener('submit', event => {
        event.preventDefault();
        void busy(form.querySelector('button[type="submit"]'), async () => {
            const data = new FormData(form);
            await api('/api/jellyfin/servers', { body: { url: data.get('url'), api_key: data.get('api_key') } });
            form.reset();
            if (!signal?.aborted && form.isConnected) await refreshPage();
        });
    }, { signal });
    const discover = document.getElementById('jellyfin-discover');
    discover?.addEventListener('click', () => busy(discover, async () => {
        const results = document.getElementById('jellyfin-discovery-results');
        results.textContent = _('Looking for Jellyfin servers…');
        try {
            const result = await api('/api/jellyfin/discover');
            if (signal?.aborted || !results.isConnected) return;
            results.replaceChildren();
            if (!result.servers.length) {
                results.textContent = _('No Jellyfin servers responded. Check UDP port 7359 and local network discovery, or enter an address manually.');
            }
            result.servers.forEach(server => {
                const row = document.createElement('div');
                row.className = 'discovered-server';
                const name = document.createElement('strong');
                name.textContent = server.name;
                const address = document.createElement('span');
                address.textContent = server.url;
                const choose = document.createElement('button');
                choose.type = 'button';
                choose.className = 'btn btn-outline-light btn-sm';
                choose.textContent = server.connected ? _('Connected') : _('Use this address');
                choose.disabled = Boolean(server.connected);
                choose.addEventListener('click', () => {
                    if (server.connected) return;
                    form.elements.url.value = server.url;
                    form.elements.api_key.focus();
                }, { signal });
                row.append(name, address, choose);
                results.append(row);
            });
        } catch (error) {
            if (!signal?.aborted && results.isConnected) results.textContent = error.message;
            throw error;
        }
    }), { signal });
    document.querySelectorAll('[data-connector-form]').forEach(connectorForm => {
        const status = connectorForm.querySelector('[data-connector-status]');
        const button = connectorForm.querySelector('button[type="submit"]');
        const restartButton = connectorForm.closest('.server-card').querySelector('[data-restart-server]');
        const url = `/api/jellyfin/servers/${encodeURIComponent(connectorForm.dataset.serverId)}/connector`;
        let timer;
        let suggested = false;
        let automatic = connectorForm.dataset.autoUpdate === 'true';
        async function check() {
            try {
                const result = await api(url, { method: 'GET' });
                if (signal?.aborted || !status.isConnected) return;
                status.textContent = result.message;
                automatic = Boolean(result.auto_update);
                button.textContent = automatic ? _('Save connector address') : _('Install matching connector');
                button.hidden = !automatic && Boolean(result.installed || result.restart_required || result.phase === 'restarting');
                if (restartButton) {
                    restartButton.disabled = !result.can_restart || result.phase === 'restarting';
                    restartButton.title = result.can_restart ? '' :
                        _('This server cannot restart itself. Restart its service or container.');
                }
                if (!suggested) {
                    if (!connectorForm.elements.themerr_url.value) {
                        connectorForm.elements.themerr_url.value = connectorAddress(result);
                    }
                    suggested = true;
                }
                timer = setTimeout(check, result.restart_required ? 5000 : 30000);
            } catch (error) {
                if (!signal?.aborted && status.isConnected) {
                    status.textContent = error.message;
                    timer = setTimeout(check, 10000);
                }
            }
        }
        signal?.addEventListener('abort', () => clearTimeout(timer), { once: true });
        void check();
        connectorForm.addEventListener('submit', event => {
            event.preventDefault();
            void busy(button, async () => {
                const result = await api(url, { method: automatic ? 'PUT' : 'POST',
                    body: { themerr_url: new FormData(connectorForm).get('themerr_url') } });
                if (!signal?.aborted && status.isConnected) {
                    status.textContent = result.message;
                    toast(result.message);
                    clearTimeout(timer);
                    timer = setTimeout(check, 5000);
                }
            });
        }, { signal });
        restartButton?.addEventListener('click', () => {
            if (!window.confirm(_('Restart Jellyfin now? Active playback will be interrupted.'))) return;
            void busy(restartButton, async () => {
                const result = await api(`/api/jellyfin/servers/${encodeURIComponent(connectorForm.dataset.serverId)}/restart`,
                    { body: {} });
                if (!signal?.aborted && status.isConnected) {
                    status.textContent = result.message;
                    toast(result.message);
                    clearTimeout(timer);
                    timer = setTimeout(check, 5000);
                }
            });
        }, { signal });
    });
}
