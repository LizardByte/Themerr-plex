import { refreshIcons } from './icons.js';

const alertPlaceholder = document.createElement('div');
alertPlaceholder.className = 'container alert_placeholder';
document.body.appendChild(alertPlaceholder);

export function showAlert(message, alertType = 'alert-info', iconName = null, timeout = null) {
    const alert = document.createElement('div');
    alert.className = `alert ${alertType} alert-dismissible fade show`;
    alert.setAttribute('role', 'alert');

    if (iconName !== null) {
        const icon = document.createElement('i');
        icon.dataset.lucide = iconName;
        icon.className = 'me-2';
        alert.appendChild(icon);
    }
    alert.appendChild(document.createTextNode(message));

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn-close';
    close.setAttribute('data-bs-dismiss', 'alert');
    close.setAttribute('aria-label', 'Close');
    alert.appendChild(close);
    alertPlaceholder.appendChild(alert);
    refreshIcons();

    if (timeout !== null) {
        setTimeout(() => alert.remove(), timeout);
    }
}
