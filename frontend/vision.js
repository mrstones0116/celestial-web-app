/**
 * vision.js - 照片识星前端
 * · 只绑定一次
 * · 点击按钮只打开文件选择框
 * · 选完照片只调用一次 /api/vision/vl-identify
 * · 展示 VL 识别到的星座（中文名 + 英文名 + 缩写 + 置信度 + 理由）
 * · 显示 plate solve 状态和标注图
 */
(function () {
  const API = '/api/vision/vl-identify';

  // 每个星座按顺序分配的强调色（只用于左侧竖条和缩写文字）
  const ITEM_COLORS = [
    '#ff3b3b', '#ff8c00', '#ff00b4', '#b400ff',
    '#ffc800', '#00c8ff', '#00dc64', '#ff6464'
  ];

  let busy = false;
  let modalEl = null;
  let imgEl = null;
  let titleEl = null;
  let scale = 1;
  let currentSrc = '';

  function el(id) { return document.getElementById(id); }

  function clampScale(v) { return Math.max(0.35, Math.min(4.5, v)); }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function setStatus(text, color) {
    const s = el('photo-status');
    if (!s) return;
    s.textContent = text || '';
    s.style.color = color || '#ccc';
  }

  function setBusy(v) {
    busy = v;
    const btn = el('btn-photo-identify');
    if (!btn) return;
    btn.disabled = v;
    btn.style.opacity = v ? '0.6' : '1';
    btn.textContent = v ? '⏳ 正在识别…' : '📷 用 AI 识别夜空照片';
  }

  /* ---------- 弹窗 ---------- */

  function ensureModal() {
    if (modalEl) return;

    const style = document.createElement('style');
    style.textContent = `
      #vision-modal { position: fixed; inset: 0; z-index: 9999; display: none;
        align-items: center; justify-content: center; }
      #vision-modal.open { display: flex; }
      #vision-modal .vm-backdrop { position: absolute; inset: 0;
        background: rgba(0,0,0,.8); }
      #vision-modal .vm-dialog { position: relative; width: min(1100px, 94vw);
        height: min(820px, 92vh); background: #101418; border-radius: 12px;
        display: flex; flex-direction: column; overflow: hidden;
        box-shadow: 0 20px 60px rgba(0,0,0,.5); }
      #vision-modal .vm-toolbar { display: flex; align-items: center; gap: 8px;
        padding: 10px 12px; background: rgba(255,255,255,.06); }
      #vision-modal .vm-title { margin-right: auto; color: #fff; font-size: .9rem; }
      #vision-modal .vm-toolbar button { padding: 6px 10px; border: 0;
        border-radius: 6px; background: #2b3a4a; color: #fff; cursor: pointer; }
      #vision-modal .vm-toolbar button:hover { background: #3d5164; }
      #vision-modal .vm-viewport { flex: 1; overflow: auto; background: #000;
        display: flex; align-items: center; justify-content: center; }
      #vision-modal .vm-viewport img { max-width: 100%; max-height: 100%;
        transform-origin: center center; transition: transform .08s linear;
        user-select: none; -webkit-user-drag: none; }
    `;
    document.head.appendChild(style);

    modalEl = document.createElement('div');
    modalEl.id = 'vision-modal';
    modalEl.innerHTML = `
      <div class="vm-backdrop" data-vm-close="1"></div>
      <div class="vm-dialog">
        <div class="vm-toolbar">
          <span class="vm-title">识别标注图</span>
          <button id="vm-zoom-out" type="button">−</button>
          <button id="vm-zoom-reset" type="button">100%</button>
          <button id="vm-zoom-in" type="button">＋</button>
          <button id="vm-save" type="button">保存</button>
          <button id="vm-close" type="button">关闭</button>
        </div>
        <div class="vm-viewport"><img alt="识别标注图"></div>
      </div>
    `;
    document.body.appendChild(modalEl);

    imgEl = modalEl.querySelector('.vm-viewport img');
    titleEl = modalEl.querySelector('.vm-title');

    modalEl.querySelector('#vm-zoom-in').onclick    = () => { scale = clampScale(scale + 0.18); applyScale(); };
    modalEl.querySelector('#vm-zoom-out').onclick   = () => { scale = clampScale(scale - 0.18); applyScale(); };
    modalEl.querySelector('#vm-zoom-reset').onclick = () => { scale = 1; applyScale(); };
    modalEl.querySelector('#vm-save').onclick       = saveImage;
    modalEl.querySelector('#vm-close').onclick      = closeModal;

    modalEl.addEventListener('click', (e) => {
      if (e.target && e.target.dataset && e.target.dataset.vmClose) closeModal();
    });

    modalEl.querySelector('.vm-viewport').addEventListener('wheel', (e) => {
      e.preventDefault();
      scale = clampScale(scale + (e.deltaY < 0 ? 0.15 : -0.15));
      applyScale();
    }, { passive: false });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModal();
    });
  }

  function applyScale() {
    if (!imgEl) return;
    imgEl.style.transform = 'scale(' + scale + ')';
    const z = modalEl && modalEl.querySelector('#vm-zoom-reset');
    if (z) z.textContent = Math.round(scale * 100) + '%';
  }

  function openModal(src, title) {
    ensureModal();
    currentSrc = src;
    scale = 1;
    imgEl.src = src;
    applyScale();
    if (titleEl) titleEl.textContent = title || '识别标注图';
    modalEl.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    if (!modalEl) return;
    modalEl.classList.remove('open');
    document.body.style.overflow = '';
  }

  function saveImage() {
    if (!currentSrc) return;
    const a = document.createElement('a');
    a.download = 'identified_sky_' + Date.now() + '.png';

    if (currentSrc.startsWith('data:')) {
      a.href = currentSrc;
      document.body.appendChild(a); a.click(); a.remove();
      return;
    }
    fetch(currentSrc).then(r => r.blob()).then(b => {
      const url = URL.createObjectURL(b);
      a.href = url;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
    }).catch(() => window.open(currentSrc, '_blank'));
  }

  /* ---------- 结果渲染（只负责详情，不输出 message） ---------- */

  function renderResult(data, constellations) {
    const box = el('photo-results');
    if (!box) return;

    // 一次性覆盖，避免重复
    box.innerHTML = '';

    if (!data.success) {
      box.innerHTML =
        '<div style="color:#e67e22;font-size:.85rem;line-height:1.5;">' +
        '识别失败，请查看上方状态提示</div>';
      return;
    }

    if (!constellations.length) {
      box.innerHTML =
        '<div style="color:#e6a23c;font-size:.85rem;line-height:1.5;">' +
        '未识别出明确的星座结构</div>';
      return;
    }

    let html = '';

    // ---- 概要 ----
    const summary = data.vl_summary || '';
    const region = data.vl_sky_region || '';
    if (summary) {
      html +=
        '<div style="font-size:.82rem;line-height:1.5;color:#cfe6ff;' +
        'margin:4px 0 6px;">' + escapeHtml(summary) + '</div>';
    }
    if (region) {
      html +=
        '<div style="font-size:.78rem;color:#8ab4ff;margin-bottom:6px;">🗺 ' +
        escapeHtml(region) + '</div>';
    }

    // ---- plate solve 状态 ----
    const ps = data.plate_solve || {};
    if (ps.ok) {
      const extra = ps.scale_px_per_rad
        ? ('，scale≈' + Math.round(ps.scale_px_per_rad) + ' px/rad')
        : '';
      html +=
        '<div style="font-size:.74rem;color:#27ae60;margin-bottom:8px;">' +
        '🎯 天区定位成功（inliers=' + (ps.inliers || 0) + extra + '）</div>';
    } else {
      html +=
        '<div style="font-size:.74rem;color:#e6a23c;margin-bottom:8px;">' +
        '⚠️ 天区定位未成功，已退回标准投影</div>';
    }

    // ---- 星座列表 ----
    html += '<div style="display:flex;flex-direction:column;gap:6px;">';
    constellations.forEach((c, i) => {
      const abbr = c.abbr || '';
      const name = c.name || '';
      const nameCn = c.name_cn || '';
      const conf = Math.round((c.confidence || 0) * 100);
      const color = ITEM_COLORS[i % ITEM_COLORS.length];
      const confColor = conf >= 60 ? '#27ae60'
                       : conf >= 40 ? '#e6a23c' : '#e67e22';
      const low = !!c.low_confidence;

      html +=
        '<div style="border-left:3px solid ' + color + ';' +
        'background:rgba(255,255,255,.03);border-radius:4px;' +
        'padding:6px 8px;">' +
          '<div style="display:flex;align-items:center;gap:6px;' +
          'font-size:.88rem;flex-wrap:wrap;">' +
            '<span style="color:' + color + ';font-weight:bold;' +
            'min-width:34px;">' + escapeHtml(abbr || '?') + '</span>' +
            (nameCn
              ? '<b style="color:#fff;">' + escapeHtml(nameCn) + '</b>'
              : '') +
            (name && name !== nameCn
              ? '<span style="color:#9cb3c9;font-size:.76rem;">' +
                escapeHtml(name) + '</span>'
              : '') +
            '<span style="margin-left:auto;color:' + confColor +
            ';font-size:.75rem;">' + conf + '%</span>' +
            (low
              ? '<span style="color:#e67e22;font-size:.66rem;' +
                'padding:1px 5px;border:1px solid rgba(230,126,34,.45);' +
                'border-radius:8px;">低置信</span>'
              : '') +
          '</div>';

      if (c.reason) {
        html +=
          '<div style="color:#9cb3c9;font-size:.74rem;margin-top:3px;' +
          'line-height:1.45;">' + escapeHtml(c.reason) + '</div>';
      }

      html += '</div>';
    });
    html += '</div>';

    // ---- 标注图按钮 ----
    const hasConstImg = !!data.constellation_annotated_image;
    const hasStarImg  = !!data.star_annotated_image;
    const mainImg     = data.annotated_image || '';

    if (mainImg) {
      html +=
        '<button id="btn-view-annotated" class="primary-btn" ' +
        'style="margin-top:10px;width:100%;" type="button">' +
        '🔍 查看 / 放大星座标注图</button>';
    }

    if (hasStarImg && hasStarImg !== hasConstImg) {
      html +=
        '<button id="btn-view-stars" class="primary-btn" ' +
        'style="margin-top:6px;width:100%;" type="button">' +
        '⭐ 查看星点图</button>';
    }

    box.innerHTML = html;

    // ---- 绑定 ----
    const viewBtn = el('btn-view-annotated');
    if (viewBtn) {
      viewBtn.onclick = () => {
        openModal(
          'data:' + (data.annotated_mime || 'image/png') + ';base64,' +
          data.annotated_image,
          '星座标注图'
        );
      };
    }
    const viewStarsBtn = el('btn-view-stars');
    if (viewStarsBtn) {
      viewStarsBtn.onclick = () => {
        openModal(
          'data:' + (data.annotated_mime || 'image/png') + ';base64,' +
          data.star_annotated_image,
          '星点图'
        );
      };
    }
  }

  /* ---------- 识别流程 ---------- */

  async function identify(file) {
    if (busy) {
      console.warn('[vision] 正在识别中，忽略重复触发');
      return;
    }
    if (!file) return;

    busy = true;
    setBusy(true);
    setStatus('正在识别，请稍候…', '#8ab4ff');

    const preview = el('photo-preview');
    if (preview) {
      if (preview.dataset && preview.dataset.url) {
        URL.revokeObjectURL(preview.dataset.url);
      }
      const url = URL.createObjectURL(file);
      preview.dataset.url = url;
      preview.src = url;
      preview.style.display = 'block';
    }

    const fd = new FormData();
    fd.append('file', file);

    try {
      console.log('[vision] 发送一次识别请求');
      const res = await fetch(API, { method: 'POST', body: fd });
      const data = await res.json();
      console.log('[vision] 后端返回', data);

      const constellations = Array.isArray(data.constellations)
        ? data.constellations
        : [];

      // 渲染详情（不含 message）
      renderResult(data, constellations);

      // 状态只在这里设置一次
      if (data.success && constellations.length) {
        setStatus('识别完成，共 ' + constellations.length + ' 个星座', '#27ae60');

        if (window.celestialScene &&
            typeof window.celestialScene.highlightIdentified === 'function') {
          try {
            window.celestialScene.highlightIdentified(data.matched_stars || []);
          } catch (e) {
            console.warn('[vision] highlightIdentified 调用失败', e);
          }
        }

        if (data.annotated_image) {
          openModal(
            'data:' + (data.annotated_mime || 'image/png') + ';base64,' +
            data.annotated_image,
            '星座标注图'
          );
        }
      } else if (data.success) {
        setStatus(data.message || '未能识别出星座', '#e6a23c');
      } else {
        setStatus(data.message || '识别失败', '#e74c3c');
      }
    } catch (err) {
      console.error('[vision] 请求失败', err);
      setStatus('请求失败: ' + err.message, '#e74c3c');
      renderResult({ success: false }, []);
    } finally {
      busy = false;
      setBusy(false);
      const input = el('photo-upload');
      if (input) input.value = '';
    }
  }

  /* ---------- 绑定（防重复） ---------- */

  document.addEventListener('DOMContentLoaded', () => {
    console.log('[vision] vision.js loaded');

    let btn = el('btn-photo-identify');
    let input = el('photo-upload');

    if (!btn || !input) {
      console.warn('[vision] 未找到 btn-photo-identify / photo-upload');
      return;
    }

    // 克隆替换：确保本次加载的 listener 生效，旧的被丢弃
    const cleanBtn = btn.cloneNode(true);
    btn.parentNode.replaceChild(cleanBtn, btn);
    btn = el('btn-photo-identify');

    const cleanInput = input.cloneNode(true);
    input.parentNode.replaceChild(cleanInput, input);
    input = el('photo-upload');

    btn.addEventListener('click', () => {
      if (busy) return;
      input.click();
    });

    input.addEventListener('change', () => {
      if (busy) return;
      const f = input.files && input.files[0];
      if (!f) return;
      identify(f);
    });
  });
})();