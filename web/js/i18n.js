let messages = {};

export async function initTranslations(root = document, load = fetch) {
    if (!root.body.classList.contains('app-body') || root.documentElement.lang.startsWith('en')) return;
    try {
        const response = await load('/translations');
        if (response.ok) messages = await response.json();
    } catch {
        // Source messages keep the interface usable when the request fails.
    }
}

export function _(message) {
    return messages[message] || message;
}
