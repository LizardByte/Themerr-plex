import { api } from './api.js';
import { refreshIcons } from './icons.js';

export function initActivity() {
    const list = document.getElementById('job-list');
    if (!list) return;
    let timer;
    let active = true;
    window.addEventListener('pagehide', () => { active = false; clearTimeout(timer); });
    async function update() {
        try {
            const result = await api('/api/tasks', { method: 'GET' });
            document.getElementById('queue-size').textContent = result.queue_size;
            if (result.jobs.length) {
                list.replaceChildren();
                result.jobs.forEach(job => {
                    const row = document.createElement('div');
                    row.className = 'job-row';
                    const symbol = document.createElement('span');
                    symbol.className = 'job-symbol';
                    const icon = document.createElement('i');
                    icon.dataset.lucide = job.status === 'running' ? 'loader-circle' :
                        job.status === 'finished' ? 'circle-check' : 'circle-alert';
                    symbol.append(icon);
                    const info = document.createElement('div');
                    const title = document.createElement('strong');
                    title.textContent = job.name;
                    const time = document.createElement('time');
                    time.dateTime = job.started;
                    time.textContent = new Date(job.started).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
                    info.append(title, time);
                    const badge = document.createElement('span');
                    badge.className = `status-badge ${job.status === 'finished' ? 'success' : job.status === 'failed' ? 'warning' : 'pending'}`;
                    badge.textContent = job.status[0].toUpperCase() + job.status.slice(1);
                    const duration = document.createElement('small');
                    duration.textContent = job.duration === null ? 'In progress' : `${job.duration}s`;
                    row.append(symbol, info, badge, duration);
                    list.append(row);
                });
                refreshIcons();
            }
        } catch {
            // Keep the last useful task snapshot during a temporary connection failure.
        } finally {
            if (active) timer = setTimeout(update, 5000);
        }
    }
    timer = setTimeout(update, 3000);
}
