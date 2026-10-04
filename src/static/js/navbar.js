// // Fetch GitHub stars
// function formatStarCount(count) {
//     if (count >= 1000) {return `${ (count / 1000).toFixed(1) }k`;}

//     return count.toString();
// }

// async function fetchGitHubStars() {
//     try {
//         const res = await fetch('https://gitee.com/api/v5/repos/xihaishen/repoingest');

//         if (!res.ok) {throw new Error(`${res.status} ${res.statusText}`);}
//         const data = await res.json();

//         document.getElementById('github-stars').textContent =
//         formatStarCount(data.stargazers_count);
//     } catch (err) {
//         console.error('Error fetching GitHub stars:', err);
//         const el = document.getElementById('github-stars').parentElement;

//         if (el) {el.style.display = 'none';}
//     }
// }

// // auto-run when script loads
// fetchGitHubStars();

// Switch UI language and record the choice before navigating.
function switchLanguage(code) {
    if (typeof window.track === 'function') {
        window.track('language_switched', { lang: code });
    }

    window.location = '/lang/' + code + '?next=' + encodeURIComponent(window.location.pathname + window.location.search);
}

window.switchLanguage = switchLanguage;
