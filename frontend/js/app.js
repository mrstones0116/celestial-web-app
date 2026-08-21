/**
 * 主应用逻辑
 */
const API_BASE = 'http://localhost:8000';

let scene3d = null;
let chart2d = null;

// ===== 页面初始化 =====
document.addEventListener('DOMContentLoaded', () => {
    chart2d = new Chart2D('chart-2d');
    setupEventListeners();
    loadSpectralInfo();
});

// ===== 事件绑定 =====
function setupEventListeners() {
    document.getElementById('btn-load').addEventListener('click', loadData);
    document.getElementById('btn-apply').addEventListener('click', applyFilter);
    document.getElementById('btn-reset').addEventListener('click', resetFilter);

    const slider = document.getElementById('mag-slider');
    slider.addEventListener('input', () => {
        document.getElementById('mag-value').textContent = parseFloat(slider.value).toFixed(2);
    });
}

// ===== 加载数据 =====
async function loadData() {
    showLoading(true);
    const statusEl = document.getElementById('load-status');
    statusEl.textContent = '正在从GitHub下载HYG星表数据...';

    try {
        const res = await fetch(`${API_BASE}/api/load`, { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            statusEl.textContent = `✅ ${data.message}`;
            statusEl.style.color = '#27ae60';

            // 显示控制面板
            document.getElementById('filter-panel').style.display = 'block';
            document.getElementById('stats-panel').style.display = 'block';
            document.getElementById('placeholder-3d').style.display = 'none';

            // 初始化3D场景
            if (!scene3d) {
                scene3d = new CelestialScene3D('canvas-container');
                scene3d.init();
            }

            // 加载星星数据
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

// ===== 刷新数据 =====
async function refreshData(maxMag) {
    try {
        // 并行请求
        const [starsRes, brightRes, statsRes, constRes, topRes] = await Promise.all([
            fetch(`${API_BASE}/api/stars?max_mag=${maxMag}`),
            fetch(`${API_BASE}/api/bright-stars?max_mag=2.5`),
            fetch(`${API_BASE}/api/stats?max_mag=${maxMag}`),
            fetch(`${API_BASE}/api/constellations?max_mag=${maxMag}`),
            fetch(`${API_BASE}/api/top-bright?limit=15&max_mag=${maxMag}`)
        ]);

        const starsData = await starsRes.json();
        const brightData = await brightRes.json();
        const statsData = await statsRes.json();
        const constData = await constRes.json();
        const topData = await topRes.json();

        // 更新3D场景
        if (scene3d) {
            scene3d.updateStars(starsData.stars, brightData.stars);
        }

        // 更新2D图表
        chart2d.draw(starsData.stars);

        // 更新统计
        updateStats(statsData);

        // 更新星座表格
        updateConstellationTable(constData.constellations);

        // 更新最亮星星表格
        updateBrightStarsTable(topData.stars);

        // 更新筛选信息
        document.getElementById('filter-info').textContent =
            `当前显示: ${statsData.current_count} / ${statsData.total_stars} 颗星`;

    } catch (err) {
        console.error('刷新数据失败:', err);
    }
}

// ===== 应用筛选 =====
function applyFilter() {
    const maxMag = parseFloat(document.getElementById('mag-slider').value);
    refreshData(maxMag);
}

// ===== 重置筛选 =====
function resetFilter() {
    document.getElementById('mag-slider').value = 6;
    document.getElementById('mag-value').textContent = '6.00';
    refreshData(6.0);
}

// ===== 更新统计面板 =====
function updateStats(stats) {
    document.getElementById('stat-total').textContent = stats.total_stars;
    document.getElementById('stat-current').textContent = stats.current_count;
    document.getElementById('stat-avg-mag').textContent = stats.avg_mag;
    document.getElementById('stat-min-mag').textContent = stats.min_mag;
    document.getElementById('stat-avg-dist').textContent = `${stats.avg_dist_ly} ly`;
    document.getElementById('stat-const-count').textContent = stats.constellation_count;
}

// ===== 更新星座表格 =====
function updateConstellationTable(constellations) {
    const tbody = document.querySelector('#constellation-table tbody');
    tbody.innerHTML = constellations.slice(0, 30).map(c => `
        <tr>
            <td>${c.constellation}</td>
            <td>${c.star_count}</td>
            <td>${c.brightest_mag}</td>
            <td>${c.dimmest_mag}</td>
            <td>${c.avg_mag}</td>
        </tr>
    `).join('');
}

// ===== 更新最亮星星表格 =====
function updateBrightStarsTable(stars) {
    const tbody = document.querySelector('#bright-stars-table tbody');
    tbody.innerHTML = stars.map(s => `
        <tr>
            <td>${s.name}</td>
            <td>${s.constellation}</td>
            <td>${s.ra_hours}</td>
            <td>${s.dec}</td>
            <td>${s.mag}</td>
            <td>${s.absmag ?? '-'}</td>
            <td>${s.spect}</td>
            <td>${s.dist_ly}</td>
        </tr>
    `).join('');
}

// ===== 加载光谱信息 =====
async function loadSpectralInfo() {
    try {
        const res = await fetch(`${API_BASE}/api/spectral-info`);
        const data = await res.json();

        const legend = document.getElementById('spectral-legend');
        legend.innerHTML = Object.entries(data.info).map(([key, info]) => `
            <div class="spectral-item">
                <span class="spectral-dot" style="background:${info.color}"></span>
                <span>${info.name} - ${info.color_name} ${info.temp}</span>
            </div>
        `).join('');
    } catch (err) {
        // API未启动时使用默认值
        console.log('光谱信息API未就绪，使用默认值');
    }
}

// ===== 加载遮罩 =====
function showLoading(show) {
    document.getElementById('loading-overlay').style.display = show ? 'flex' : 'none';
}