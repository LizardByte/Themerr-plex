function setPlaying(button, playing) {
    if (!button) return;
    button.querySelector('.theme-play-icon').classList.toggle('d-none', playing);
    button.querySelector('.theme-pause-icon').classList.toggle('d-none', !playing);
    const label = playing ? button.dataset.pauseLabel : button.dataset.playLabel;
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-pressed', String(playing));
    button.title = label;
}

export function formatTime(seconds) {
    const value = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}

function trackFromButton(button) {
    return { url: button.dataset.themeUrl, title: button.dataset.themeTitle,
        year: button.dataset.themeYear, type: button.dataset.themeType, server: button.dataset.themeServer,
        poster: button.dataset.themePoster, itemUrl: button.dataset.themeItemUrl,
        playLabel: button.dataset.playLabel, pauseLabel: button.dataset.pauseLabel, errorLabel: button.dataset.errorLabel };
}

function rowError(button) {
    return button.closest('td')?.querySelector('.theme-playback-error');
}

const players = new WeakMap();

export function initThemePlayer(root = document, { load = fetch, random = Math.random } = {}) {
    const audio = root.querySelector('#theme-player');
    if (!audio) return;
    if (players.has(audio)) return players.get(audio);
    const widget = root.querySelector('#theme-widget');
    const field = name => widget?.querySelector(`[data-player-${name}]`);
    const playButton = field('play');
    const error = field('error');
    const seek = field('seek');
    const poster = field('poster');
    const bound = new WeakSet();
    let rows = [];
    let activeRows = [];
    let queue = [];
    let active;
    let pending = false;
    let playRequest = 0;
    let animation;
    let shuffle = false;
    let repeat = false;
    const history = [];
    const visited = new Set();

    function updateProgress() {
        const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
        const fraction = duration ? Math.min(1, Math.max(0, audio.currentTime / duration)) : 0;
        activeRows.forEach(button => {
            button.querySelector('.theme-playback-progress').style.strokeDashoffset = String(100 * (1 - fraction));
        });
        if (seek) {
            seek.disabled = !active || !duration;
            seek.value = String(fraction * 100);
            seek.setAttribute('aria-valuetext', `${formatTime(audio.currentTime)} / ${formatTime(duration)}`);
            field('elapsed').textContent = formatTime(audio.currentTime);
            field('duration').textContent = formatTime(duration);
        }
    }

    function updateControls() {
        const playing = !!active && !audio.paused && !audio.ended;
        activeRows = rows.filter(button => button.dataset.themeUrl === active?.url);
        rows.forEach(button => {
            const selected = button.dataset.themeUrl === active?.url;
            if (!selected) button.querySelector('.theme-playback-progress').style.strokeDashoffset = '100';
            setPlaying(button, selected && playing);
            if (selected && pending) button.setAttribute('aria-busy', 'true');
            else button.removeAttribute('aria-busy');
        });
        setPlaying(playButton, playing);
        if (playButton) {
            playButton.disabled = !active;
            if (pending) playButton.setAttribute('aria-busy', 'true');
            else playButton.removeAttribute('aria-busy');
            field('next').disabled = !active || queue.length < 2;
            field('previous').disabled = !active || (queue.length < 2 && !history.length);
        }
        updateProgress();
    }

    function animateProgress() {
        updateProgress();
        if (!audio.paused && !audio.ended) animation = requestAnimationFrame(animateProgress);
    }

    function stopAnimation() {
        cancelAnimationFrame(animation);
        animation = undefined;
    }

    function showError() {
        if (!active) return;
        pending = false;
        audio.pause();
        if (error) {
            error.textContent = widget.dataset.errorLabel;
            error.hidden = false;
        }
        activeRows.forEach(button => {
            const message = rowError(button);
            if (message) { message.textContent = active.errorLabel; message.hidden = false; }
        });
        stopAnimation();
        updateControls();
    }

    function showMetadata() {
        if (!widget) return;
        field('title').textContent = active.title;
        field('title').title = active.title;
        field('link').href = active.itemUrl;
        field('details').textContent = [active.year, active.type, active.server].filter(Boolean).join(' · ');
        poster.hidden = true;
        if (active.poster) poster.src = active.poster;
        else poster.removeAttribute('src');
    }

    async function play(track = active, { remember = true } = {}) {
        if (!track) return;
        const ticket = ++playRequest;
        const changing = active?.url !== track.url;
        if (changing) {
            pending = false;
            audio.pause();
            if (active && remember) history.push(active);
            active = track;
            visited.add(track.url);
            audio.src = track.url;
            audio.load();
            showMetadata();
        }
        if (audio.error) audio.load();
        if (audio.ended) audio.currentTime = 0;
        if (error) error.hidden = true;
        rows.forEach(button => { const message = rowError(button); if (message) message.hidden = true; });
        pending = true;
        updateControls();
        try {
            await audio.play();
        } catch {
            // Replacing a source or cancelling a pending play also rejects play().
            if (ticket === playRequest) showError();
        } finally {
            if (ticket === playRequest) { pending = false; updateControls(); }
        }
    }

    function pause() {
        ++playRequest;
        pending = false;
        audio.pause();
        updateControls();
    }

    function toggle(track = active) {
        if (track?.url === active?.url && (pending || !audio.paused)) { pause(); return; }
        return play(track);
    }

    async function ensureQueue(ticket) {
        if (queue.length) return true;
        const response = await load(widget.dataset.libraryUrl, { headers: { Accept: 'text/html' } });
        if (!response.ok || response.redirected) throw new Error('Unable to load library');
        const page = new DOMParser().parseFromString(await response.text(), 'text/html');
        if (ticket !== playRequest) return false;
        if (!page.querySelector('#theme-widget')) throw new Error('Invalid library page');
        queue = [...page.querySelectorAll('[data-theme-url]')].map(trackFromButton);
        updateControls();
        if (!queue.length && error) { error.textContent = widget.dataset.noThemesLabel; error.hidden = false; }
        return queue.length > 0;
    }

    function randomTrack() {
        let choices = queue.filter(track => track.url !== active?.url && !visited.has(track.url));
        if (!choices.length) {
            visited.clear();
            choices = queue.filter(track => track.url !== active?.url);
        }
        return choices[Math.floor(random() * choices.length)] || queue[0];
    }

    async function surprise() {
        const ticket = ++playRequest;
        const button = field('random');
        if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
        try {
            if (await ensureQueue(ticket) && ticket === playRequest) await play(randomTrack());
        } catch {
            if (ticket === playRequest && error) { error.textContent = widget.dataset.queueErrorLabel; error.hidden = false; }
        } finally {
            if (button) { button.disabled = false; button.removeAttribute('aria-busy'); }
        }
    }

    function next(automatic = false) {
        if (!queue.length) return;
        const index = queue.findIndex(track => track.url === active?.url);
        if (automatic && !shuffle && index === queue.length - 1) return;
        return play(shuffle ? randomTrack() : queue[(index + 1) % queue.length]);
    }

    function previous() {
        if (history.length) return play(history.pop(), { remember: false });
        const index = queue.findIndex(track => track.url === active?.url);
        if (queue.length) return play(queue[(index - 1 + queue.length) % queue.length], { remember: false });
    }

    function sync() {
        rows = [...root.querySelectorAll('[data-theme-url]')];
        if (root.querySelector('#library-search')) queue = rows.map(trackFromButton);
        // New pages get row listeners; the audio element and its listeners stay mounted.
        rows.forEach(button => {
            if (bound.has(button)) return;
            bound.add(button);
            button.title = button.dataset.playLabel;
            button.addEventListener('click', () => toggle(trackFromButton(button)));
        });
        if (!queue.length && rows.length) queue = rows.map(trackFromButton);
        updateControls();
    }

    audio.addEventListener('playing', () => { updateControls(); stopAnimation(); animateProgress(); });
    audio.addEventListener('pause', () => { stopAnimation(); updateControls(); });
    audio.addEventListener('ended', () => {
        stopAnimation();
        updateControls();
        if (repeat) { audio.currentTime = 0; void play(); }
        else void next(true);
    });
    audio.addEventListener('error', showError);
    for (const event of ['timeupdate', 'loadedmetadata', 'durationchange']) audio.addEventListener(event, updateProgress);
    playButton?.addEventListener('click', () => toggle());
    field('next')?.addEventListener('click', () => next());
    field('previous')?.addEventListener('click', previous);
    field('random')?.addEventListener('click', surprise);
    field('shuffle')?.addEventListener('click', () => {
        shuffle = !shuffle;
        visited.clear();
        if (active) visited.add(active.url);
        field('shuffle').setAttribute('aria-pressed', String(shuffle));
    });
    field('repeat')?.addEventListener('click', () => {
        repeat = !repeat;
        field('repeat').setAttribute('aria-pressed', String(repeat));
    });
    seek?.addEventListener('input', () => {
        if (Number.isFinite(audio.duration) && audio.duration > 0) audio.currentTime = audio.duration * Number(seek.value) / 100;
        updateProgress();
    });
    field('volume')?.addEventListener('input', () => { audio.volume = Number(field('volume').value); });
    poster?.addEventListener('load', () => { poster.hidden = false; });
    poster?.addEventListener('error', () => { poster.hidden = true; });
    if (widget && typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(() => {
            root.body.style.setProperty('--player-height', `${Math.ceil(widget.getBoundingClientRect().height)}px`);
        }).observe(widget);
    }
    const controller = { sync, play, pause, next, previous, surprise };
    players.set(audio, controller);
    sync();
    return controller;
}
