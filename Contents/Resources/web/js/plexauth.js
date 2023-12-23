// Reference: https://github.com/Tautulli/Tautulli/blob/d019efcf911b4806618761c2da48bab7d04031ec/data/interfaces/default/js/script.js

var p = {
    name: 'Unknown',
    version: 'Unknown',
    os: 'Unknown'
}
if (typeof platform !== 'undefined') {
    p.name = platform.name
    p.version = platform.version
    p.os = platform.os.toString()
}

function getPlexHeaders(clientID) {
    return {
        'Accept': 'application/json',
        'X-Plex-Product': 'Themerr',
        'X-Plex-Version': 'Plex OAuth',
        'X-Plex-Client-Identifier': clientID ? clientID : getLocalStorage('Themerr_ClientID', uuidv4(), false),
        'X-Plex-Platform': p.name,
        'X-Plex-Platform-Version': p.version,
        'X-Plex-Model': 'Plex OAuth',
        'X-Plex-Device': p.os,
        'X-Plex-Device-Name': p.name + ' (Themerr)',
        'X-Plex-Device-Screen-Resolution': window.screen.width + 'x' + window.screen.height,
        'X-Plex-Language': 'en'
    }
}

function encodeData(data) {
    return Object.keys(data).map(function (key) {
        return [key, data[key]].map(encodeURIComponent).join("=")
    }).join("&")
}

var plex_oauth_window = null
const plex_oauth_loader = '<style>' +
    '.login-loader-container {' +
    'font-family: "Open Sans", Arial, sans-serif;' +
    'position: absolute;' +
    'top: 0;' +
    'right: 0;' +
    'bottom: 0;' +
    'left: 0;' +
    '}' +
    '.login-loader-message {' +
    'color: #282A2D;' +
    'text-align: center;' +
    'position: absolute;' +
    'left: 50%;' +
    'top: 25%;' +
    'transform: translate(-50%, -50%);' +
    '}' +
    '.login-loader {' +
    'border: 5px solid #ccc;' +
    '-webkit-animation: spin 1s linear infinite;' +
    'animation: spin 1s linear infinite;' +
    'border-top: 5px solid #282A2D;' +
    'border-radius: 50%;' +
    'width: 50px;' +
    'height: 50px;' +
    'position: relative;' +
    'left: calc(50% - 25px);' +
    '}' +
    '@keyframes spin {' +
    '0% { transform: rotate(0deg); }' +
    '100% { transform: rotate(360deg); }' +
    '}' +
    '</style>' +
    '<div class="login-loader-container">' +
    '<div class="login-loader-message">' +
    '<div class="login-loader"></div>' +
    '<br>' +
    'Redirecting to the Plex login page...' +
    '</div>' +
    '</div>'

function closePlexOAuthWindow() {
    if (plex_oauth_window) {
        plex_oauth_window.close()
    }
}

function getKeyPath(key, path) {
    var key_path = key
    if (path !== false) {
        key_path = `${key_path}_${window.location.pathname}`
    }
    return key_path
}

function setLocalStorage(key, value, path) {
    var key_path = getKeyPath(key, path)
    localStorage.setItem(key_path, value)
}

function getLocalStorage(key, default_value, path) {
    var key_path = getKeyPath(key, path)
    var value = localStorage.getItem(key_path)
    if (value !== null) {
        return value
    } else if (default_value !== undefined) {
        setLocalStorage(key, default_value, path)
        return default_value
    }
}

function uuidv4() {
    return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, function (c) {
        var cryptoObj = window.crypto || window.msCrypto // for IE 11
        return (c ^ cryptoObj.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
    })
}

getPlexOAuthPin = function (clientID) {
    var x_plex_headers = getPlexHeaders(clientID)
    var deferred = $.Deferred()

    $.ajax({
        url: 'https://plex.tv/api/v2/pins?strong=true',
        type: 'POST',
        headers: x_plex_headers,
        success: function (data) {
            deferred.resolve({ pin: data.id, code: data.code })
        },
        error: function () {
            closePlexOAuthWindow()
            deferred.reject()
        }
    })
    return deferred
}

function PopupCenter(url, title, w, h) {
    // Fixes dual-screen position                         Most browsers       Firefox
    var dualScreenLeft = window.screenLeft != undefined ? window.screenLeft : window.screenX
    var dualScreenTop = window.screenTop != undefined ? window.screenTop : window.screenY

    var width = window.innerWidth ? window.innerWidth : document.documentElement.clientWidth ? document.documentElement.clientWidth : screen.width
    var height = window.innerHeight ? window.innerHeight : document.documentElement.clientHeight ? document.documentElement.clientHeight : screen.height

    var left = ((width / 2) - (w / 2)) + dualScreenLeft
    var top = ((height / 2) - (h / 2)) + dualScreenTop
    var newWindow = window.open(url, title, `scrollbars=yes, width=${w}, height=${h}, top=${top}, left=${left}`)

    // Puts focus on the newWindow
    if (window.focus) {
        newWindow.focus()
    }

    return newWindow
}

var polling = null

function PlexOAuth(success, error, pre, clientID) {
    if (typeof pre === "function") {
        pre()
    }
    closePlexOAuthWindow()
    plex_oauth_window = PopupCenter('', 'Plex-OAuth', 600, 700)
    $(plex_oauth_window.document.body).html(plex_oauth_loader)

    getPlexOAuthPin(clientID).then(function (data) {
        var x_plex_headers = getPlexHeaders(clientID)
        const pin = data.pin
        const code = data.code

        var oauth_params = {
            'clientID': x_plex_headers['X-Plex-Client-Identifier'],
            'context[device][product]': x_plex_headers['X-Plex-Product'],
            'context[device][version]': x_plex_headers['X-Plex-Version'],
            'context[device][platform]': x_plex_headers['X-Plex-Platform'],
            'context[device][platformVersion]': x_plex_headers['X-Plex-Platform-Version'],
            'context[device][device]': x_plex_headers['X-Plex-Device'],
            'context[device][deviceName]': x_plex_headers['X-Plex-Device-Name'],
            'context[device][model]': x_plex_headers['X-Plex-Model'],
            'context[device][screenResolution]': x_plex_headers['X-Plex-Device-Screen-Resolution'],
            'context[device][layout]': 'desktop',
            'code': code
        }

        plex_oauth_window.location = `https://app.plex.tv/auth/#!?${encodeData(oauth_params)}`
        polling = pin;

        (function poll() {
            $.ajax({
                url: `https://plex.tv/api/v2/pins/${pin}`,
                type: 'GET',
                headers: x_plex_headers,
                success: function (data) {
                    if (data.authToken) {
                        closePlexOAuthWindow()
                        if (typeof success === "function") {
                            success(data.authToken)
                        }
                    }
                },
                error: function (jqXHR, textStatus, errorThrown) {
                    if (textStatus !== "timeout") {
                        closePlexOAuthWindow()
                        if (typeof error === "function") {
                            error()
                        }
                    }
                },
                complete: function () {
                    if (!plex_oauth_window.closed && polling === pin) {
                        setTimeout(function () { poll() }, 1000)
                    }
                },
                timeout: 10000
            })
        })()
    }, function () {
        closePlexOAuthWindow()
        if (typeof error === "function") {
            error()
        }
    })
}
