// search.js - 恒星搜索：键入英文 → 动态建议 → 定位聚焦
(function () {
    const input = document.getElementById('star-search');
    const list  = document.getElementById('search-suggestions');
    const btn   = document.getElementById('search-btn');
    if (!input || !list || !btn) return;

    let current = [];
    let timer = null;

    function namedStars() {
        const scene = window.celestialScene;
        if (!scene || !scene.starData) return [];
        return scene.starData.filter(s => s.name && s.name.trim());
    }

    function renderSuggestions(q) {
        const query = q.trim().toLowerCase();
        list.innerHTML = '';
        current = [];
        if (!query) { list.style.display = 'none'; return; }
        const pool = namedStars();
        if (!pool.length) {
            list.innerHTML = '<div class="search-item">请先加载 HYG 星表数据</div>';
            list.style.display = 'block';
            return;
        }
        const prefix   = pool.filter(s => s.name.toLowerCase().startsWith(query));
        const contains = pool.filter(s => !s.name.toLowerCase().startsWith(query)
                                        && s.name.toLowerCase().includes(query));
        current = prefix.concat(contains).sort((a, b) => a.mag - b.mag).slice(0, 8);
        if (!current.length) { list.style.display = 'none'; return; }
        current.forEach(star => {
            const item = document.createElement('div');
            item.className = 'search-item';
            item.innerHTML = '<span class="s-name">' + star.name + '</span>' +
                             '<span class="s-meta">' + star.constellation + ' · mag ' + star.mag + '</span>';
            item.addEventListener('mousedown', (e) => { e.preventDefault(); choose(star); });
            list.appendChild(item);
        });
        list.style.display = 'block';
    }

    function choose(star) {
        input.value = star.name;
        list.style.display = 'none';
        if (window.celestialScene) window.celestialScene.focusOnStar(star);
    }

    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => renderSuggestions(input.value), 150);
    });
    btn.addEventListener('click', () => {
        const q = input.value.trim().toLowerCase();
        if (!q) return;
        let star = current.find(s => s.name.toLowerCase() === q);
        if (!star) { renderSuggestions(input.value); star = current[0]; }
        if (star) choose(star);
    });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') btn.click(); });
    document.addEventListener('click', (e) => {
        if (!list.contains(e.target) && e.target !== input) list.style.display = 'none';
    });
})();