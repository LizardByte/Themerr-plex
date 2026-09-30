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

    const directoryPicker = document.getElementById('directory-picker');
    const directoryCurrent = document.getElementById('directory-current');
    const directoryList = document.getElementById('directory-list');
    const directoryError = document.getElementById('directory-error');
    const directoryUp = document.getElementById('directory-up');
    const directorySelect = document.getElementById('directory-select');
    let directoryField;
    let currentDirectory;

    async function loadDirectory(path) {
        directoryError.textContent = '';
        directorySelect.disabled = true;
        directoryUp.disabled = true;
        directoryList.replaceChildren();
        const response = await fetch('/api/directories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.dataset.csrfToken },
            body: JSON.stringify({ path }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.message || `HTTP ${response.status}`);

        currentDirectory = result.path;
        directoryCurrent.textContent = currentDirectory;
        directoryUp.disabled = !result.parent;
        directoryUp.dataset.path = result.parent || '';
        result.directories.forEach(directory => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'list-group-item list-group-item-action text-start';
            button.textContent = directory.name;
            button.addEventListener('click', () => {
                loadDirectory(directory.path).catch(error => { directoryError.textContent = error.message; });
            });
            directoryList.append(button);
        });
        directorySelect.disabled = false;
    }

    form.querySelectorAll('[data-directory-target]').forEach(button => {
        button.addEventListener('click', async () => {
            directoryField = document.getElementById(button.dataset.directoryTarget);
            directoryPicker.showModal();
            try {
                await loadDirectory(directoryField.value);
            } catch (error) {
                directoryError.textContent = error.message;
                if (directoryField.value) {
                    try {
                        await loadDirectory('');
                    } catch (fallbackError) {
                        directoryError.textContent = fallbackError.message;
                    }
                }
            }
        });
    });
    directoryUp.addEventListener('click', () => {
        loadDirectory(directoryUp.dataset.path).catch(error => { directoryError.textContent = error.message; });
    });
    document.getElementById('directory-cancel').addEventListener('click', () => directoryPicker.close());
    directorySelect.addEventListener('click', () => {
        directoryField.value = currentDirectory;
        directoryField.dispatchEvent(new Event('input', { bubbles: true }));
        directoryPicker.close();
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
