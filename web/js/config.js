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
}
