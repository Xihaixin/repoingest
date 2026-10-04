/* eslint-disable */
(function () {
    window.track = function () {};

    const cfg = window.POSTHOG_CONFIG;

    if (!cfg || !cfg.api_key || typeof window.posthog === 'undefined') {
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
        disable_session_recording: true,
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
