function submitExample(repoName) {
    const input = document.getElementById('input_text');

    if (input) {
        input.value = repoName;
        input.focus();
    }

    if (typeof window.track === 'function') {
        window.track('example_clicked', {
            repo_host: typeof repoHostFromInput === 'function' ? repoHostFromInput(repoName) : 'unknown'
        });
    }
}

// Make it visible to inline onclick handlers
window.submitExample = submitExample;
