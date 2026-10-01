import { api } from './api.js';
import { refreshIcons } from './icons.js';

export function initDirectoryPicker() {
    const picker = document.getElementById('directory-picker');
    if (!picker) return;
    const current = document.getElementById('directory-current');
    const list = document.getElementById('directory-list');
    const error = document.getElementById('directory-error');
    const up = document.getElementById('directory-up');
    const select = document.getElementById('directory-select');
    let field;
    let path;
    let requestNumber = 0;
    async function loadDirectory(requested) {
        const ticket = ++requestNumber;
        error.textContent = '';
        select.disabled = true;
        up.disabled = true;
        list.replaceChildren();
        const result = await api('/api/directories', { body: { path: requested } });
        if (ticket !== requestNumber) return;
        path = result.path;
        current.textContent = path;
        up.disabled = !result.parent;
        up.dataset.path = result.parent || '';
        result.directories.forEach(directory => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'list-group-item list-group-item-action text-start';
            const icon = document.createElement('i');
            icon.dataset.lucide = 'folder';
            const name = document.createElement('span');
            name.textContent = directory.name;
            button.append(icon, name);
            button.addEventListener('click', () => loadDirectory(directory.path).catch(exc => { error.textContent = exc.message; }));
            list.append(button);
        });
        refreshIcons();
        select.disabled = false;
    }
    document.querySelectorAll('[data-directory-target]').forEach(button => button.addEventListener('click', async () => {
        field = document.getElementById(button.dataset.directoryTarget);
        picker.showModal();
        try {
            await loadDirectory(field.value || '');
        } catch (exc) {
            error.textContent = exc.message;
            if (field.value) {
                try { await loadDirectory(''); } catch (fallback) { error.textContent = fallback.message; }
            }
        }
    }));
    up.addEventListener('click', () => loadDirectory(up.dataset.path).catch(exc => { error.textContent = exc.message; }));
    document.getElementById('directory-cancel').addEventListener('click', () => picker.close());
    picker.addEventListener('close', () => { requestNumber++; });
    select.addEventListener('click', () => {
        field.value = path;
        field.dispatchEvent(new Event('input', { bubbles: true }));
        picker.close();
    });
}
