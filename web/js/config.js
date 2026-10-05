import { api, toast } from './api.js';
import { _ } from './i18n.js';
import { refreshPage } from './workspace_navigation.js';

export function initSettings(signal) {
    const form = document.getElementById('configForm');
    if (!form) return;
    const save = document.getElementById('save-button');
    const status = document.getElementById('settings-save-status');
    const locale = document.getElementById('General-LOCALE') || document.getElementById('LOCALE');
    const pageLocale = locale.value;
    let dirty = false;
    let revision = 0;
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
        form.querySelectorAll('[category]').forEach(field => {
            if (!field.disabled) data.append(`${field.getAttribute('category')}|${field.dataset.settingKey || field.id}`,
                field.type === 'checkbox' ? String(field.checked) : field.value);
        });
        save.disabled = true;
        save.setAttribute('aria-busy', 'true');
        const submittedRevision = revision;
        const submittedLocale = locale.value;
        try {
            await api('/api/settings', { form: data });
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
