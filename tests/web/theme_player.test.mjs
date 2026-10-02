import assert from 'node:assert/strict';
import test from 'node:test';
import { initThemePlayer } from '../../web/js/theme_player.js';

function playerFixture(t) {
    const frames = new Map();
    let frameId = 0;
    globalThis.requestAnimationFrame = callback => {
        frames.set(++frameId, callback);
        return frameId;
    };
    globalThis.cancelAnimationFrame = id => frames.delete(id);
    t.after(() => {
        delete globalThis.requestAnimationFrame;
        delete globalThis.cancelAnimationFrame;
    });

    function button(id) {
        const attributes = new Map([['aria-pressed', 'false']]);
        const icon = hidden => ({ classList: {
            hidden, toggle(name, value) { this.hidden = value; },
        } });
        const parts = {
            '.theme-play-icon': icon(false), '.theme-pause-icon': icon(true),
            '.theme-playback-progress': { style: { strokeDashoffset: '100' } },
        };
        const error = { textContent: '', hidden: true };
        return {
            dataset: { themeUrl: `/api/themes/${id}`, playLabel: `Play ${id}`, pauseLabel: `Pause ${id}`,
                errorLabel: 'Unable to play this theme.' },
            parts, error, attributes,
            querySelector: selector => parts[selector],
            closest: () => ({ querySelector: () => error }),
            setAttribute: (name, value) => attributes.set(name, value),
            getAttribute: name => attributes.get(name),
            removeAttribute: name => attributes.delete(name),
            addEventListener(event, callback) { this.click = callback; },
        };
    }

    class Audio extends EventTarget {
        paused = true;
        ended = false;
        duration = 100;
        currentTime = 0;
        loads = 0;

        load() { this.currentTime = 0; this.ended = false; this.error = null; this.loads++; }
        play() {
            if (this.playImpl) return this.playImpl();
            this.paused = false;
            this.ended = false;
            this.dispatchEvent(new Event('playing'));
            return Promise.resolve();
        }
        pause() {
            this.paused = true;
            this.dispatchEvent(new Event('pause'));
        }
    }
    const audio = new Audio();
    const buttons = [button(1), button(2)];
    initThemePlayer({ querySelector: () => audio, querySelectorAll: () => buttons });
    return { audio, buttons, frames };
}

function progress(button) {
    return Number(button.parts['.theme-playback-progress'].style.strokeDashoffset);
}

test('play, pause and resume keep icons, labels and elapsed progress in sync', async t => {
    const { audio, buttons: [button], frames } = playerFixture(t);
    assert.equal(audio.src, undefined); // No audio requests before a user clicks.
    await button.click();
    assert.equal(button.getAttribute('aria-pressed'), 'true');
    assert.equal(button.getAttribute('aria-label'), 'Pause 1');
    assert.equal(button.parts['.theme-play-icon'].classList.hidden, true);
    assert.equal(button.parts['.theme-pause-icon'].classList.hidden, false);
    audio.currentTime = 25;
    audio.dispatchEvent(new Event('timeupdate'));
    assert.equal(progress(button), 75);
    await button.click();
    assert.equal(audio.paused, true);
    assert.equal(button.getAttribute('aria-label'), 'Play 1');
    assert.equal(button.parts['.theme-pause-icon'].classList.hidden, true);
    assert.equal(progress(button), 75);
    assert.equal(frames.size, 0);
    await button.click();
    assert.equal(audio.currentTime, 25);
    assert.equal(audio.loads, 1);
});

test('switching items stops the previous theme and resets its control', async t => {
    const { audio, buttons: [first, second] } = playerFixture(t);
    await first.click();
    audio.currentTime = 60;
    audio.dispatchEvent(new Event('timeupdate'));
    await second.click();
    assert.equal(audio.src, '/api/themes/2');
    assert.equal(first.getAttribute('aria-pressed'), 'false');
    assert.equal(progress(first), 100);
    assert.equal(second.getAttribute('aria-pressed'), 'true');
    assert.equal(audio.currentTime, 0);
});

test('finishing a theme returns to play and replay starts at the beginning', async t => {
    const { audio, buttons: [button] } = playerFixture(t);
    await button.click();
    audio.currentTime = audio.duration;
    audio.ended = true;
    audio.paused = true;
    audio.dispatchEvent(new Event('ended'));
    assert.equal(progress(button), 0);
    assert.equal(button.getAttribute('aria-pressed'), 'false');
    await button.click();
    assert.equal(audio.currentTime, 0);
    assert.equal(button.getAttribute('aria-pressed'), 'true');
});

test('play failure shows a safe message and permits a retry', async t => {
    const { audio, buttons: [button] } = playerFixture(t);
    audio.playImpl = () => Promise.reject(new Error('private URL or token'));
    await button.click();
    assert.equal(button.error.hidden, false);
    assert.equal(button.error.textContent, button.dataset.errorLabel);
    assert.equal(button.getAttribute('aria-pressed'), 'false');
    assert.equal(button.getAttribute('aria-busy'), undefined);
    delete audio.playImpl;
    await button.click();
    assert.equal(button.error.hidden, true);
    assert.equal(button.getAttribute('aria-pressed'), 'true');
    audio.error = { code: 2 }; // A failed network request must be loaded again on retry.
    audio.dispatchEvent(new Event('error'));
    assert.equal(button.error.hidden, false);
    assert.equal(button.getAttribute('aria-pressed'), 'false');
    await button.click();
    assert.equal(audio.loads, 2);
    assert.equal(audio.error, null);
    assert.equal(button.getAttribute('aria-pressed'), 'true');
});

test('cancelling pending playback does not display its rejected promise as an error', async t => {
    const { audio, buttons: [button] } = playerFixture(t);
    let reject;
    audio.playImpl = () => new Promise((resolve, fail) => { reject = fail; });
    const pending = button.click();
    assert.equal(button.getAttribute('aria-busy'), 'true');
    await button.click();
    reject(new Error('Playback aborted'));
    await pending;
    assert.equal(button.error.hidden, true);
    assert.equal(button.getAttribute('aria-busy'), undefined);
    assert.equal(audio.paused, true);
});

test('a stale play rejection cannot change the newly selected item', async t => {
    const { audio, buttons: [first, second] } = playerFixture(t);
    let reject;
    audio.playImpl = () => new Promise((resolve, fail) => { reject = fail; });
    const pending = first.click();
    delete audio.playImpl;
    await second.click();
    reject(new Error('Previous source aborted'));
    await pending;
    assert.equal(second.getAttribute('aria-pressed'), 'true');
    assert.equal(second.error.hidden, true);
    assert.equal(first.error.hidden, true);
});

test('unknown duration and overshooting time never produce invalid progress', async t => {
    const { audio, buttons: [button] } = playerFixture(t);
    audio.duration = Number.NaN;
    await button.click();
    assert.equal(progress(button), 100);
    audio.duration = 100;
    audio.currentTime = 150;
    audio.dispatchEvent(new Event('durationchange'));
    assert.equal(progress(button), 0);
});

test('pages without a theme player need no controls', () => {
    assert.doesNotThrow(() => initThemePlayer({ querySelector: () => null }));
});
