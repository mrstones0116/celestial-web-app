/**
 * search.js - 恒星/天体搜索 + 搜索历史(最多10条) + 收藏夹
 */
(function () {
    const input = document.getElementById('star-search');
    const list  = document.getElementById('search-suggestions');
    const btn   = document.getElementById('search-btn');
    if (!input || !list || !btn) return;

    const SOLAR_SYSTEM_BODIES = [
        { name: 'Sun', mag: -30 }, { name: 'Moon', mag: -29 },
        { name: 'Mercury', mag: -28 }, { name: 'Venus', mag: -27 },
        { name: 'Mars', mag: -26 }, { name: 'Jupiter', mag: -25 },
        { name: 'Saturn', mag: -24 }, { name: 'Uranus', mag: -23 },
        { name: 'Neptune', mag: -22 }
    ];

    let current = [];
    let timer = null;

    // ===== 搜索历史（最多 10 条）=====
    function getHistory() {
        try { return JSON.parse(localStorage.getItem('searchHistory') || '[]'); } catch { return []; }
    }
    function addHistory(term) {
        if (!term || !term.trim()) return;
        let h = getHistory().filter(x => x !== term);
        h.unshift(term);
        localStorage.setItem('searchHistory', JSON.stringify(h.slice(0, 10)));
    }

    // ===== 收藏夹 =====
    function getFavorites() {
        try { return JSON.parse(localStorage.getItem('favorites') || '[]'); } catch { return []; }
    }
    window.isFavorite = (name) => getFavorites().some(f => f.name === name);
    window.toggleFavorite = (star) => {
        let favs = getFavorites();
        if (favs.some(f => f.name === star.name)) {
            favs = favs.filter(f => f.name !== star.name);
        } else {
            favs.push({ name: star.name, constellation: star.constellation || '', mag: star.mag });
        }
        localStorage.setItem('favorites', JSON.stringify(favs));
        renderFavorites();
    };

    function renderFavorites() {
        const container = document.getElementById('favorites-list');
        if (!container) return;
        const favs = getFavorites();
        if (favs.length === 0) {
            container.innerHTML = '<div class="fav-empty">暂无收藏</div>';
            return;
        }
        container.innerHTML = favs.map(f => `
            <div class="fav-item" data-name="${f.name}">
                <span class="fav-name">${f.name}</span>
                <span class="fav-meta">${f.constellation || ''}</span>
                <button class="fav-remove" title="移除">✕</button>
            </div>`).join('');
        container.querySelectorAll('.fav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('fav-remove')) {
                    window.toggleFavorite({ name: item.dataset.name });
                    return;
                }
                const scene = window.celestialScene;
                if (!scene) return;
                const star = scene.starData && scene.starData.find(s => s.name === item.dataset.name);
                if (star) {
                    scene.focusOnStar(star);
                    scene._onClickFocusStar(star); // 触发信息面板
                }
            });
        });
    }
    window.renderFavorites = renderFavorites;
    renderFavorites();

    // ===== 搜索逻辑 =====
    function namedStars() {
        const scene = window.celestialScene;
        const stars = (scene && scene.starData) ? scene.starData.filter(s => s.name && s.name.trim()) : [];
        const solar = SOLAR_SYSTEM_BODIES.map(b => ({
            name: b.name, isSolar: true, mag: b.mag, constellation: 'Solar System'
        }));
        return stars.concat(solar);
    }

    function renderSuggestions(q) {
        const query = q.trim().toLowerCase();
        list.innerHTML = '';
        current = [];
        if (!query) {
            // 显示搜索历史
            const history = getHistory();
            if (history.length > 0) {
                list.innerHTML = '<div class="search-history-title">搜索历史</div>' +
                    history.map(h => `<div class="search-item search-history-item" data-term="${h}">
                        <span class="s-name">${h}</span><span class="s-meta">历史</span>
                    </div>`).join('');
                list.querySelectorAll('.search-history-item').forEach(item => {
                    item.addEventListener('mousedown', e => {
                        e.preventDefault();
                        input.value = item.dataset.term;
                        renderSuggestions(item.dataset.term);
                    });
                });
                list.style.display = 'block';
            } else {
                list.style.display = 'none';
            }
            return;
        }
        const pool = namedStars();
        if (pool.length === 0) {
            list.innerHTML = '<div class="search-item">请先加载 HYG 星表数据</div>';
            list.style.display = 'block';
            return;
        }
        const prefix = pool.filter(s => s.name.toLowerCase().startsWith(query));
        const contains = pool.filter(s => !s.name.toLowerCase().startsWith(query) && s.name.toLowerCase().includes(query));
        current = prefix.concat(contains).sort((a, b) => a.mag - b.mag).slice(0, 8);
        if (current.length === 0) { list.style.display = 'none'; return; }
        current.forEach(star => {
            const item = document.createElement('div');
            item.className = 'search-item';
            const meta = star.isSolar ? 'Solar System' : `${star.constellation} · mag ${star.mag}`;
            item.innerHTML = `<span class="s-name">${star.name}</span><span class="s-meta">${meta}</span>`;
            item.addEventListener('mousedown', e => { e.preventDefault(); choose(star); });
            list.appendChild(item);
        });
        list.style.display = 'block';
    }

    function choose(star) {
        input.value = star.name;
        list.style.display = 'none';
        const scene = window.celestialScene;
        if (!scene) return;
        if (star.isSolar && scene.focusOnSolarBody) {
            scene.focusOnSolarBody(star.name);
        } else {
            scene.focusOnStar(star);
            if (scene.showStarInfo) scene.showStarInfo(star);   // ← 弹出与点击一致的介绍栏
        }
    }

    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => renderSuggestions(input.value), 150);
    });
    input.addEventListener('focus', () => renderSuggestions(input.value));
    btn.addEventListener('click', () => {
        const q = input.value.trim().toLowerCase();
        if (!q) return;
        let star = current.find(s => s.name.toLowerCase() === q);
        if (!star) { renderSuggestions(input.value); star = current[0]; }
        if (star) choose(star);
    });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') btn.click(); });
    document.addEventListener('click', e => {
        if (!list.contains(e.target) && e.target !== input) list.style.display = 'none';
    });
})();