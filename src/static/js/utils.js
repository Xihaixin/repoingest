// Analytics no-op fallback: overridden by analytics.js when PostHog is enabled.
if (typeof window.track !== 'function') {
    window.track = function () {};
}

// Best-effort extraction of a repository host (never the full URL).
function repoHostFromInput(input) {
    if (!input) {return 'unknown';}

    const value = String(input).trim();
    const ssh = value.match(/^[^@]+@([^:/]+)[:/]/);

    if (ssh) {return ssh[1];}

    if (value.includes('://')) {
        try {return new URL(value).hostname || 'unknown';} catch (e) {return 'unknown';}
    }

    const first = value.split('/')[0];

    if (first.includes('.')) {return first;}

    return 'unknown';
}

// Best-effort extraction of "owner/repo" (no scheme, host, credentials or token).
function repoSlugFromInput(input) {
    if (!input) {return 'unknown';}

    const value = String(input).trim();
    const ssh = value.match(/^[^@]+@[^:/]+:(.+)$/);
    let path;

    if (ssh) {
        path = ssh[1];
    } else if (value.includes('://')) {
        try {path = new URL(value).pathname;} catch (e) {return 'unknown';}
    } else {
        path = value;
    }

    let parts = path.split('/').filter(Boolean);

    if (parts.length >= 3 && parts[0].includes('.')) {
        parts = parts.slice(1);
    }

    if (parts.length && parts[parts.length - 1].endsWith('.git')) {
        parts[parts.length - 1] = parts[parts.length - 1].slice(0, -4);
    }

    return parts.length >= 2 ? parts[0] + '/' + parts[1] : 'unknown';
}

function getFileName(element) {
    const indentSize = 4;
    let path = '';
    let prevIndentLevel = null;

    while (element) {
        const line = element.textContent;
        const index = line.search(/[a-zA-Z0-9_.-]/);
        const indentLevel = index / indentSize;

        // Stop when we reach or go above the top-level directory
        if (indentLevel <= 1) {
            break;
        }

        // Only include directories that are one level above the previous
        if (prevIndentLevel === null || indentLevel === prevIndentLevel - 1) {
            const fileName = line.substring(index).trim();

            path = fileName + path;
            prevIndentLevel = indentLevel;
        }

        element = element.previousElementSibling;
    }

    return path;
}

function toggleFile(element) {
    const patternInput = document.getElementById('pattern');
    const patternFiles = patternInput.value ? patternInput.value.split(',').map((item) => item.trim()) : [];

    const directoryContainer = document.getElementById('directory-structure-container');
    const treeLineElements = Array.from(directoryContainer.children).filter((child) => child.tagName === 'PRE');

    // Skip the first two tree lines (header and repository name)
    if (treeLineElements[0] === element || treeLineElements[1] === element) {
        return;
    }

    element.classList.toggle('line-through');
    element.classList.toggle('text-gray-500');

    const fileName = getFileName(element);
    const fileIndex = patternFiles.indexOf(fileName);

    if (fileIndex !== -1) {
        patternFiles.splice(fileIndex, 1);
    } else {
        patternFiles.push(fileName);
    }

    patternInput.value = patternFiles.join(', ');
}

// Copy functionality
function copyText(className) {
    let textToCopy;

    if (className === 'directory-structure') {
    // For directory structure, get the hidden input value
        const hiddenInput = document.getElementById('directory-structure-content');

        if (!hiddenInput) {return;}
        textToCopy = hiddenInput.value;
    } else {
    // For other elements, get the textarea value
        const textarea = document.querySelector(`.${ className }`);

        if (!textarea) {return;}
        textToCopy = textarea.value;
    }

    const button = document.querySelector(`button[onclick="copyText('${className}')"]`);

    if (!button) {return;}

    // Copy text
    navigator.clipboard.writeText(textToCopy)
        .then(() => {
            // Store original content
            const originalContent = button.innerHTML;

            // Change button content
            button.innerHTML = I18N.t('js.copied');

            // Reset after 1 second
            setTimeout(() => {
                button.innerHTML = originalContent;
            }, 1000);
        })
        .catch((err) => {
            console.error('Failed to copy text:', err);
            const originalContent = button.innerHTML;

            button.innerHTML = I18N.t('js.failedcopy');
            setTimeout(() => {
                button.innerHTML = originalContent;
            }, 1000);
        });
}

