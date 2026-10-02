import { api, busy, toast } from './api.js';

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
        window.location.reload();
    }));
    row.append(name, addresses, connect);
    return row;
}

export function initServers() {
    const authStart = document.getElementById('plex-auth-start');
    if (!authStart) return;
    const status = document.getElementById('plex-auth-status');
    const link = document.getElementById('plex-auth-link');
    let pollTimer;
    window.addEventListener('pagehide', () => clearTimeout(pollTimer));
    async function pollLogin() {
        try {
            const result = await api('/api/plex/auth/check');
            if (result.connected) {
                window.location.reload();
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
        void busy(disconnect, async () => { await api('/api/plex/auth/disconnect'); window.location.reload(); });
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
            window.location.reload();
        });
    });
    document.querySelectorAll('[data-server-form]').forEach(form => form.addEventListener('submit', event => {
        event.preventDefault();
        void busy(form.querySelector('button[type="submit"]'), async () => {
            const data = new FormData(form);
            const result = await api(`/api/servers/${encodeURIComponent(form.dataset.serverId)}`, { body: {
                enabled: form.elements.enabled.checked, data_directory: data.get('data_directory'),
                ignored_libraries: data.get('ignored_libraries'),
            } });
            toast(result.message);
            window.location.reload();
        });
    }));
    document.querySelectorAll('[data-remove-server]').forEach(button => button.addEventListener('click', () => {
        if (!window.confirm('Remove this server and its local theme history? Plex media will stay on the server.')) return;
        void busy(button, async () => {
            await api(`/api/servers/${encodeURIComponent(button.dataset.removeServer)}`, { method: 'DELETE' });
            window.location.reload();
        });
    }));
}
