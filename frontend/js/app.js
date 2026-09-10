/**
 * app.js - 主应用逻辑
 * API 使用相对路径，自动适配启动器动态端口，杜绝端口错配
 */
let scene3d = null;
let chart2d = null;

document.addEventListener('DOMContentLoaded', () => {
    chart2d = new Chart2D('chart-2d');
    setupEventListeners();
    setupUI();
    loadSpectralInfo();
});

function setupEventListeners() {
    document.getElementById('btn-load').addEventListener('click', loadData);
    document.getElementById('btn-apply').addEventListener('click', applyFilter);
    document.getElementById('btn-reset').addEventListener('click', resetFilter);
    const slider = document.getElementById('mag-slider');
    slider.addEventListener('input', () => {
        document.getElementById('mag-value').textContent = parseFloat(slider.value).toFixed(2);
    });
}

/* ===== 抽屉菜单 + 全屏 ===== */
function setupUI() {
    const left  = document.getElementById('left-drawer');
    const right = document.getElementById('right-drawer');
    const bL = document.getElementById('toggle-left');
    const bR = document.getElementById('toggle-right');
    const bF = document.getElementById('toggle-fullscreen');
    const sync = () => {
        bL.textContent = left.classList.contains('open')  ? '✕' : '☰';
        bR.textContent = right.classList.contains('open') ? '✕' : '📊';
    };
    bL.addEventListener('click', () => { left.classList.toggle('open');  sync(); });
    bR.addEventListener('click', () => { right.classList.toggle('open'); sync(); });
    bF.addEventListener('click', () => {
        if (!document.fullscreenElement) {
            const p = document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
            if (p && p.catch) p.catch(() => {});
        } else if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    });
    sync();
}

/* ===== 加载数据 ===== */
async function loadData() {
    showLoading(true);
    const statusEl = document.getElementById('load-status');
    statusEl.textContent = '正在加载 HYG 星表数据...';
    try {
        const res  = await fetch('/api/load', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            statusEl.textContent = `✅ ${data.message}`;
            statusEl.style.color = '#27ae60';
            document.getElementById('filter-panel').style.display = 'block';
            document.getElementById('stats-panel').style.display  = 'block';
            document.getElementById('placeholder-3d').style.display = 'none';
            if (!scene3d) {
                scene3d = new CelestialScene3D('canvas-container');
                window.celestialScene = scene3d;
                scene3d.init();
            }
            await refreshData(6.0);
        } else {
            statusEl.textContent = `❌ ${data.message}`;
            statusEl.style.color = '#e74c3c';
        }
    } catch (err) {
        statusEl.textContent = `❌ 请求失败: ${err.message}`;
        statusEl.style.color = '#e74c3c';
    } finally {
        showLoading(false);
    }
}

/* ===== 刷新数据 ===== */
async function refreshData(maxMag) {
    try {
        const [starsRes, brightRes, statsRes, constRes, topRes] = await Promise.all([
            fetch(`/api/stars?max_mag=${maxMag}`),
            fetch('/api/bright-stars?max_mag=2.5'),
            fetch(`/api/stats?max_mag=${maxMag}`),
            fetch(`/api/constellations?max_mag=${maxMag}`),
            fetch(`/api/top-bright?limit=15&max_mag=${maxMag}`)
        ]);
        const starsData  = await starsRes.json();
        const brightData = await brightRes.json();
        const statsData  = await statsRes.json();
        const constData  = await constRes.json();
        const topData    = await topRes.json();

        if (scene3d) scene3d.updateStars(starsData.stars, brightData.stars);
        chart2d.draw(starsData.stars);
        updateStats(statsData);
        updateConstellationTable(constData.constellations);
        updateBrightStarsTable(topData.stars);
        document.getElementById('filter-info').textContent =
            `当前显示: ${statsData.current_count} / ${statsData.total_stars} 颗星`;
    } catch (err) {
        console.error('刷新数据失败:', err);
    }
}

function applyFilter() {
    refreshData(parseFloat(document.getElementById('mag-slider').value));
}
function resetFilter() {
    document.getElementById('mag-slider').value = 6;
    document.getElementById('mag-value').textContent = '6.00';
    refreshData(6.0);
}

function updateStats(s) {
    document.getElementById('stat-total').textContent       = s.total_stars;
    document.getElementById('stat-current').textContent     = s.current_count;
    document.getElementById('stat-avg-mag').textContent     = s.avg_mag;
    document.getElementById('stat-min-mag').textContent     = s.min_mag;
    document.getElementById('stat-avg-dist').textContent    = `${s.avg_dist_ly} ly`;
    document.getElementById('stat-const-count').textContent = s.constellation_count;
}
function updateConstellationTable(list) {
    document.querySelector('#constellation-table tbody').innerHTML =
        list.slice(0, 30).map(c => `<tr><td>${c.constellation}</td><td>${c.star_count}</td><td>${c.brightest_mag}</td><td>${c.dimmest_mag}</td><td>${c.avg_mag}</td></tr>`).join('');
}
function updateBrightStarsTable(stars) {
    document.querySelector('#bright-stars-table tbody').innerHTML =
        stars.map(s => `<tr><td>${s.name}</td><td>${s.constellation}</td><td>${s.ra_hours}</td><td>${s.dec}</td><td>${s.mag}</td><td>${s.absmag ?? '-'}</td><td>${s.spect}</td><td>${s.dist_ly}</td></tr>`).join('');
}

async function loadSpectralInfo() {
    try {
        const res  = await fetch('/api/spectral-info');
        const data = await res.json();
        document.getElementById('spectral-legend').innerHTML =
            Object.entries(data.info).map(([key, info]) => `
                <div class="spectral-item">
                    <span class="spectral-dot" style="background:${info.color}"></span>
                    <span>${info.name} - ${info.color_name} ${info.temp}</span>
                </div>`).join('');
    } catch (err) {
        console.log('光谱信息API未就绪');
    }
}

function showLoading(show) {
    document.getElementById('loading-overlay').style.display = show ? 'flex' : 'none';
}