// Helper functions for toggling result blocks
function showLoading() {
    document.getElementById('results-loading').style.display = 'block';
    document.getElementById('results-section').style.display = 'none';
    document.getElementById('results-error').style.display = 'none';
}
function showResults() {
    document.getElementById('results-loading').style.display = 'none';
    document.getElementById('results-section').style.display = 'block';
    document.getElementById('results-error').style.display = 'none';
}
function showError(msg) {
    document.getElementById('results-loading').style.display = 'none';
    document.getElementById('results-section').style.display = 'none';
    const errorDiv = document.getElementById('results-error');

    errorDiv.innerHTML = msg;
    errorDiv.style.display = 'block';
}

// Best-effort translation of known backend error messages (kept English
// server-side). Falls back to the original text.
function translateError(text) {
    const t = I18N.t.bind(I18N);
    const rules = [
        [/repository not found/i, t('errors.repo_not_found')],
        [/invalid github token/i, t('errors.invalid_token')]
    ];

    for (const [pattern, replacement] of rules) {
        if (pattern.test(text)) {
            return text.replace(pattern, replacement);
        }
    }

    return text;
}

// ── Cookie helpers & browser identity (uid) ────────────────────────
function getCookie(name) {
    const escaped = name.replace(/([.*+?^=!:${}()|[\]/\\])/g, '\\$1');
    const match = document.cookie.match(new RegExp('(?:^|; )' + escaped + '=([^;]*)'));

    return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name, value, days) {
    const date = new Date();

    date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/; expires=${date.toUTCString()}; SameSite=Lax`;
}

function ensureUid() {
    let uid = getCookie('repoingest_uid');

    if (!uid) {
        uid = (window.crypto && window.crypto.randomUUID)
            ? crypto.randomUUID()
            : ('uid-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2));
        setCookie('repoingest_uid', uid, 365);
    }

    return uid;
}

// ── Job polling / resume ───────────────────────────────────────────
function stopPoll(jobId) {
    const timers = window.pollTimers;

    if (timers && timers[jobId]) {
        clearInterval(timers[jobId]);
        delete timers[jobId];
    }
}

function pollJob(jobId) {
    window.currentJobId = jobId;
    const timers = window.pollTimers || (window.pollTimers = {});
    const submitButton = document.querySelector('#ingestForm button[type="submit"]');

    const poll = () => {
        fetch('/api/jobs/' + jobId)
            .then(async (response) => {
                let data;

                try {
                    data = await response.json();
                } catch {
                    data = {};
                }

                if (!response.ok) {
                    // Job expired / server restarted
                    stopPoll(jobId);
                    setButtonLoadingState(submitButton, false);
                    showError(`<div class='mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700'>${I18N.t('js.job.gone')}</div>`);
                    loadRecentJobs(false);

                    return;
                }

                if (data.status === 'running') {
                    return; // keep polling
                }

                stopPoll(jobId);
                setButtonLoadingState(submitButton, false);

                if (data.status === 'error') {
                    showError(`<div class='mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700'>${translateError(data.error || I18N.t('js.error'))}</div>`);
                } else if (data.result) {
                    handleSuccessfulResponse(data.result);
                }

                loadRecentJobs(false);
            })
            .catch(() => { /* transient network error: keep polling */ });
    };

    stopPoll(jobId);
    timers[jobId] = setInterval(poll, 2000);
    poll();
}

function statusLabel(status) {
    if (status === 'running') {
        return I18N.t('js.job.running');
    }
    if (status === 'error') {
        return I18N.t('js.job.error');
    }

    return I18N.t('js.job.done');
}

function statusColor(status) {
    if (status === 'running') {
        return 'bg-[#ffc480]';
    }
    if (status === 'error') {
        return 'bg-[#FE4A60] text-white';
    }

    return 'bg-[#EBDBB7]';
}

function renderJobList(jobs) {
    const container = document.getElementById('recent-jobs');
    const list = document.getElementById('recent-jobs-list');

    if (!container || !list) {
        return false;
    }

    if (!jobs.length) {
        container.classList.add('hidden');
        return true;
    }

    container.classList.remove('hidden');
    list.innerHTML = '';

    jobs.forEach((job) => {
        const li = document.createElement('li');

        li.className = 'flex items-center justify-between gap-3 border-[3px] border-gray-900 rounded-lg bg-white px-3 py-2 cursor-pointer hover:bg-[#ffc480]/20';
        li.onclick = () => openJob(job);

        const repo = document.createElement('span');

        repo.className = 'text-gray-900 font-medium text-sm truncate';
        repo.textContent = job.repo_url || job.id.slice(0, 12);

        const badge = document.createElement('span');

        badge.className = `text-xs font-bold px-2 py-0.5 rounded-sm border border-gray-900 flex-shrink-0 ${statusColor(job.status)}`;
        badge.textContent = statusLabel(job.status);

        li.appendChild(repo);
        li.appendChild(badge);
        list.appendChild(li);
    });

    return true;
}

function openJob(job) {
    window.currentJobId = job.id;
    const submitButton = document.querySelector('#ingestForm button[type="submit"]');

    if (job.status === 'running') {
        showLoading();
        if (submitButton) {
            setButtonLoadingState(submitButton, true);
        }
        pollJob(job.id);

        return;
    }

    // done / error: fetch the full job and render it
    fetch('/api/jobs/' + job.id)
        .then(async (response) => {
            if (!response.ok) {
                showError(`<div class='mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700'>${I18N.t('js.job.gone')}</div>`);
                return;
            }
            const data = await response.json();

            if (data.status === 'error') {
                showError(`<div class='mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700'>${translateError(data.error || I18N.t('js.error'))}</div>`);
            } else if (data.result) {
                handleSuccessfulResponse(data.result);
            }
        })
        .catch(() => {});
}

function loadRecentJobs(resume = true) {
    ensureUid();
    fetch('/api/jobs')
        .then(async (response) => {
            if (!response.ok) {
                return;
            }
            let data;

            try {
                data = await response.json();
            } catch {
                data = {};
            }

            const jobs = data.jobs || [];

            if (!renderJobList(jobs) || !resume) {
                return;
            }

            if (jobs.length) {
                autoResume(jobs);
            }
        })
        .catch(() => {});
}

function autoResume(jobs) {
    // jobs is newest-first: resume the most recent one
    openJob(jobs[0]);
}

// Helper function to collect form data
function collectFormData(form) {
    const json_data = {};
    const inputText = form.querySelector('[name="input_text"]');
    const token = form.querySelector('[name="token"]');
    const hiddenInput = document.getElementById('max_file_size_kb');
    const patternType = document.getElementById('pattern_type');
    const pattern = document.getElementById('pattern');

    if (inputText) {json_data.input_text = inputText.value;}
    if (token) {json_data.token = token.value;}
    if (hiddenInput) {json_data.max_file_size = hiddenInput.value;}
    if (patternType) {json_data.pattern_type = patternType.value;}
    if (pattern) {json_data.pattern = pattern.value;}

    return json_data;
}

// Helper function to manage button loading state
function setButtonLoadingState(submitButton, isLoading) {
    if (!isLoading) {
        submitButton.disabled = false;
        submitButton.innerHTML = submitButton.getAttribute('data-original-content') || I18N.t('js.submit');
        submitButton.classList.remove('bg-[#ffb14d]');

        return;
    }

    // Store original content if not already stored
    if (!submitButton.getAttribute('data-original-content')) {
        submitButton.setAttribute('data-original-content', submitButton.innerHTML);
    }

    submitButton.disabled = true;
    submitButton.innerHTML = `
        <div class="flex items-center justify-center">
            <svg class="animate-spin h-5 w-5 text-gray-900" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span class="ml-2">${I18N.t('js.processing')}</span>
        </div>
    `;
    submitButton.classList.add('bg-[#ffb14d]');
}

// Helper function to handle successful response
function handleSuccessfulResponse(data) {
    // Show results section
    showResults();

    // Store the digest_url for download functionality
    window.currentDigestUrl = data.digest_url;

    // Set plain text content for summary, tree, and content
    document.getElementById('result-summary').value = data.summary || '';
    document.getElementById('directory-structure-content').value = data.tree || '';
    document.getElementById('result-content').value = data.content || '';

    // Populate directory structure lines as clickable <pre> elements
    const dirPre = document.getElementById('directory-structure-pre');

    if (dirPre && data.tree) {
        dirPre.innerHTML = '';
        data.tree.split('\n').forEach((line) => {
            const pre = document.createElement('pre');

            pre.setAttribute('name', 'tree-line');
            pre.className = 'cursor-pointer hover:line-through hover:text-gray-500';
            pre.textContent = line;
            pre.onclick = function () { toggleFile(this); };
            dirPre.appendChild(pre);
        });
    }

    // Scroll to results
    document.getElementById('results-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function handleSubmit(event, showLoadingSpinner = false) {
    event.preventDefault();
    const form = event.target || document.getElementById('ingestForm');

    if (!form) {return;}

    // Ensure hidden input is updated before collecting form data
    const slider = document.getElementById('file_size');
    const hiddenInput = document.getElementById('max_file_size_kb');

    if (slider && hiddenInput) {
        hiddenInput.value = logSliderToSize(slider.value);
    }

    if (showLoadingSpinner) {
        showLoading();
    }

    const submitButton = form.querySelector('button[type="submit"]');

    if (!submitButton) {return;}

    const json_data = collectFormData(form);

    ensureUid();

    if (showLoadingSpinner) {
        setButtonLoadingState(submitButton, true);
    }

    // Submit the form to /api/ingest as JSON; the endpoint creates a
    // background job and returns 202 + job_id, which we then poll.
    fetch('/api/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(json_data)
    })
        .then(async (response) => {
            let data;

            try {
                data = await response.json();
            } catch {
                data = {};
            }

            if (!response.ok) {
                setButtonLoadingState(submitButton, false);

                // Show all error details if present
                if (Array.isArray(data.detail)) {
                    const details = data.detail.map((d) => `<li>${d.msg || JSON.stringify(d)}</li>`).join('');

                    showError(`<div class='mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700'><b>${I18N.t('js.errors')}</b><ul>${details}</ul></div>`);

                    return;
                }
                // Other errors
                showError(`<div class='mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700'>${translateError(data.error || JSON.stringify(data) || I18N.t('js.error'))}</div>`);

                return;
            }

            // 202: job created -> poll until done/error (keeps loading state)
            if (data.job_id) {
                window.track('ingest_submitted', {
                    job_id: data.job_id,
                    repo_host: repoHostFromInput(json_data.input_text),
                    repo_slug: repoSlugFromInput(json_data.input_text),
                    pattern_type: json_data.pattern_type,
                    has_token: Boolean(json_data.token),
                    max_file_size_kb: Number(json_data.max_file_size) || null
                });
                loadRecentJobs(false);
                pollJob(data.job_id);

                return;
            }

            // Fallback: an unexpected synchronous result
            setButtonLoadingState(submitButton, false);
            handleSuccessfulResponse(data);
        })
        .catch((error) => {
            setButtonLoadingState(submitButton, false);
            showError(`<div class='mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700'>${error}</div>`);
        });
}

function copyFullDigest() {
    const summary = document.getElementById('result-summary').value;
    const directoryStructure = document.getElementById('directory-structure-content').value;
    const filesContent = document.getElementById('result-content').value;
    const fullDigest = `${I18N.t('js.summary')}:\n${summary}\n\n${I18N.t('js.directory')}:\n${directoryStructure}\n\n${I18N.t('js.content')}:\n${filesContent}`;
    const button = document.querySelector('[onclick="copyFullDigest()"]');
    const originalText = button.innerHTML;

    navigator.clipboard.writeText(fullDigest).then(() => {
        button.innerHTML = `
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
            </svg>
            ${I18N.t('js.copied')}
        `;
        window.track('digest_copied', { job_id: window.currentJobId || null });

        setTimeout(() => {
            button.innerHTML = originalText;
        }, 2000);
    })
        .catch((err) => {
            console.error('Failed to copy text: ', err);
        });
}

function downloadFullDigest() {
    const summary = document.getElementById('result-summary').value;
    const directoryStructure = document.getElementById('directory-structure-content').value;
    const filesContent = document.getElementById('result-content').value;
    const fullDigest = `${I18N.t('js.summary')}:\n${summary}\n\n${I18N.t('js.directory')}:\n${directoryStructure}\n\n${I18N.t('js.content')}:\n${filesContent}`;

    // Show feedback on the button
    const button = document.querySelector('[onclick="downloadFullDigest()"]');
    const originalText = button.innerHTML;

    button.innerHTML = `
        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
        </svg>
        ${I18N.t('js.downloading')}
    `;

    // Create a blob and download it
    const blob = new Blob([fullDigest], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = 'digest.txt';
    document.body.appendChild(a);
    a.click();

    // Clean up
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    window.track('digest_downloaded', { job_id: window.currentJobId || null });

    // Update button to show success
    button.innerHTML = `
        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
        </svg>
        ${I18N.t('js.downloaded')}
    `;

    setTimeout(() => {
        button.innerHTML = originalText;
    }, 2000);
}

// Add the logSliderToSize helper function
function logSliderToSize(position) {
    const maxPosition = 500;
    const maxValue = Math.log(102400); // 100 MB

    const value = Math.exp(maxValue * (position / maxPosition)**1.5);

    return Math.round(value);
}

// Move slider initialization to a separate function
function initializeSlider() {
    const slider = document.getElementById('file_size');
    const sizeValue = document.getElementById('size_value');
    const hiddenInput = document.getElementById('max_file_size_kb');

    if (!slider || !sizeValue || !hiddenInput) {return;}

    function updateSlider() {
        const value = logSliderToSize(slider.value);

        sizeValue.textContent = formatSize(value);
        slider.style.backgroundSize = `${(slider.value / slider.max) * 100}% 100%`;
        hiddenInput.value = value; // Set hidden input to KB value
    }

    // Update on slider change
    slider.addEventListener('input', updateSlider);

    // Initialize slider position
    updateSlider();
}

// Add helper function for formatting size
function formatSize(sizeInKB) {
    if (sizeInKB >= 1024) {
        return `${ Math.round(sizeInKB / 1024) }MB`;
    }

    return `${ Math.round(sizeInKB) }kB`;
}

// Add this new function
function setupGlobalEnterHandler() {
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.target.matches('textarea')) {
            const form = document.getElementById('ingestForm');

            if (form) {
                handleSubmit(new Event('submit'), true);
            }
        }
    });
}

// Add to the DOMContentLoaded event listener
document.addEventListener('DOMContentLoaded', () => {
    initializeSlider();
    setupGlobalEnterHandler();
    loadRecentJobs(true);
});


// Make sure these are available globally
window.handleSubmit = handleSubmit;
window.toggleFile = toggleFile;
window.copyText = copyText;
window.copyFullDigest = copyFullDigest;
window.downloadFullDigest = downloadFullDigest;
