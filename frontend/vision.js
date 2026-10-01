/**
 * vision.js - 照片识星前端
 * · 只绑定一次
 * · 点击按钮只打开文件选择框
 * · 选完照片只调用一次 /api/vision/vl-identify
 * · 展示每个簇的星座信息
 * · 引导用户「是/否」把星图切到照片所在画面
 */
(function () {
  const API = '/api/vision/vl-identify';

  const CLUSTER_COLORS = [
    '#ff3b3b', '#ff8c00', '#ff00b4', '#b400ff',
    '#ffc800', '#00c8ff', '#00dc64', '#ff6464'
  ];

  let busy = false;
  let modalEl = null;
  let imgEl = null;
  let titleEl = null;
  let scale = 1;
  let currentSrc = '';
  let currentObjectUrl = null;

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

  /* ---------- 坐标格式化 ---------- */

  function fmtRa(raHours) {
    let h = ((raHours % 24) + 24) % 24;
    const hh = Math.floor(h);
    const mm = Math.floor((h - hh) * 60);
    const ss = Math.round(((h - hh) * 60 - mm) * 60);
    return String(hh).padStart(2, '0') + 'h ' +
           String(mm).padStart(2, '0') + 'm ' +
           String(ss).padStart(2, '0') + 's';
  }

  function fmtDec(decDeg) {
    const sign = decDeg >= 0 ? '+' : '−';
    const a = Math.abs(decDeg);
    const dd = Math.floor(a);
    const mm = Math.floor((a - dd) * 60);
    return sign + String(dd).padStart(2, '0') + '° ' +
           String(mm).padStart(2, '0') + '′';
  }

  /* ---------- 3D 视角定位适配层 ---------- */

  function aimSceneAtRaDec(raHours, decDeg) {
    const s = window.celestialScene;
    if (!s) {
      return { ok: false, reason: '3D 场景未初始化，请先在左侧加载 HYG 星表数据' };
    }

    const raDeg = (((raHours % 24) + 24) % 24) * 15;
    const dec = Math.max(-89.5, Math.min(89.5, decDeg));

    // 依次尝试常见命名，命中哪个用哪个
    const candidates = [
      'lookAtRaDec', 'setViewRaDec', 'aimAtRaDec',
      'setViewDirection', 'lookAtSky', 'gotoRaDec', 'focusRaDec'
    ];
    for (const name of candidates) {
      if (typeof s[name] === 'function') {
        try {
          s[name](raDeg, dec);
          return { ok: true, method: name };
        } catch (e) {
          console.warn('[vision] ' + name + ' 调用失败', e);
        }
      }
    }

    return {
      ok: false,
      reason: '当前 3D 场景未提供视角定位接口（需要 scene3d 暴露 lookAtRaDec 等）'
    };
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

    modalEl.querySelector('#vm-zoom-in').onclick  = () => { scale = clampScale(scale + 0.18); applyScale(); };
    modalEl.querySelector('#vm-zoom-out').onclick = () => { scale = clampScale(scale - 0.18); applyScale(); };
    modalEl.querySelector('#vm-zoom-reset').onclick = () => { scale = 1; applyScale(); };
    modalEl.querySelector('#vm-save').onclick = saveImage;
    modalEl.querySelector('#vm-close').onclick = closeModal;

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

  /* ---------- 结果渲染 ---------- */

  function renderResult(data) {
    const box = el('photo-results');
    if (!box) return;

    if (!data.success) {
      box.innerHTML =
        '<div style="color:#e67e22;font-size:.85rem;">' +
        escapeHtml(data.message || '识别失败') + '</div>';
      return;
    }

    const clusters = (data.vl_clusters || data.clusters || []);
    const items = clusters
      .map(c => ({ c, vr: (c && c.vl_result) || {} }))
      .filter(x => x.vr && x.vr.success);

    if (!items.length) {
      box.innerHTML =
        '<div style="color:#e67e22;font-size:.85rem;line-height:1.5;">' +
        escapeHtml(data.message || '未能识别出星座') + '</div>';
      return;
    }

    let html = '';

    // ---- 概要 ----
    const summary = data.vl_summary || '';
    const region = data.vl_sky_region || '';
    if (summary) {
      html += '<div style="font-size:.82rem;line-height:1.5;color:#cfe6ff;margin:4px 0 8px;">' +
        escapeHtml(summary) + '</div>';
    }
    if (region) {
      html += '<div style="font-size:.78rem;color:#8ab4ff;margin-bottom:8px;">🗺 ' +
        escapeHtml(region) + '</div>';
    }

    // ---- 每个簇 ----
    html += '<div style="display:flex;flex-direction:column;gap:6px;">';
    for (const { c, vr } of items) {
      const cid = c.id;
      const full = vr.constellation_full || vr.constellation || '';
      const abbr = vr.constellation_abbr || '';
      const conf = Math.round((vr.confidence || 0) * 100);
      const isPos = vr.method === 'position-only';
      const color = CLUSTER_COLORS[cid % CLUSTER_COLORS.length];
      const confColor = conf >= 60 ? '#27ae60' : (conf >= 40 ? '#e6a23c' : '#e67e22');

      html +=
        '<div style="border-left:3px solid ' + color + ';' +
        'background:rgba(255,255,255,.03);border-radius:4px;padding:6px 8px;">' +
          '<div style="display:flex;align-items:center;gap:6px;font-size:.88rem;">' +
            '<span style="color:' + color + ';font-weight:bold;">C' + cid + '</span>' +
            '<b style="color:#fff;">' + escapeHtml(full || abbr || '?') + '</b>' +
            (abbr && full !== abbr
              ? '<span style="color:#888;font-size:.72rem;">' + escapeHtml(abbr) + '</span>'
              : '') +
            '<span style="margin-left:auto;color:' + confColor + ';font-size:.75rem;">' +
              conf + '%</span>' +
            (isPos
              ? '<span style="color:#8ab4ff;font-size:.68rem;padding:1px 5px;' +
                'border:1px solid rgba(90,160,255,.45);border-radius:8px;">位置推断</span>'
              : '') +
          '</div>';

      const shape = vr.shape_description || '';
      if (shape) {
        html += '<div style="color:#aaa;font-size:.74rem;margin-top:3px;">形状：' +
          escapeHtml(shape) + '</div>';
      }
      const reason = vr.reason || '';
      if (reason) {
        html += '<div style="color:#9cb3c9;font-size:.74rem;margin-top:2px;line-height:1.45;">' +
          escapeHtml(reason) + '</div>';
      }
      const edge = vr.edge_note || '';
      if (edge) {
        html += '<div style="color:#7a8a99;font-size:.72rem;margin-top:2px;">边缘：' +
          escapeHtml(edge) + '</div>';
      }
      const alts = vr.alternative || [];
      if (alts.length) {
        const txt = alts.slice(0, 3).map(a =>
          (a.name || a.abbr || '?') + ' ' + Math.round((a.confidence || 0) * 100) + '%'
        ).join('、');
        html += '<div style="color:#7a8a99;font-size:.72rem;margin-top:2px;">备选：' +
          escapeHtml(txt) + '</div>';
      }
      html += '</div>';
    }
    html += '</div>';

    // ---- 视角切换引导 ----
    const focus = data.photo_focus || null;
    if (focus && typeof focus.ra_hours === 'number') {
      const names = items
        .map(x => x.vr.constellation_full || x.vr.constellation_abbr)
        .filter(Boolean);

      html +=
        '<div id="vision-focus-card" style="margin-top:12px;padding:10px;' +
        'border-radius:6px;background:rgba(60,120,200,.12);' +
        'border:1px solid rgba(90,160,255,.35);">' +
          '<div style="font-size:.85rem;color:#cfe6ff;font-weight:bold;margin-bottom:6px;">' +
            '🔄 是否把星图切换到照片所在的画面？' +
          '</div>' +
          '<div style="font-size:.74rem;color:#9cb3c9;line-height:1.55;margin-bottom:8px;">' +
            '视角中心将定位到这 ' + items.length + ' 个星座主星的平均位置：<br>' +
            '<span style="color:#cfe6ff;">' + escapeHtml(names.join('、')) + '</span><br>' +
            '<span style="color:#8ab4ff;">RA ' + fmtRa(focus.ra_hours) +
            '  ·  Dec ' + fmtDec(focus.dec_deg) + '</span>' +
          '</div>' +
          '<div style="display:flex;gap:8px;">' +
            '<button id="vision-focus-yes" type="button" ' +
            'style="flex:1;padding:7px 10px;border:0;border-radius:6px;' +
            'background:#2d6cdf;color:#fff;cursor:pointer;font-weight:bold;">' +
            '✅ 是，切换视角</button>' +
            '<button id="vision-focus-no" type="button" ' +
            'style="flex:1;padding:7px 10px;border:0;border-radius:6px;' +
            'background:#2b3a4a;color:#fff;cursor:pointer;">' +
            '✖ 否，保持当前视角</button>' +
          '</div>' +
          '<div id="vision-focus-msg" style="font-size:.72rem;color:#8ab4ff;' +
          'margin-top:6px;min-height:1em;"></div>' +
        '</div>';
    }

    if (data.annotated_image) {
      html += '<button id="btn-view-annotated" class="primary-btn" ' +
        'style="margin-top:8px;width:100%;" type="button">' +
        '🔍 查看 / 放大标注图</button>';
    }

    box.innerHTML = html;

    // ---- 绑定 ----
    const viewBtn = el('btn-view-annotated');
    if (viewBtn) {
      viewBtn.onclick = () => {
        openModal(
          'data:' + (data.annotated_mime || 'image/png') + ';base64,' + data.annotated_image,
          '识别标注图'
        );
      };
    }
    bindFocusButtons(focus);
  }

  function bindFocusButtons(focus) {
    const yes = el('vision-focus-yes');
    const no  = el('vision-focus-no');
    const msg = el('vision-focus-msg');
    if (!yes || !no) return;

    const say = (t, c) => {
      if (!msg) return;
      msg.textContent = t;
      msg.style.color = c || '#8ab4ff';
    };

    yes.onclick = () => {
      if (!focus || typeof focus.ra_hours !== 'number') {
        say('❌ 缺少天球坐标，无法切换', '#e67e22');
        return;
      }
      const r = aimSceneAtRaDec(focus.ra_hours, focus.dec_deg);
      if (r.ok) {
        say('✅ 已切换到照片画面（RA ' + fmtRa(focus.ra_hours) +
            ' / Dec ' + fmtDec(focus.dec_deg) + '）', '#27ae60');
        yes.disabled = true;
        yes.style.opacity = '.55';
        yes.textContent = '✅ 已切换';
      } else {
        say('❌ ' + r.reason, '#e74c3c');
      }
    };

    no.onclick = () => {
      say('已保持当前视角。你可以随时回来点击「是，切换视角」。', '#888');
    };
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
      const res = await fetch(API, { method: 'POST', body: fd });
      const data = await res.json();
      console.log('[vision] 后端返回', data);

      renderResult(data);

      const items = (data.vl_clusters || [])
        .filter(c => c && c.vl_result && c.vl_result.success);

      if (data.success && items.length) {
        setStatus('识别完成，共 ' + items.length + ' 个星座', '#27ae60');

        if (window.celestialScene && window.celestialScene.highlightIdentified) {
          window.celestialScene.highlightIdentified(data.matched_stars || []);
        }

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

    // 防重复绑定：克隆替换
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