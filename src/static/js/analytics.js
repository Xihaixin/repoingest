/* eslint-disable */
(function () {
    window.track = function () {};

    const cfg = window.POSTHOG_CONFIG;

    if (!cfg || !cfg.api_key || typeof window.posthog === 'undefined') {
        return;
    }

    // Honor Do Not Track / Global Privacy Control (basic opt-out).
    const dnt = navigator.doNotTrack === '1'
        || navigator.doNotTrack === 'yes'
        || navigator.globalPrivacyControl === true;

    if (dnt) {
        return;
    }

    let uid = '';

    if (typeof ensureUid === 'function') {
        try {
            uid = ensureUid();
        } catch (e) {
            uid = '';
        }
    }

    const initOptions = {
        api_host: cfg.api_host,
        person_profiles: 'identified_only',
        autocapture: cfg.autocapture !== false,
        disable_session_recording: cfg.session_replay !== true,
        // Strip query strings (e.g. /app?repo=<url>) so repo URLs never leak.
        sanitize_properties: function (properties) {
            ['$current_url', '$referrer'].forEach(function (key) {
                if (typeof properties[key] === 'string' && properties[key].indexOf('?') !== -1) {
                    properties[key] = properties[key].split('?')[0];
                }
            });

            return properties;
        },
    };

    if (uid) {
        initOptions.bootstrap = { distinctID: uid };
    }

    window.posthog.init(cfg.api_key, initOptions);

    window.track = function (event, props) {
        try {
            window.posthog.capture(event, Object.assign({}, props));
        } catch (e) {}
    };
})();
