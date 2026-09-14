/**
 * vision.js - 照片识星前端（防重复调用版）
 *
 * · 只绑定一次
 * · 点击按钮只打开文件选择框
 * · 选完照片只调用一次 /api/vision/vl-identify
 * · 等后端最终结果返回后才弹窗
 */
(function () {
  const API = '/api/vision/vl-identify';

  let busy = false;
  let modalEl = null;
  let imgEl = null;
  let titleEl = null;
  let scale = 1;
  let currentSrc = '';
  let currentObjectUrl = null;

  function el(id) {
    return document.getElementById(id);
  }

  function clampScale(v) {
    return Math.max(0.35, Math.min(4.5, v));
  }

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
    btn.textContent = v
      ? '⏳ 正在识别…'
      : '📷 用 AI 识别夜空照片';
  }

  /* ---------- 弹窗 ---------- */

  function ensureModal() {
    if (modalEl) return;

    const style = document.createElement('style');
    style.textContent = `
      #vision-modal {
        position: fixed;
        inset: 0;
        z-index: 9999;
        display: none;
        align-items: center;
        justify-content: center;
      }

      #vision-modal.open {
        display: flex;
      }

      #vision-modal .vm-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(0,0,0,.8);
      }

      #vision-modal .vm-dialog {
        position: relative;
        width: min(1100px, 94vw);
        height: min(820px, 92vh);
        background: #101418;
        border-radius: 12px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        box-shadow: 0 20px 60px rgba(0,0,0,.5);
      }

      #vision-modal .vm-toolbar {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 12px;
        background: rgba(255,255,255,.06);
      }

      #vision-modal .vm-title {
        margin-right: auto;
        color: #fff;
        font-size: .9rem;
      }

      #vision-modal .vm-toolbar button {
        padding: 6px 10px;
        border: 0;
        border-radius: 6px;
        background: #2b3a4a;
        color: #fff;
        cursor: pointer;
      }

      #vision-modal .vm-toolbar button:hover {
        background: #3d5164;
      }

      #vision-modal .vm-viewport {
        flex: 1;
        overflow: auto;
        background: #000;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      #vision-modal .vm-viewport img {
        max-width: 100%;
        max-height: 100%;
        transform-origin: center center;
        transition: transform .08s linear;
        user-select: none;
        -webkit-user-drag: none;
      }
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
        <div class="vm-viewport">
          <img alt="识别标注图">
        </div>
      </div>
    `;
    document.body.appendChild(modalEl);

    imgEl = modalEl.querySelector('.vm-viewport img');
    titleEl = modalEl.querySelector('.vm-title');

    modalEl.querySelector('#vm-zoom-in').onclick = () => {
      scale = clampScale(scale + 0.18);
      applyScale();
    };

    modalEl.querySelector('#vm-zoom-out').onclick = () => {
      scale = clampScale(scale - 0.18);
      applyScale();
    };

    modalEl.querySelector('#vm-zoom-reset').onclick = () => {
      scale = 1;
      applyScale();
    };

    modalEl.querySelector('#vm-save').onclick = saveImage;
    modalEl.querySelector('#vm-close').onclick = closeModal;

    modalEl.addEventListener('click', (e) => {
      if (e.target && e.target.dataset && e.target.dataset.vmClose) {
        closeModal();
      }
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
      document.body.appendChild(a);
      a.click();
      a.remove();
      return;
    }

    fetch(currentSrc)
      .then(r => r.blob())
      .then(b => {
        const url = URL.createObjectURL(b);
        a.href = url;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 3000);
      })
      .catch(() => window.open(currentSrc, '_blank'));
  }

  /* ---------- 结果渲染 ---------- */

  function renderResult(data) {
    const box = el('photo-results');
    if (!box) return;

    if (!data.success) {
      box.innerHTML =
        '<div style="color:#e67e22;font-size:.85rem;">' +
        escapeHtml(data.message || '识别失败') +
        '</div>';
      return;
    }

    const list = data.vl_constellations || [];

    if (!data.vl_visible || !list.length) {
      box.innerHTML =
        '<div style="color:#e67e22;font-size:.85rem;line-height:1.5;">' +
        escapeHtml(data.message || '未能识别出星座') +
        (data.vl_note ? '<br>' + escapeHtml(data.vl_note) : '') +
        '</div>';
      return;
    }

    let html = '';

    const season = data.vl_season_zh || data.estimated_season || '';
    if (season) {
      html += '<div style="color:#8ab4ff;font-size:.85rem;margin:4px 0;">推测季节：' +
        escapeHtml(season) + '</div>';
    }

    if (data.image_description) {
      html += '<div style="color:#999;font-size:.8rem;margin-bottom:6px;">' +
        escapeHtml(data.image_description) + '</div>';
    }

    html += '<ul style="list-style:none;margin:0;padding:0;">';

    for (const c of list) {
      const starNames = (c.skeleton_stars || c.matched_stars || [])
        .map(s => s.display_name || s.name)
        .filter(Boolean)
        .join('、');

      html +=
        '<li style="border-top:1px solid rgba(255,255,255,.08);padding:6px 0;">' +
          '<div style="display:flex;gap:8px;align-items:center;font-size:.9rem;color:#fff;">' +
            '<b>' + escapeHtml(c.full || c.abbr) + '</b>' +
            '<span style="color:#27ae60;font-size:.75rem;">' +
              Math.round((c.confidence || 0) * 100) + '%' +
            '</span>' +
            '<span style="color:#888;font-size:.75rem;">' +
              escapeHtml(c.position || '') +
            '</span>' +
          '</div>' +
          (starNames
            ? '<div style="color:#aaa;font-size:.78rem;margin-top:2px;">骨架星：' +
              escapeHtml(starNames) +
              '</div>'
            : '') +
        '</li>';
    }

    html += '</ul>';

    if (data.annotated_image) {
      html +=
        '<button id="btn-view-annotated" class="primary-btn" ' +
        'style="margin-top:8px;" type="button">' +
        '查看 / 放大标注图' +
        '</button>';
    }

    box.innerHTML = html;

    const viewBtn = el('btn-view-annotated');
    if (viewBtn) {
      viewBtn.onclick = () => {
        openModal(
          'data:' + (data.annotated_mime || 'image/png') + ';base64,' + data.annotated_image,
          '识别标注图'
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

    if (currentObjectUrl) {
      URL.revokeObjectURL(currentObjectUrl);
      currentObjectUrl = null;
    }

    currentObjectUrl = URL.createObjectURL(file);

    const preview = el('photo-preview');
    if (preview) {
      preview.src = currentObjectUrl;
      preview.style.display = 'block';
    }

    const fd = new FormData();
    fd.append('file', file);

    try {
      console.log('[vision] 发送一次识别请求');

      const res = await fetch(API, {
        method: 'POST',
        body: fd
      });

      const data = await res.json();

      console.log('[vision] 后端返回', data);

      renderResult(data);

      const list = data.vl_constellations || [];

      if (data.success && data.vl_visible && list.length) {
        setStatus('识别完成', '#27ae60');

        if (window.celestialScene && window.celestialScene.highlightIdentified) {
          window.celestialScene.highlightIdentified(data.matched_stars || []);
        }

        // 重点：等最终结果返回后才弹窗
        if (data.annotated_image) {
          openModal(
            'data:' + (data.annotated_mime || 'image/png') + ';base64,' + data.annotated_image,
            '识别标注图'
          );
        }
      } else {
        setStatus(data.message || '未能识别', '#e67e22');
      }
    } catch (err) {
      console.error('[vision] 请求失败', err);
      setStatus('请求失败: ' + err.message, '#e74c3c');
    } finally {
      busy = false;
      setBusy(false);

      const input = el('photo-upload');
      if (input) input.value = '';
    }
  }

  /* ---------- 绑定 ---------- */

  document.addEventListener('DOMContentLoaded', () => {
    console.log('[vision] vision.js loaded');

    let btn = el('btn-photo-identify');
    let input = el('photo-upload');

    if (!btn || !input) {
      console.warn('[vision] 未找到 btn-photo-identify / photo-upload');
      return;
    }

    // 清除可能存在的旧监听器：克隆节点替换
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