import { api, toast } from './api.js';
import { _ } from './i18n.js';
import { refreshPage } from './workspace_navigation.js';

function setSecretVisible(button, visible) {
    const label = visible ? _('Hide cookies') : _('Show cookies');
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-pressed', String(visible));
    button.title = label;
    button.querySelectorAll('[data-secret-icon]').forEach(icon => {
        icon.hidden = icon.dataset.secretIcon !== (visible ? 'hide' : 'show');
    });
}

function markSecretsSaved(form, secretFields, revealedSecrets) {
    for (const { field, value } of secretFields) {
        field.dataset.hasSecret = 'true';
        field.placeholder = _('Cookies saved');
        if (field.value === value) {
            field.value = '';
            revealedSecrets.delete(field);
            field.type = 'password';
            const button = form.querySelector(`[data-secret-toggle="${field.id}"]`);
            setSecretVisible(button, false);
        }
    }
}

function markSecretsCleared(form, clearedSecrets, revealedSecrets, unchanged) {
    for (const checkbox of clearedSecrets) {
        for (const input of form.querySelectorAll('[category]')) {
            if (`${input.getAttribute('category')}|${input.dataset.settingKey || input.id}` !== checkbox.dataset.clearSecret) continue;
            input.dataset.hasSecret = 'false';
            input.placeholder = _('No cookies saved');
            if (unchanged) input.value = '';
            revealedSecrets.delete(input);
        }
    }
    if (unchanged) {
        for (const field of clearedSecrets) field.checked = false;
    }
}

export function initSettings(signal) {
    const form = document.getElementById('configForm');
    if (!form) return;
    const save = document.getElementById('save-button');
    const status = document.getElementById('settings-save-status');
    const locale = document.getElementById('General-LOCALE') || document.getElementById('LOCALE');
    const pageLocale = locale.value;
    let dirty = false;
    let revision = 0;
    const revealedSecrets = new Map();
    form.querySelectorAll('[data-secret-toggle]').forEach(button => {
        const field = document.getElementById(button.dataset.secretToggle);
        button.addEventListener('click', async () => {
            const show = field.type === 'password';
            button.disabled = true;
            try {
                if (show && !field.value && field.dataset.hasSecret === 'true') {
                    const requestedRevision = revision;
                    const result = await api('/api/settings/youtube-cookies');
                    // Keep any edits entered while the reveal request was pending.
                    if (!form.isConnected || field.value || revision !== requestedRevision) return;
                    field.value = result.value;
                    revealedSecrets.set(field, result.value);
                }
                field.type = show ? 'text' : 'password';
                setSecretVisible(button, show);
            } catch (error) {
                toast(error.message, true);
            } finally {
                button.disabled = false;
            }
        });
    });
    function markDirty() {
        revision += 1;
        dirty = true;
        save.disabled = false;
        status.textContent = _('Unsaved changes');
    }
    form.addEventListener('input', markDirty);
    form.addEventListener('change', markDirty);
    window.addEventListener('beforeunload', event => {
        if (dirty) event.preventDefault();
    }, { signal });
    document.addEventListener('themerr:before-navigate', event => {
        if (dirty && !window.confirm(_('Discard unsaved settings changes?'))) event.preventDefault();
    }, { signal });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        const data = new FormData();
        const secretFields = [];
        form.querySelectorAll('[category]').forEach(field => {
            if (field.dataset.secret && !field.value) return;
            if (field.dataset.secret && field.value === revealedSecrets.get(field)) return;
            if (!field.disabled) data.append(`${field.getAttribute('category')}|${field.dataset.settingKey || field.id}`,
                field.type === 'checkbox' ? String(field.checked) : field.value);
            if (field.dataset.secret) secretFields.push({
                field,
                value: field.value,
            });
        });
        const clearedSecrets = [];
        form.querySelectorAll('[data-clear-secret]').forEach(field => {
            if (!field.checked) return;
            data.delete(field.dataset.clearSecret);
            data.append(`${field.dataset.clearSecret}|clear`, 'true');
            clearedSecrets.push(field);
        });
        save.disabled = true;
        save.setAttribute('aria-busy', 'true');
        const submittedRevision = revision;
        const submittedLocale = locale.value;
        try {
            await api('/api/settings', { form: data });
            markSecretsSaved(form, secretFields, revealedSecrets);
            markSecretsCleared(form, clearedSecrets, revealedSecrets, revision === submittedRevision);
            dirty = revision !== submittedRevision;
            save.disabled = !dirty;
            status.textContent = dirty ? _('Unsaved changes') : _('All changes saved.');
            if (!dirty && submittedLocale !== pageLocale && form.isConnected) void refreshPage();
            toast(_('Settings saved. Network changes take effect after restarting Themerr.'));
        } catch (error) {
            toast(error.message, true);
            save.disabled = false;
            status.textContent = _('Unable to save changes.');
        } finally {
            save.removeAttribute('aria-busy');
        }
    });
    document.getElementById('password-form').addEventListener('submit', async event => {
        event.preventDefault();
        if (dirty) {
            toast(_('Save your settings changes before changing your password.'), true);
            return;
        }
        const button = event.target.querySelector('button');
        button.disabled = true;
        try {
            const result = await api('/api/admin/password', { form: new FormData(event.target) });
            dirty = false;
            toast(result.message);
            // Refresh the CSRF token after rotating the authenticated session.
            setTimeout(() => { if (form.isConnected) void refreshPage(); }, 1000);
        } catch (error) { toast(error.message, true); } finally { button.disabled = false; }
    });
    const observer = new IntersectionObserver(entries => {
        const visible = entries.find(entry => entry.isIntersecting);
        if (!visible) return;
        document.querySelectorAll('.settings-nav a').forEach(link => {
            link.classList.toggle('active', link.hash === `#${visible.target.id}`);
        });
    }, { rootMargin: '-10% 0px -65% 0px' });
    document.querySelectorAll('.settings-panel').forEach(panel => observer.observe(panel));
    signal?.addEventListener('abort', () => observer.disconnect(), { once: true });
}
