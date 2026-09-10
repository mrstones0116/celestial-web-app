/**
 * ui.js - 全屏沉浸交互：抽屉菜单弹出/收回 + OS 级全屏切换
 * 抽屉为纯 CSS transform 覆盖层，不改变画布尺寸，无需重绘
 */
(function () {
    const left  = document.getElementById('left-drawer');
    const right = document.getElementById('right-drawer');
    const bL = document.getElementById('toggle-left');
    const bR = document.getElementById('toggle-right');
    const bF = document.getElementById('toggle-fullscreen');

    function sync() {
        if (bL) bL.textContent = (left  && left.classList.contains('open'))  ? '✕' : '☰';
        if (bR) bR.textContent = (right && right.classList.contains('open')) ? '✕' : '📊';
    }

    if (bL && left)  bL.addEventListener('click', () => { left.classList.toggle('open');  sync(); });
    if (bR && right) bR.addEventListener('click', () => { right.classList.toggle('open'); sync(); });

    if (bF) bF.addEventListener('click', () => {
        if (!document.fullscreenElement) {
            const p = document.documentElement.requestFullscreen &&
                      document.documentElement.requestFullscreen();
            if (p && p.catch) p.catch(() => {});
        } else {
            document.exitFullscreen && document.exitFullscreen();
        }
    });

    sync();
})();