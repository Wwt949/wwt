/* ==========================================================================
   智能律询通 · 前端内核
   状态机 / 路由 / 接口 / 图表 / 浮层。界面渲染见 views.js。
   ========================================================================== */

/* ------------------------------------------------------------------ 基础工具 */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* 极简 Markdown：**加粗** + 换行 */
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');

const api = async (path) => (await fetch(path)).json();
const post = (path, body) => fetch(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
}).then((r) => r.json());

const icon = (id, cls = '') => `<svg class="ic ${cls}"><use href="#${id}"/></svg>`;

function toast(text, ms = 2000) {
  const el = $('#toast');
  el.textContent = text;
  el.classList.add('on');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('on'), ms);
}

const pad2 = (n) => String(n).padStart(2, '0');
function fmtTime(ts) {
  const m = String(ts || '').match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return m ? `${m[4]}:${m[5]}` : '—';
}
function fmtDay(ts) {
  const m = String(ts || '').match(/(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return '—';
  const d = `${m[1]}-${m[2]}-${m[3]}`;
  const today = new Date();
  const t = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`;
  const y = new Date(today.getTime() - 86400000);
  const yd = `${y.getFullYear()}-${pad2(y.getMonth() + 1)}-${pad2(y.getDate())}`;
  if (d === t) return '今天 ' + fmtTime(ts);
  if (d === yd) return '昨天 ' + fmtTime(ts);
  return `${m[2]}-${m[3]} ${fmtTime(ts)}`;
}
const dayOf = (ts) => (String(ts || '').match(/(\d{4}-\d{2}-\d{2})/) || ['', ''])[1];
const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
};

/* --------------------------------------------------------------- 全局状态 */
const S = {
  stack: [{ name: 'home', params: {} }],
  health: null,
  counts: { high: 0, total: 0 },
  chat: {
    sessionId: null,
    messages: [],
    sending: false,
    busy: false,
    trace: null,
    refs: null,
    intro: true,
  },
  wb: {
    items: [],
    filtered: [],
    filters: { category: '', grade: '', time: '' },
    loaded: false,
    loading: false,
  },
  me: { role: '消费者' },
};
const cur = () => S.stack[S.stack.length - 1];

/* --------------------------------------------------------------- 路由 */
const VIEWS = {};      // views.js 注册：name -> render(params) -> {html, after}
const ACTIONS = {};    // views.js 注册：data-act -> handler(el, event)

function on(act, handler) { ACTIONS[act] = handler; }

function go(name, params) {
  S.stack.push({ name, params: params || {} });
  render('fwd');
}
function back() {
  if (S.stack.length > 1) { S.stack.pop(); render('back'); return; }
  // 栈底（工作台 / 我的等以标签页方式进入的界面）没有上一屏，退回首页
  if (cur().name !== 'home') home();
}
function home() { S.stack = [{ name: 'home', params: {} }]; render('back'); }
function root(name, params) { S.stack = [{ name, params: params || {} }]; render(); }

function render(dir) {
  const view = cur();
  const def = VIEWS[view.name];
  if (!def) return;
  const { html, after } = def(view.params);
  const app = $('#app');
  app.innerHTML = html;
  const page = $('.page', app);
  if (page && dir === 'back') page.classList.add('is-back');
  document.body.dataset.screen = view.name;
  if (after) after(params2(view));
  if (S.scrollToRestore != null) { const b = $('.page-body', app); if (b) b.scrollTop = S.scrollToRestore; }
}
const params2 = (view) => view.params;

/* 页面内滚动容器自动滚到底（聊天用） */
function scrollBottom(sel = '.page-body') {
  const b = $(sel);
  if (b) b.scrollTop = b.scrollHeight;
}

/* --------------------------------------------------------------- 事件委托 */
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const fn = ACTIONS[el.dataset.act];
  if (!fn) return;
  e.preventDefault();
  fn(el, e);
});
document.addEventListener('change', (e) => {
  const el = e.target.closest('[data-act-change]');
  if (!el) return;
  const fn = ACTIONS[el.dataset.actChange];
  if (fn) fn(el, e);
});
document.addEventListener('input', (e) => {
  const el = e.target.closest('[data-act-input]');
  if (!el) return;
  const fn = ACTIONS[el.dataset.actInput];
  if (fn) fn(el, e);
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeSheet();
});

/* --------------------------------------------------------------- 底部浮层 */
let sheetTimer = null;
function openSheet(html, opts = {}) {
  const root = $('#sheetRoot');
  clearTimeout(sheetTimer);              // 避免上一次关闭的延时清空打断新浮层
  root.innerHTML = `
    <div class="backdrop" data-act="sheet-close"></div>
    <div class="sheet" role="dialog">${html}</div>`;
  requestAnimationFrame(() => root.classList.add('show'));
  if (opts.after) setTimeout(() => opts.after(root), 60);
}
function closeSheet() {
  const root = $('#sheetRoot');
  if (!root.classList.contains('show')) return;
  root.classList.remove('show');
  clearTimeout(sheetTimer);
  sheetTimer = setTimeout(() => { root.innerHTML = ''; }, 260);
}

/* ==========================================================================
   图表（规范：细笔触 · 圆端数据端 · 单一数据集用单色 · 直接标注 · 悬停提示）
   ========================================================================== */
function ring(viz) {
  const { pct = 0, size = 62, width = 7, warm = false, label = '' } = viz;
  const r = (size - width) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, pct));
  const dash = (c * v) / 100;
  return `
  <svg class="ring${warm ? ' warm' : ''}" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img"
       aria-label="${esc(label || v.toFixed(0) + '%')}">
    <circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${width}"/>
    <circle class="ring-fill" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${width}"
            stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${(c - dash).toFixed(1)}"
            transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="${size / 2}" y="${size / 2 + 4}" text-anchor="middle"
          font-size="13" font-weight="700" fill="var(--ink)" font-family="var(--sans)">${v.toFixed(0)}%</text>
  </svg>`;
}

/* 柱顶 4px 圆角、基线端为直角 */
function barPath(x, y, w, h, radius = 4) {
  const r = Math.max(0, Math.min(radius, w / 2, h));
  return `M${x} ${y + h}V${y + r}a${r} ${r} 0 0 1 ${r} ${-r}h${w - 2 * r}` +
         `a${r} ${r} 0 0 1 ${r} ${r}V${y + h}Z`;
}

function bars(rows) {
  const W = 96, H = 48, base = 32, bw = 12, gap = 14;
  const max = Math.max(1, ...rows.map((r) => r.value));
  let out = `<svg class="bars" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="案件类型分布">`;
  rows.forEach((r, i) => {
    const x = i * (bw + gap);
    const h = r.value ? Math.max(4, (r.value / max) * base) : 0;
    const y = base - h;
    if (h) out += `<path class="bar" d="${barPath(x, y, bw, h)}"/>`;
    out += `<text class="bar-val" x="${x + bw / 2}" y="${h ? y - 3 : base - 3}">${r.value}</text>`;
    out += `<text class="bar-x" x="${x + bw / 2}" y="${base + 11}">${esc(r.label)}</text>`;
    out += `<rect class="bar-hit" x="${x - gap / 2}" y="0" width="${bw + gap}" height="${base}"
             data-tip="${esc(r.full || r.label)} · ${r.value} 条${r.share != null ? ` · 占比 ${r.share}%` : ''}"/>`;
  });
  return out + '</svg>';
}

/* 生成回答所用的模型档位（trace 第 4 步） */
function genModel(trace) {
  const t = (trace || []).find((s) => s.step === 4);
  return t && t.model ? t.model.model_label : '';
}

/* 悬停提示（鼠标环境） */
document.addEventListener('mouseover', (e) => {
  const hit = e.target.closest('[data-tip]');
  if (!hit) return;
  let tip = $('.chart-tip');
  if (!tip) { tip = document.createElement('div'); tip.className = 'chart-tip'; document.body.appendChild(tip); }
  tip.textContent = hit.dataset.tip;
  const r = hit.getBoundingClientRect();
  tip.style.left = `${r.left + r.width / 2}px`;
  tip.style.top = `${r.top}px`;
  tip.classList.add('on');
});
document.addEventListener('mouseout', (e) => {
  if (!e.target.closest('[data-tip]')) return;
  const tip = $('.chart-tip');
  if (tip) tip.classList.remove('on');
});

/* ==========================================================================
   回答解析：把模型的三段式文本拆成结构化卡片
   ========================================================================== */
const SECTION_MAP = [
  { key: 'law', re: /一、\s*法律依据/, title: '法律依据' },
  { key: 'evidence', re: /二、\s*证据(清单|准备)/, title: '证据清单' },
  { key: 'path', re: /三、\s*维权路径/, title: '维权路径' },
  { key: 'case', re: /四、\s*类案参考/, title: '类案参考' },
  { key: 'risk', re: /(⚠️)?\s*风险提示/, title: '风险提示' },
];

function parseAnswer(text) {
  const raw = String(text || '');
  const lines = raw.split('\n');
  const out = { intro: '', sections: [], footnote: '' };
  let section = null;
  let inFoot = false;

  const isHeader = (line) => {
    const t = line.trim().replace(/^\*\*|\*\*$/g, '');
    return SECTION_MAP.find((m) => m.re.test(t));
  };

  lines.forEach((line) => {
    const t = line.trim();
    if (!t) return;
    if (/^-{3,}$/.test(t)) { inFoot = true; return; }
    if (/^_.+_$/.test(t)) { out.footnote = t.replace(/^_|_$/g, ''); return; }
    if (inFoot) return;

    const head = isHeader(line);
    if (head) {
      section = { no: out.sections.length + 1, key: head.key, title: head.title, items: [] };
      out.sections.push(section);
      return;
    }
    if (!section) {
      out.intro += (out.intro ? '\n' : '') + t;
      return;
    }
    // 列表项：去掉编号 / 圆点
    const item = t.replace(/^[·•\-]\s*/, '').replace(/^\d+[.．)]\s*/, '');
    section.items.push(splitLabel(item));
  });
  return out;
}

/* 「标签：正文」或「标签 —— 正文」拆成 {label, text} */
function splitLabel(item) {
  const cut = item.match(/^([^：:]{2,22})[：:]\s*(.+)$/);
  if (cut) return { label: cut[1], text: cut[2] };
  const dash = item.match(/^(.{2,26}?)\s*——\s*(.+)$/);
  if (dash) return { label: dash[1], text: dash[2] };
  const num = item.match(/^(\d+)\.\s*(.+)$/);
  if (num) return { label: '', text: num[2] };
  return { label: '', text: item };
}

/* ==========================================================================
   接口封装
   ========================================================================== */
async function loadHealth() {
  try {
    S.health = await api('/api/health');
  } catch (e) { S.health = null; }
  return S.health;
}
async function refreshCounts() {
  try {
    const res = await api('/api/leads');
    if (res.ok) {
      S.counts.total = res.total;
      S.counts.high = res.counts['高'] || 0;
    }
  } catch (e) { /* 忽略 */ }
}
async function loadLeads(force) {
  if (S.wb.loading) return;
  if (S.wb.loaded && !force) return;
  S.wb.loading = true;
  const q = new URLSearchParams({
    category: S.wb.filters.category,
    grade: S.wb.filters.grade,
  });
  const res = await api('/api/leads?' + q.toString());
  S.wb.loading = false;
  S.wb.items = res.ok ? res.items : [];
  S.wb.loaded = true;
  applyTimeFilter();
  S.counts.total = res.total || 0;
  S.counts.high = (res.counts && res.counts['高']) || 0;
}

function applyTimeFilter() {
  const t = S.wb.filters.time;
  if (!t) { S.wb.filtered = S.wb.items.slice(); return; }
  const today = new Date();
  const limit = t === 'today' ? todayStr()
    : t === '7d' ? dayOf(new Date(today.getTime() - 6 * 86400000).toISOString())
      : dayOf(new Date(today.getTime() - 29 * 86400000).toISOString());
  S.wb.filtered = S.wb.items.filter((l) => dayOf(l.created_at) >= limit);
}

/* 工作台统计：全部由真实线索实时计算 */
function wbStats() {
  const items = S.wb.filtered;
  const today = todayStr();
  const days = new Set(items.map((l) => dayOf(l.created_at)));
  const todayCount = items.filter((l) => dayOf(l.created_at) === today).length;
  const high = items.filter((l) => l.grade === '高').length;
  const cats = ['劳动纠纷', '婚姻家事', '合同纠纷', '民间借贷'];
  const catCount = cats.map((c) => items.filter((l) => (l.tags || []).includes(c)).length);
  const totalCat = catCount.reduce((a, b) => a + b, 0) || 1;
  const topIdx = catCount.indexOf(Math.max(...catCount));
  const top = { name: cats[topIdx], count: catCount[topIdx], share: Math.round((catCount[topIdx] / totalCat) * 100) };
  const weekAgo = dayOf(new Date(Date.now() - 6 * 86400000).toISOString());
  const recent = items.filter((l) => dayOf(l.created_at) >= weekAgo).length;
  return {
    total: items.length, todayCount, high, top, cats, catCount,
    recent, days: days.size,
    todayShare: recent ? Math.round((todayCount / recent) * 100) : 0,
    highShare: items.length ? Math.round((high / items.length) * 100) : 0,
  };
}

/* 地域标签：会话中出现异地城市/省份则判为异地（演示口径） */
const PLACES = ['北京', '上海', '广州', '深圳', '杭州', '南京', '成都', '重庆', '武汉', '西安', '苏州',
  '天津', '长沙', '郑州', '青岛', '宁波', '厦门', '合肥', '福州', '济南', '沈阳', '昆明', '外省', '外地', '省外'];
function regionTag(history) {
  const blob = (history || []).filter((m) => m.role === 'user').map((m) => m.content).join(' ');
  return PLACES.some((p) => blob.includes(p)) ? '异地' : '本地';
}

/* 跟进记录的本地暂存（服务端保存失败时兜底展示） */
const notesKey = (sid) => 'law_note_' + sid;
function getNote(sid) {
  try { return localStorage.getItem(notesKey(sid)) || ''; } catch (e) { return ''; }
}
function setNote(sid, v) {
  try { localStorage.setItem(notesKey(sid), v); } catch (e) { /* 忽略 */ }
}

/* 状态栏时间 */
function tickClock() {
  const d = new Date();
  $('#sbTime').textContent = `${d.getHours()}:${pad2(d.getMinutes())}`;
}

/* 深链：#/home #/chat #/workbench #/customers #/me #/lead/<会话ID> */
function initialStack() {
  const h = (location.hash || '').replace(/^#\/?/, '');
  if (h.startsWith('lead/')) return [{ name: 'home', params: {} }, { name: 'lead', params: { id: decodeURIComponent(h.slice(5)) } }];
  if (['chat', 'workbench', 'customers', 'me'].includes(h)) return [{ name: h, params: {} }];
  return [{ name: 'home', params: {} }];
}

/* 启动 */
(async () => {
  tickClock();
  setInterval(tickClock, 20000);
  S.stack = initialStack();
  await Promise.all([loadHealth(), refreshCounts()]);
  render();
  setTimeout(() => $('#splash').classList.add('gone'), 260);
})();

