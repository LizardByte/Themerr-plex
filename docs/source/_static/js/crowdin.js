(() => {
    function languageUrl(language) {
        const url = new URL(globalThis.location.href);
        if (language && language !== 'en') url.searchParams.set('lng', language);
        else url.searchParams.delete('lng');
        return url.href;
    }

    function repairPickerLinks() {
        // Crowdin generates links from hostname, omitting the application's port.
        document.querySelectorAll('#crowdin-language-picker a[data-lang-code]').forEach(link => {
            link.href = languageUrl(link.dataset.langCode);
        });
        const button = document.querySelector('#crowdin-language-picker .cr-picker-button');
        if (button) button.href = globalThis.location.href;
    }

    document.addEventListener('click', event => {
        const link = event.target.closest?.('#crowdin-language-picker a');
        if (!link) return;
        if (link.classList.contains('cr-picker-button')) {
            event.preventDefault();
            return;
        }
        const language = link.dataset.langCode;
        if (!language) return;
        // Use a normal navigation to the same origin, including its port. This
        // also avoids relying on Crowdin's inline onclick handler under our CSP.
        event.stopImmediatePropagation();
        if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        globalThis.location.assign(languageUrl(language));
    }, true);

    const observer = new MutationObserver(repairPickerLinks);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    repairPickerLinks();
    if (typeof globalThis.initCrowdIn === 'function') globalThis.initCrowdIn('LizardByte-docs', 'dockle');
})();
