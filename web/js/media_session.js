export function initMediaSession(audio, controls, host = globalThis) {
    const session = host.navigator?.mediaSession;
    if (!session) return;
    let track;
    let canPrevious;
    let canNext;

    function setAction(action, handler) {
        try {
            session.setActionHandler(action, handler);
        } catch {
            // Browsers can expose the API without supporting every media action.
        }
    }

    function updatePosition() {
        if (!session.setPositionState) return;
        try {
            if (!track || !Number.isFinite(audio.duration) || audio.duration <= 0) {
                session.setPositionState();
                return;
            }
            session.setPositionState({
                duration: audio.duration,
                position: Math.min(audio.duration, Math.max(0, audio.currentTime || 0)),
                playbackRate: Number.isFinite(audio.playbackRate) && audio.playbackRate !== 0 ? audio.playbackRate : 1,
            });
        } catch {
            // Position reporting is optional and must not interrupt playback.
        }
    }

    function updateState() {
        const playback = audio.paused || audio.ended ? 'paused' : 'playing';
        session.playbackState = track ? playback : 'none';
        updatePosition();
    }

    function seek(time, fast = false) {
        if (!track || !Number.isFinite(time) || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
        const position = Math.min(audio.duration, Math.max(0, time));
        if (fast && typeof audio.fastSeek === 'function') audio.fastSeek(position);
        else audio.currentTime = position;
        updatePosition();
    }

    setAction('play', controls.play);
    setAction('pause', controls.pause);
    setAction('stop', () => { controls.pause(); seek(0); });
    setAction('seekbackward', details => seek(audio.currentTime - (details.seekOffset ?? 10)));
    setAction('seekforward', details => seek(audio.currentTime + (details.seekOffset ?? 10)));
    setAction('seekto', details => seek(details.seekTime, details.fastSeek));
    for (const event of ['playing', 'pause', 'ended', 'error']) audio.addEventListener(event, updateState);
    for (const event of ['timeupdate', 'loadedmetadata', 'durationchange', 'ratechange', 'seeked']) {
        audio.addEventListener(event, updatePosition);
    }

    return {
        setTrack(item) {
            track = item;
            if (host.MediaMetadata) {
                session.metadata = new host.MediaMetadata({
                    title: item.title,
                    artist: [item.year, item.type, item.server].filter(Boolean).join(' · '),
                    album: 'Themerr',
                    artwork: item.poster ? [{ src: item.poster }] : [],
                });
            }
            updateState();
        },
        setNavigation(previous, next) {
            if (canPrevious !== previous) {
                canPrevious = previous;
                setAction('previoustrack', previous ? controls.previous : null);
            }
            if (canNext !== next) {
                canNext = next;
                setAction('nexttrack', next ? controls.next : null);
            }
        },
    };
}
