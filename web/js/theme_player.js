export function initThemePlayer(root = document) {
    const audio = root.querySelector('#theme-player');
    if (!audio) return;

    let activeButton;
    let playRequest = 0;
    let animation;

    function setPlaying(button, playing) {
        button.querySelector('.theme-play-icon').classList.toggle('d-none', playing);
        button.querySelector('.theme-pause-icon').classList.toggle('d-none', !playing);
        const label = playing ? button.dataset.pauseLabel : button.dataset.playLabel;
        button.setAttribute('aria-label', label);
        button.setAttribute('aria-pressed', String(playing));
        button.title = label;
    }

    function updateProgress() {
        if (!activeButton) return;
        const fraction = Number.isFinite(audio.duration) && audio.duration > 0
            ? Math.min(1, Math.max(0, audio.currentTime / audio.duration)) : 0;
        activeButton.querySelector('.theme-playback-progress').style.strokeDashoffset = String(100 * (1 - fraction));
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
        if (!activeButton) return;
        audio.pause();
        const message = activeButton.closest('td').querySelector('.theme-playback-error');
        message.textContent = activeButton.dataset.errorLabel;
        message.hidden = false;
        activeButton.removeAttribute('aria-busy');
        setPlaying(activeButton, false);
        stopAnimation();
    }

    audio.addEventListener('playing', () => {
        if (!activeButton) return;
        setPlaying(activeButton, true);
        stopAnimation();
        animateProgress();
    });
    audio.addEventListener('pause', () => {
        if (activeButton) setPlaying(activeButton, false);
        stopAnimation();
        updateProgress();
    });
    audio.addEventListener('ended', () => {
        if (activeButton) setPlaying(activeButton, false);
        stopAnimation();
        updateProgress();
    });
    audio.addEventListener('error', showError);
    for (const event of ['timeupdate', 'loadedmetadata', 'durationchange']) {
        audio.addEventListener(event, updateProgress);
    }

    root.querySelectorAll('[data-theme-url]').forEach(button => {
        button.title = button.dataset.playLabel;
        button.addEventListener('click', async () => {
            const ticket = ++playRequest;
            if (button === activeButton && (!audio.paused || button.getAttribute('aria-busy') === 'true')) {
                audio.pause();
                button.removeAttribute('aria-busy');
                return;
            }
            if (activeButton !== button) {
                audio.pause();
                if (activeButton) {
                    setPlaying(activeButton, false);
                    activeButton.removeAttribute('aria-busy');
                    activeButton.querySelector('.theme-playback-progress').style.strokeDashoffset = '100';
                }
                activeButton = button;
                audio.src = button.dataset.themeUrl;
                audio.load();
            }
            if (audio.error) audio.load();
            if (audio.ended) audio.currentTime = 0;
            button.closest('td').querySelector('.theme-playback-error').hidden = true;
            button.setAttribute('aria-busy', 'true');
            try {
                await audio.play();
            } catch {
                // Switching themes or cancelling a pending play request also rejects play().
                if (ticket === playRequest) showError();
            } finally {
                if (ticket === playRequest) button.removeAttribute('aria-busy');
            }
        });
    });
}
