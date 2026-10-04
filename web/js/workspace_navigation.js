let refreshWorkspace;

export function refreshPage() {
    return refreshWorkspace ? refreshWorkspace() : window.location.reload();
}

export function workspaceLink(event, current, paths) {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
        event.shiftKey || event.altKey || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const url = new URL(link.href, current);
    if (url.origin !== new URL(current).origin || !paths.has(url.pathname)) return;
    if (url.pathname === new URL(current).pathname && url.search === new URL(current).search && url.hash) return;
    return url;
}

export function initWorkspaceNavigation({ enter, leave, reportError = () => {} }, root = document, host = window,
    load = fetch, parse = html => new DOMParser().parseFromString(html, 'text/html')) {
    if (!root.querySelector('#theme-widget')) return;
    const paths = new Set([...root.querySelectorAll('[data-workspace-link]')].map(link => new URL(link.href).pathname));
    paths.add('/home');
    let currentUrl = host.location.href;
    let position = host.history.state?.workspacePosition ?? 0;
    let restoring = false;
    let request;
    host.history.replaceState({ ...host.history.state, workspacePosition: position }, '', currentUrl);
    host.history.scrollRestoration = 'manual';

    function canLeave() {
        return root.dispatchEvent(new CustomEvent('themerr:before-navigate', { cancelable: true }));
    }

    function failedNavigation(state) {
        reportError();
        if (state && position !== state.workspacePosition) {
            restoring = true;
            host.history.go(position - state.workspacePosition);
        }
    }

    async function navigate(url, { replace = false, state, approved = false } = {}) {
        if (!approved && !canLeave()) return;
        request?.abort();
        const controller = new AbortController();
        request = controller;
        const main = root.querySelector('#main-content');
        main.setAttribute('aria-busy', 'true');
        try {
            const response = await load(url, { headers: { Accept: 'text/html' }, signal: controller.signal });
            if (controller.signal.aborted) return;
            if (response.status === 401) {
                const requested = new URL(url, currentUrl);
                host.location.assign(`/login?next=${encodeURIComponent(requested.pathname + requested.search)}`);
                return;
            }
            const destination = new URL(response.url || url, currentUrl);
            if (destination.origin === host.location.origin && ['/login', '/setup'].includes(destination.pathname)) {
                host.location.assign(destination.href);
                return;
            }
            if (!response.ok || destination.origin !== host.location.origin || !paths.has(destination.pathname)) {
                failedNavigation(state);
                return;
            }
            const page = parse(await response.text());
            if (controller.signal.aborted) return;
            const content = page.querySelector('#page-content');
            const modals = page.querySelector('#page-modals');
            const breadcrumb = page.querySelector('.workspace-breadcrumb strong');
            const csrf = page.querySelector('meta[name="csrf-token"]');
            if (!page.querySelector('#theme-widget') || !content || !modals || !breadcrumb || !csrf) {
                failedNavigation(state);
                return;
            }
            if (page.documentElement.lang !== root.documentElement.lang) {
                host.location.assign(destination.href);
                return;
            }
            // Reuse the running JavaScript even if a rebuild changes its asset fingerprint.
            // Reloading to fetch a new bundle would discard the mounted audio element.
            page.querySelectorAll('link[rel="stylesheet"]').forEach(link => {
                const href = new URL(link.getAttribute('href'), destination);
                if (href.origin === host.location.origin &&
                    ![...root.querySelectorAll('link[rel="stylesheet"]')].some(style => style.href === href.href)) {
                    const style = root.createElement('link');
                    style.rel = 'stylesheet';
                    style.href = href.href;
                    root.head.append(style);
                }
            });
            leave();
            root.querySelector('#page-content').replaceWith(content);
            root.querySelector('#page-modals').replaceWith(modals);
            root.title = page.title;
            root.querySelector('.workspace-breadcrumb strong').textContent = breadcrumb.textContent;
            const token = csrf.content;
            root.querySelector('meta[name="csrf-token"]').content = token;
            root.querySelectorAll('.logout-form [name="csrf_token"]').forEach(input => { input.value = token; });
            root.querySelectorAll('[data-workspace-link]').forEach(link => {
                if (link.classList.contains('brand')) return;
                const active = [...page.querySelectorAll('[data-workspace-link]')].some(item =>
                    new URL(item.getAttribute('href'), destination).href === link.href &&
                    item.getAttribute('aria-current') === 'page');
                link.classList.toggle('active', active);
                if (active) link.setAttribute('aria-current', 'page');
                else link.removeAttribute('aria-current');
                const dot = link.querySelector('.nav-active-dot');
                if (dot) dot.hidden = !active;
            });
            root.body.classList.remove('sidebar-open');
            root.querySelector('.mobile-menu').setAttribute('aria-expanded', 'false');
            root.dispatchEvent(new Event('themerr:navigation'));
            if (state) position = state.workspacePosition;
            else {
                host.history.replaceState({ ...host.history.state, scroll: [host.scrollX, host.scrollY] }, '', currentUrl);
                if (!replace) ++position;
                host.history[replace ? 'replaceState' : 'pushState']({ workspacePosition: position }, '', destination.href);
            }
            currentUrl = host.location.href;
            await enter();
            if (controller.signal.aborted) return;
            host.scrollTo(...(state?.scroll || [0, 0]));
            main.focus({ preventScroll: true });
            if (new URL(currentUrl).hash) root.getElementById(decodeURIComponent(new URL(currentUrl).hash.slice(1)))?.scrollIntoView();
        } catch {
            if (!controller.signal.aborted) failedNavigation(state);
        } finally {
            if (request === controller) main.removeAttribute('aria-busy');
        }
    }

    root.addEventListener('click', event => {
        const url = workspaceLink(event, host.location.href, paths);
        if (!url) return;
        event.preventDefault();
        void navigate(url.href);
    });
    host.addEventListener('popstate', event => {
        if (restoring) { restoring = false; return; }
        if (!Number.isInteger(event.state?.workspacePosition)) { host.location.reload(); return; }
        const url = new URL(host.location.href);
        const previous = new URL(currentUrl);
        if (url.pathname === previous.pathname && url.search === previous.search) { currentUrl = url.href; return; }
        if (!canLeave()) {
            restoring = true;
            host.history.go(position - event.state.workspacePosition);
            return;
        }
        void navigate(url.href, { state: event.state, approved: true });
    });
    refreshWorkspace = () => navigate(host.location.href, { replace: true });
    return { navigate };
}
