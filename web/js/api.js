export async function api(path, { method = 'POST', body, form } = {}) {
    const headers = { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, { method, headers, body: form || (body === undefined ? undefined : JSON.stringify(body)) });
    if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
        throw new Error('Your session expired. Sign in to continue.');
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || `The request failed (HTTP ${response.status}).`);
    return result;
}

export function toast(message, error = false) {
    const region = document.getElementById('toast-region');
    const notice = document.createElement('div');
    notice.className = `app-toast${error ? ' error' : ''}`;
    const text = document.createElement('span');
    text.textContent = message;
    const close = document.createElement('button');
    close.type = 'button';
    close.textContent = '×';
    close.setAttribute('aria-label', 'Dismiss message');
    close.addEventListener('click', () => notice.remove());
    notice.append(text, close);
    region.append(notice);
    setTimeout(() => notice.remove(), error ? 15000 : 7000);
}

export async function busy(button, operation) {
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    try {
        return await operation();
    } catch (error) {
        toast(error.message, true);
    } finally {
        button.disabled = false;
        button.removeAttribute('aria-busy');
    }
}
