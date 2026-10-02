import 'bootstrap/dist/css/bootstrap.min.css';
import '@fontsource/open-sans/index.css';
import '@fontsource/open-sans/600.css';
import '@fontsource/open-sans/700.css';
import '../css/custom.css';

import { refreshIcons } from './icons.js';
import { initThemePlayer } from './theme_player.js';
import { initDashboard, initNavigation } from './dashboard.js';
import { initDirectoryPicker } from './directories.js';
import { initSettings } from './config.js';
import { initServers } from './servers.js';
import { initActivity } from './activity.js';
import { initDatabaseStatus } from './database_status.js';

refreshIcons();
initNavigation();
initThemePlayer();
initDashboard();
initDirectoryPicker();
initSettings();
initServers();
initActivity();
initDatabaseStatus();
