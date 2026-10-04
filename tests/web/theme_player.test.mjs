import assert from 'node:assert/strict';
import test from 'node:test';
import { initThemePlayer, formatTime } from '../../web/js/theme_player.js';

function playerFixture(t, options = {}) {
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
            dataset: { themeUrl: `/api/themes/${id}`, themeTitle: `Theme ${id}`, themeYear: '2020',
                themeType: 'Movie', themeServer: 'Plex', themePoster: `/api/themes/${id}/poster`,
                themeItemUrl: `https://app.plex.tv/item/${id}`, playLabel: `Play ${id}`, pauseLabel: `Pause ${id}`,
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
    class Control extends EventTarget {
        attributes = new Map();
        value = '0';
        setAttribute(name, value) { this.attributes.set(name, value); }
        removeAttribute(name) { this.attributes.delete(name); }
        getAttribute(name) { return this.attributes.get(name); }
    }
    const fields = Object.fromEntries(['title', 'link', 'details', 'poster', 'error', 'seek', 'elapsed', 'duration',
        'next', 'previous', 'random', 'shuffle', 'repeat', 'volume'].map(name => [name, new Control()]));
    fields.play = button('widget');
    fields.error.hidden = true;
    const widget = { dataset: { errorLabel: 'Unable to play this theme.', libraryUrl: '/home',
        queueErrorLabel: 'Unable to load themes.', noThemesLabel: 'No installed themes.' },
        querySelector: selector => fields[selector.slice(13, -1)] };
    const root = { dashboard: true, querySelector: selector => ({ '#theme-player': audio,
        '#theme-widget': widget, '#library-search': root.dashboard ? {} : null })[selector],
        querySelectorAll: () => buttons };
    const controller = initThemePlayer(root, { random: () => 0, ...options });
    return { audio, buttons, frames, fields, root, controller, button };
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

test('finishing the last theme returns to play and replay starts at the beginning', async t => {
    const { audio, buttons: [, button] } = playerFixture(t);
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

test('widget shows item metadata, seek position, volume, and poster fallback', async t => {
    const { audio, buttons: [button], fields } = playerFixture(t);
    await button.click();
    assert.equal(fields.title.textContent, 'Theme 1');
    assert.equal(fields.link.href, 'https://app.plex.tv/item/1');
    assert.equal(fields.details.textContent, '2020 · Movie · Plex');
    assert.equal(fields.poster.src, '/api/themes/1/poster');
    fields.poster.dispatchEvent(new Event('load'));
    assert.equal(fields.poster.hidden, false);
    fields.poster.dispatchEvent(new Event('error'));
    assert.equal(fields.poster.hidden, true);
    fields.seek.value = '45';
    fields.seek.dispatchEvent(new Event('input'));
    assert.equal(audio.currentTime, 45);
    assert.equal(fields.elapsed.textContent, '0:45');
    assert.equal(fields.duration.textContent, '1:40');
    fields.volume.value = '0.35';
    fields.volume.dispatchEvent(new Event('input'));
    assert.equal(audio.volume, 0.35);
    await fields.play.click();
    assert.equal(audio.paused, true);
    await fields.play.click();
    assert.equal(audio.currentTime, 45);
});

test('changing workspace pages keeps playing and returning synchronizes new row buttons', async t => {
    const { audio, buttons, root, controller, fields, button } = playerFixture(t);
    await buttons[0].click();
    audio.currentTime = 37;
    root.dashboard = false;
    buttons.splice(0);
    controller.sync();
    assert.equal(audio.paused, false);
    assert.equal(audio.currentTime, 37);
    assert.equal(audio.loads, 1);
    assert.equal(fields.title.textContent, 'Theme 1');
    assert.equal(initThemePlayer(root), controller);
    root.dashboard = true;
    buttons.push(button(1), button(2));
    controller.sync();
    assert.equal(buttons[0].getAttribute('aria-pressed'), 'true');
    assert.equal(progress(buttons[0]), 63);
    await buttons[0].click();
    assert.equal(audio.paused, true);
    assert.equal(audio.loads, 1);
});

test('next and previous retain actual playback history and ended advances the queue', async t => {
    const { audio, buttons, controller } = playerFixture(t);
    await buttons[0].click();
    audio.ended = true;
    audio.paused = true;
    audio.dispatchEvent(new Event('ended'));
    await Promise.resolve();
    assert.equal(audio.src, '/api/themes/2');
    assert.equal(audio.paused, false);
    await controller.previous();
    assert.equal(audio.src, '/api/themes/1');
    await controller.next();
    assert.equal(audio.src, '/api/themes/2');
});

test('shuffle and randomizer avoid repeating items until the queue has been played', async t => {
    const { audio, buttons, button, controller, fields } = playerFixture(t);
    buttons.push(button(3), button(4));
    controller.sync();
    await buttons[0].click();
    fields.shuffle.dispatchEvent(new Event('click'));
    assert.equal(fields.shuffle.getAttribute('aria-pressed'), 'true');
    const heard = new Set([audio.src]);
    for (let index = 0; index < 3; ++index) {
        await controller.next();
        assert.equal(heard.has(audio.src), false);
        heard.add(audio.src);
    }
    assert.equal(heard.size, 4);
    const last = audio.src;
    await controller.surprise();
    assert.notEqual(audio.src, last);
    fields.repeat.dispatchEvent(new Event('click'));
    assert.equal(fields.repeat.getAttribute('aria-pressed'), 'true');
    const repeating = audio.src;
    audio.currentTime = 100;
    audio.ended = true;
    audio.paused = true;
    audio.dispatchEvent(new Event('ended'));
    await Promise.resolve();
    assert.equal(audio.src, repeating);
    assert.equal(audio.currentTime, 0);
    assert.equal(audio.paused, false);
});

test('identical rating keys on different servers remain separate tracks', async t => {
    const { audio, buttons, controller } = playerFixture(t);
    buttons[1].dataset.themeUrl = '/api/servers/other/themes/1';
    controller.sync();
    await buttons[0].click();
    await controller.next();
    assert.equal(audio.src, '/api/servers/other/themes/1');
    assert.equal(buttons[0].getAttribute('aria-pressed'), 'false');
    assert.equal(buttons[1].getAttribute('aria-pressed'), 'true');
});

test('randomizer can load a queue from another page, handle an empty library and retry a failure', async t => {
    let response;
    const load = t.mock.fn(async () => response);
    const { audio, buttons, button, root, fields, controller } = playerFixture(t, { load });
    const savedParser = globalThis.DOMParser;
    t.after(() => { globalThis.DOMParser = savedParser; });
    let remote = [];
    globalThis.DOMParser = class {
        parseFromString() { return { querySelector: () => ({}), querySelectorAll: () => remote }; }
    };
    buttons.splice(0);
    controller.sync();
    root.dashboard = false;
    response = { ok: false };
    await controller.surprise();
    assert.equal(audio.src, undefined);
    assert.equal(fields.error.textContent, 'Unable to load themes.');
    assert.equal(fields.random.disabled, false);
    response = { ok: true, text: async () => 'library' };
    await controller.surprise();
    assert.equal(fields.error.textContent, 'No installed themes.');
    remote = [button(3)];
    await controller.surprise();
    assert.equal(audio.src, '/api/themes/3');
    assert.equal(fields.error.hidden, true);
    assert.equal(load.mock.calls[0].arguments[0], '/home');
});

test('a failed randomizer request cannot overwrite a newer row selection', async t => {
    let reject;
    const { audio, buttons, button, root, fields, controller } = playerFixture(t,
        { load: () => new Promise((resolve, fail) => { reject = fail; }) });
    buttons.splice(0);
    controller.sync();
    root.dashboard = false;
    const pending = controller.surprise();
    buttons.push(button(2));
    root.dashboard = true;
    controller.sync();
    await buttons[0].click();
    reject(new Error('private endpoint'));
    await pending;
    assert.equal(audio.src, '/api/themes/2');
    assert.equal(audio.paused, false);
    assert.equal(fields.error.hidden, true);
});

test('playback errors stay visible after leaving the library and can be retried from the widget', async t => {
    const { audio, buttons, root, fields, controller } = playerFixture(t);
    await buttons[0].click();
    buttons.splice(0);
    root.dashboard = false;
    controller.sync();
    audio.error = { code: 2 };
    audio.dispatchEvent(new Event('error'));
    assert.equal(audio.paused, true);
    assert.equal(fields.error.hidden, false);
    assert.equal(fields.error.textContent, 'Unable to play this theme.');
    await fields.play.click();
    assert.equal(audio.loads, 2);
    assert.equal(fields.error.hidden, true);
    assert.equal(audio.paused, false);
});

test('unknown and invalid durations have safe time labels', () => {
    assert.equal(formatTime(Number.NaN), '0:00');
    assert.equal(formatTime(Number.POSITIVE_INFINITY), '0:00');
    assert.equal(formatTime(-1), '0:00');
    assert.equal(formatTime(61.9), '1:01');
});

test('a stale successful queue load cannot replace a newly refreshed library', async t => {
    let resolve;
    const { audio, buttons, button, root, controller } = playerFixture(t,
        { load: () => new Promise(done => { resolve = done; }) });
    const savedParser = globalThis.DOMParser;
    t.after(() => { globalThis.DOMParser = savedParser; });
    globalThis.DOMParser = class {
        parseFromString() { return { querySelector: () => ({}), querySelectorAll: () => [button(99)] }; }
    };
    buttons.splice(0);
    controller.sync();
    root.dashboard = false;
    const pending = controller.surprise();
    root.dashboard = true;
    buttons.push(button(3), button(4));
    controller.sync();
    await buttons[0].click();
    resolve({ ok: true, text: async () => 'old library' });
    await pending;
    await controller.next();
    assert.equal(audio.src, '/api/themes/4');
});
