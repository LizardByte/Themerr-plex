const storageKey = 'themerr-color-theme';
const modes = ['auto', 'light', 'dark'];

function themeMode(value) {
    return modes.includes(value) ? value : 'auto';
}

// Run before stylesheets load so the first paint uses the saved preference.
export function initColorTheme(root = document, browser = window) {
    const systemTheme = browser.matchMedia('(prefers-color-scheme: dark)');
    let mode = 'auto';
    try {
        mode = themeMode(browser.localStorage.getItem(storageKey));
    } catch {
        // Storage can be unavailable; the switcher still works for this page.
    }

    function updateControls() {
        root.querySelectorAll('[data-color-theme]').forEach(button => {
            button.setAttribute('aria-label', button.dataset[`${mode}Label`]);
            button.querySelectorAll('[data-theme-icon]').forEach(icon => {
                icon.hidden = icon.dataset.themeIcon !== mode;
            });
        });
    }

    function applyTheme() {
        const automaticTheme = systemTheme.matches ? 'dark' : 'light';
        const theme = mode === 'auto' ? automaticTheme : mode;
        root.documentElement.dataset.bsTheme = theme;
        root.documentElement.dataset.themeMode = mode;
        // Swagger UI's bundled stylesheet uses this class for its dark palette.
        root.documentElement.classList.toggle('dark-mode', theme === 'dark');
        root.querySelector('meta[name="color-scheme"]')?.setAttribute('content', theme);
        updateControls();
    }

    function bindControls() {
        root.querySelectorAll('[data-color-theme]').forEach(button => {
            button.addEventListener('click', () => {
                mode = modes[(modes.indexOf(mode) + 1) % modes.length];
                try {
                    browser.localStorage.setItem(storageKey, mode);
                } catch {
                    // Keep the in-memory preference when persistence is unavailable.
                }
                applyTheme();
            });
        });
        updateControls();
    }

    systemTheme.addEventListener('change', applyTheme);
    browser.addEventListener('storage', event => {
        if (event.key === storageKey || event.key === null) {
            mode = themeMode(event.newValue);
            applyTheme();
        }
    });
    applyTheme();
    if (root.readyState === 'loading') {
        root.addEventListener('DOMContentLoaded', bindControls, { once: true });
    } else {
        bindControls();
    }
}

if (typeof document !== 'undefined' && typeof window !== 'undefined') initColorTheme();
