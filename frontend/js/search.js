/**
 * search.js - 恒星搜索栏 + 太阳系天体搜索
 */
(function () {
    const input = document.getElementById('star-search');
    const list  = document.getElementById('search-suggestions');
    const btn   = document.getElementById('search-btn');
    if (!input || !list || !btn) return;

    // 太阳系天体（供搜索，mag 用虚拟值排序）
    const SOLAR_SYSTEM_BODIES = [
        { name: 'Sun',     mag: -30 },
        { name: 'Moon',    mag: -29 },
        { name: 'Mercury', mag: -28 },
        { name: 'Venus',   mag: -27 },
        { name: 'Mars',    mag: -26 },
        { name: 'Jupiter', mag: -25 },
        { name: 'Saturn',  mag: -24 },
        { name: 'Uranus',  mag: -23 },
        { name: 'Neptune', mag: -22 }
    ];

    let current = [];
    let timer = null;

    function namedStars() {
        const scene = window.celestialScene;
        const stars = (scene && scene.starData)
            ? scene.starData.filter(s => s.name && s.name.trim())
            : [];
        // 加入太阳系天体
        const solar = SOLAR_SYSTEM_BODIES.map(b => ({
            name: b.name,
            isSolar: true,
            mag: b.mag,
            constellation: 'Solar System'
        }));
        return stars.concat(solar);
    }

    function renderSuggestions(q) {
        const query = q.trim().toLowerCase();
        list.innerHTML = '';
        current = [];
        if (!query) { list.style.display = 'none'; return; }
        const pool = namedStars();
        if (pool.length === 0) {
            list.innerHTML = '<div class="search-item">请先加载 HYG 星表数据</div>';
            list.style.display = 'block';
            return;
        }
        // 前缀匹配优先，包含匹配次之
        const prefix   = pool.filter(s => s.name.toLowerCase().startsWith(query));
        const contains = pool.filter(s => !s.name.toLowerCase().startsWith(query)
                                        && s.name.toLowerCase().includes(query));
        current = prefix.concat(contains).sort((a, b) => a.mag - b.mag).slice(0, 8);
        if (current.length === 0) { list.style.display = 'none'; return; }
        current.forEach(star => {
            const item = document.createElement('div');
            item.className = 'search-item';
            const meta = star.isSolar
                ? 'Solar System'
                : `${star.constellation} · mag ${star.mag}`;
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
        if (star.isSolar) {
            scene.focusOnSolarBody(star.name);   // 聚焦实时太阳系天体
        } else {
            scene.focusOnStar(star);             // 聚焦恒星
        }
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
    input.addEventListener('keydown', e => { if (e.key === 'Enter') btn.click(); });
    document.addEventListener('click', e => {
        if (!list.contains(e.target) && e.target !== input) list.style.display = 'none';
    });
})();