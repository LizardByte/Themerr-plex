import { showAlert } from './show_alert.js';

const form = document.getElementById('configForm');
if (form) {
    const saveButton = document.getElementById('save-button');
    form.addEventListener('input', () => { saveButton.disabled = false; });
    form.addEventListener('change', () => { saveButton.disabled = false; });

    saveButton.addEventListener('click', async () => {
        if (!form.reportValidity()) return;

        const data = new FormData();
        form.querySelectorAll('input[category], textarea[category], select[category]').forEach((field) => {
            if (field.disabled) return;
            if (field.type === 'radio' && !field.checked) return;
            data.append(`${field.getAttribute('category')}|${field.id}`,
                field.type === 'checkbox' ? String(field.checked) : field.value);
        });

        saveButton.disabled = true;
        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                body: data,
                headers: { 'X-CSRFToken': form.dataset.csrfToken },
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'OK') {
                throw new Error(result.message || `HTTP ${response.status}`);
            }
            showAlert(result.message, 'alert-success', 'check', 5000);
        } catch (error) {
            showAlert(error.message, 'alert-danger', 'triangle-alert', 5000);
            saveButton.disabled = false;
        }
    });

    const plexAuth = document.getElementById('plex-auth');
    const authStatus = document.getElementById('plex-auth-status');
    const authStart = document.getElementById('plex-auth-start');
    const authDisconnect = document.getElementById('plex-auth-disconnect');
    const authLink = document.getElementById('plex-auth-link');
    const csrfHeaders = { 'X-CSRFToken': form.dataset.csrfToken };

    function setConnected(connected) {
        authStatus.textContent = connected ? plexAuth.dataset.connected : plexAuth.dataset.disconnected;
        authDisconnect.classList.toggle('d-none', !connected);
    }

    async function authRequest(path, method = 'GET') {
        const response = await fetch(path, { method, headers: csrfHeaders });
        const result = await response.json();
        if (!response.ok && response.status !== 202) {
            throw new Error(result.message || `HTTP ${response.status}`);
        }
        return result;
    }

    async function checkPlexLogin() {
        try {
            const result = await authRequest('/api/plex/auth/check', 'POST');
            if (result.connected) {
                setConnected(true);
                authStart.disabled = false;
                authLink.classList.add('d-none');
                showAlert(plexAuth.dataset.connected, 'alert-success', 'check', 5000);
                return;
            }
            setTimeout(checkPlexLogin, 1000);
        } catch (error) {
            authStart.disabled = false;
            setConnected(false);
            showAlert(error.message, 'alert-danger', 'triangle-alert', 5000);
        }
    }

    authStart.addEventListener('click', async () => {
        if (!saveButton.disabled) {
            showAlert('Save your settings before signing in to Plex.', 'alert-warning', 'triangle-alert', 5000);
            return;
        }
        const popup = window.open('', '_blank');
        authStart.disabled = true;
        try {
            const result = await authRequest('/api/plex/auth/start', 'POST');
            authLink.href = result.auth_url;
            authLink.classList.remove('d-none');
            if (popup) {
                popup.opener = null;
                popup.location.assign(result.auth_url);
            }
            authStatus.textContent = plexAuth.dataset.pending;
            setTimeout(checkPlexLogin, 1000);
        } catch (error) {
            if (popup) popup.close();
            authStart.disabled = false;
            showAlert(error.message, 'alert-danger', 'triangle-alert', 5000);
        }
    });

    authDisconnect.addEventListener('click', async () => {
        authDisconnect.disabled = true;
        try {
            await authRequest('/api/plex/auth/disconnect', 'POST');
            setConnected(false);
            authLink.classList.add('d-none');
        } catch (error) {
            showAlert(error.message, 'alert-danger', 'triangle-alert', 5000);
        } finally {
            authDisconnect.disabled = false;
        }
    });

    authRequest('/api/plex/auth').then(result => setConnected(result.connected)).catch(error => {
        showAlert(error.message, 'alert-danger', 'triangle-alert', 5000);
    });
}
