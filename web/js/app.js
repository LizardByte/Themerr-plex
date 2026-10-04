import 'bootstrap/dist/css/bootstrap.min.css';
import '@fontsource/open-sans/index.css';
import '@fontsource/open-sans/600.css';
import '@fontsource/open-sans/700.css';
import '../css/custom.css';

import { refreshIcons } from './icons.js';
import { initThemePlayer } from './theme_player.js';
import { initDashboard, initNavigation, initPageControls } from './dashboard.js';
import { initWorkspaceNavigation } from './workspace_navigation.js';
import { initDirectoryPicker } from './directories.js';
import { initSettings } from './config.js';
import { initServers } from './servers.js';
import { initActivity } from './activity.js';
import { initDatabaseStatus } from './database_status.js';
import { initTranslations } from './i18n.js';
import { initLogs } from './logs.js';
import { toast } from './api.js';

refreshIcons();
initNavigation();
await initTranslations();
const player = initThemePlayer();
let page;
async function enterPage() {
    page = new AbortController();
    const signal = page.signal;
    refreshIcons();
    player?.sync();
    initPageControls();
    initDashboard();
    initDirectoryPicker(signal);
    initSettings(signal);
    initServers(signal);
    initActivity(signal);
    initDatabaseStatus(document, undefined, signal);
    initLogs(document, undefined, window, signal);
    const docs = document.querySelector('[data-api-docs-script]');
    if (docs) {
        const module = await import(docs.dataset.apiDocsScript);
        if (!signal.aborted) module.initApiDocs();
    }
}
initWorkspaceNavigation({ enter: enterPage, leave: () => page.abort(),
    reportError: () => toast('Unable to open this page. Please try again.', true) });
await enterPage();
