import { api, toast } from './api.js';

export function initSettings() {
    const form = document.getElementById('configForm');
    if (!form) return;
    const save = document.getElementById('save-button');
    const status = document.getElementById('settings-save-status');
    let dirty = false;
    let revision = 0;
    function markDirty() {
        revision += 1;
        dirty = true;
        save.disabled = false;
        status.textContent = 'Unsaved changes';
    }
    form.addEventListener('input', markDirty);
    form.addEventListener('change', markDirty);
    window.addEventListener('beforeunload', event => {
        if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        const data = new FormData();
        form.querySelectorAll('[category]').forEach(field => {
            if (!field.disabled) data.append(`${field.getAttribute('category')}|${field.id}`,
                field.type === 'checkbox' ? String(field.checked) : field.value);
        });
        save.disabled = true;
        save.setAttribute('aria-busy', 'true');
        const submittedRevision = revision;
        try {
            await api('/api/settings', { form: data });
            dirty = revision !== submittedRevision;
            save.disabled = !dirty;
            status.textContent = dirty ? 'Unsaved changes' : 'All changes saved.';
            toast('Settings saved. Network changes take effect after restarting Themerr.');
        } catch (error) {
            toast(error.message, true);
            save.disabled = false;
            status.textContent = 'Unable to save changes.';
        } finally {
            save.removeAttribute('aria-busy');
        }
    });
    document.getElementById('password-form').addEventListener('submit', async event => {
        event.preventDefault();
        if (dirty) {
            toast('Save your settings changes before changing your password.', true);
            return;
        }
        const button = event.target.querySelector('button');
        button.disabled = true;
        try {
            const result = await api('/api/admin/password', { form: new FormData(event.target) });
            dirty = false;
            toast(result.message);
            // Refresh the CSRF token after rotating the authenticated session.
            setTimeout(() => window.location.reload(), 1000);
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
}
