/* ==========================================================================
   智能律询通 · 界面视图
   首页 / 法律咨询 / 客户详情（意向分析）/ 律师工作台 / 我的
   ========================================================================== */

/* -------------------------------------------------------------- 公共构件 */
const CHIPS = [
  { label: '劳动纠纷', q: '我上班被公司无故辞退，怎么主张赔偿？' },
  { label: '婚姻家事', q: '我想离婚，对方不同意，我们已经分居两年了，怎么起诉？' },
  { label: '合同纠纷', q: '签了装修合同付了8万定金，对方一直不开工还失联了，怎么办？' },
  { label: '民间借贷', q: '朋友借了我5万元，只有微信转账记录没有借条，现在不还了怎么办？' },
];

const gradeText = (g) => ({ 高: '高意向', 中: '中意向', 低: '低意向' }[g] || '—');
const gradeCls = (g) => ({ 高: 'high', 中: 'mid', 低: 'low' }[g] || 'low');
const riskCls = (r) => ({ 高: 'risk-high', 中: 'risk-mid', 低: 'risk-low' }[r] || 'risk-mid');
const riskText = (r) => ({ 高: '风险较高', 中: '风险中等', 低: '风险较低' }[r] || '风险待评估');

const shortId = (sid) => {
  let h = 0;
  for (const ch of String(sid || '')) h = (h * 31 + ch.charCodeAt(0)) % 9000;
  return 1000 + h;
};

function navBar(title, opts = {}) {
  const { backAct = 'nav-back', acts = true } = opts;
  return `
  <div class="nav">
    <div class="nav-back">
      <button class="icon-btn" data-act="${backAct}" aria-label="返回">${icon('i-back')}</button>
    </div>
    <div class="nav-title">${esc(title)}</div>
    <div class="nav-acts">
      ${acts ? `
        <button class="icon-btn" data-act="nav-more" aria-label="更多">${icon('i-more')}</button>
        <button class="icon-btn" data-act="nav-legal" aria-label="合规声明">${icon('i-shield', 'ic-sm')}</button>` : ''}
    </div>
  </div>`;
}

const homeTabs = (active) => `
  <div class="tabbar">
    <button class="${active === 'home' ? 'on' : ''}" data-act="go-home">${icon('i-home')}<span>首页</span></button>
    <button class="${active === 'chat' ? 'on' : ''}" data-act="go-chat">${icon('i-chat')}<span>咨询</span></button>
    <button class="${active === 'me' ? 'on' : ''}" data-act="go-me">${icon('i-user')}<span>我的</span></button>
  </div>`;

const wbTabs = (active) => `
  <div class="tabbar">
    <button class="${active === 'leads' ? 'on' : ''}" data-act="go-workbench">${icon('i-list')}<span>线索</span></button>
    <button class="${active === 'customers' ? 'on' : ''}" data-act="go-customers">${icon('i-users')}<span>客户</span></button>
    <button class="${active === 'me' ? 'on' : ''}" data-act="go-me">${icon('i-user')}<span>我的</span></button>
  </div>`;

const emptyState = (title, hint, btn) => `
  <div class="empty">
    ${icon('i-doc')}
    <div>${esc(title)}</div>
    ${hint ? `<div class="muted">${esc(hint)}</div>` : ''}
    ${btn ? `<button class="btn primary" data-act="wb-seed">生成演示线索</button>` : ''}
  </div>`;

/* ==========================================================================
   一、首页
   ========================================================================== */
VIEWS.home = () => ({
  html: `
  <div class="page">
    <div class="page-head">
      ${navBar('智能律询通')}
      <div class="home-hero" style="padding:6px 16px 18px">
        <h1>智能律询通</h1>
        <p>AI法律咨询 · 智能客户研判</p>
      </div>
    </div>
    <div class="page-body">
      <div class="card entry">
        <div>
          <h2>客户咨询</h2>
          <p class="desc">AI智能法律咨询，7×24小时免费咨询，梳理法律风险</p>
          <button class="btn primary" data-act="go-chat">进入咨询</button>
        </div>
        <div class="entry-icon">${icon('i-chat')}</div>
      </div>

      <div class="card entry">
        <div>
          <h2>法律顾问</h2>
          <p class="desc">意向客户线索，咨询语义分析，客户意向评级</p>
          <button class="btn soft" data-act="lawyer-login">律师登录认证</button>
        </div>
        <div class="entry-icon warm">${icon('i-chart')}</div>
      </div>

      <div class="legal-note">
        AI内容仅供参考，不构成正式法律意见<br>
        线索池当前 ${S.counts.total} 条 · 高意向 ${S.counts.high} 条
      </div>
    </div>
    ${homeTabs('home')}
  </div>`,
});

/* ==========================================================================
   二、法律咨询（诉求客户咨询端）
   ========================================================================== */
function renderAiCard(msg) {
  const p = msg.parsed || { intro: '', sections: [], footnote: '', plain: true };
  if (p.plain) {
    return `<div class="msg assistant"><div class="bubble">${md(msg.text)}</div></div>`;
  }
  const secs = p.sections.map((s, i) => `
    <div class="ai-sec">
      <div class="ai-sec-title">
        <span class="ai-sec-no">${i + 1}</span>${esc(s.title)}
      </div>
      <ul class="ai-list">
        ${s.items.map((it) => {
          if (!it.label) return `<li>${md(it.text)}</li>`;
          // 短标签（如「你已具备的凭证」「风险评估」）随正文同行；法条名等长标签独占一行
          return it.label.length <= 10
            ? `<li><span class="ai-li-inline">${esc(it.label)}：</span>${md(it.text)}</li>`
            : `<li><span class="ai-li-title">${esc(it.label)}</span>${md(it.text)}</li>`;
        }).join('')}
      </ul>
    </div>`).join('');

  const refs = msg.refs || {};
  const refChips = [
    ...(refs.statutes || []).slice(0, 3).map((s) => `<span class="ai-ref">${esc(s.law + s.article)}</span>`),
    ...(refs.cases || []).slice(0, 2).map((c) => `<span class="ai-ref case">${esc(c.case_no)}</span>`),
  ].join('');

  return `
  <div class="msg assistant">
    <div class="ai-card">
      <div class="ai-head">
        <span class="ai-avatar">AI</span>
        <span class="ai-name">法律AI</span>
        <span class="ai-meta">${msg.model ? esc(msg.model) : '已核验法条'}</span>
      </div>
      ${p.intro ? `<div class="ai-intro">${md(p.intro)}</div>` : ''}
      ${secs}
      ${refChips ? `<div class="ai-refs">${refChips}</div>` : ''}
      <div class="ai-foot">${icon('i-alert')}复杂案件建议线下委托律师 · 内容由 AI 生成，仅供参考</div>
    </div>
  </div>`;
}

function renderChatMsg(m) {
  if (m.role === 'user') {
    return `<div class="msg user"><div class="bubble">${md(m.text)}</div></div>`;
  }
  if (m.card) return renderAiCard(m);
  return `<div class="msg assistant"><div class="bubble">${md(m.text)}</div></div>`;
}

VIEWS.chat = () => ({
  html: `
  <div class="page">
    <div class="page-head">${navBar('法律咨询')}</div>
    <div class="chat-body" id="chatBody">
      ${S.chat.messages.map(renderChatMsg).join('')}
      ${S.chat.sending ? `<div class="msg assistant"><div class="ai-card"><div class="typing"><i></i><i></i><i></i></div></div></div>` : ''}
    </div>
    <div class="composer">
      <div class="samples">
        ${CHIPS.map((c) => `<button class="chip" data-act="chat-chip" data-q="${esc(c.q)}">${esc(c.label)}</button>`).join('')}
      </div>
      <div class="input-row">
        <div class="input-wrap">
          <textarea id="chatInput" rows="1" placeholder="请输入法律问题"></textarea>
          <button class="input-mic" data-act="chat-voice" aria-label="语音输入">${icon('i-mic')}</button>
        </div>
        <button class="send-btn" data-act="chat-send" aria-label="发送">${icon('i-send')}</button>
      </div>
    </div>
  </div>`,
  after: () => {
    const ta = $('#chatInput');
    if (ta) {
      ta.addEventListener('input', () => {
        ta.style.height = 'auto';
        ta.style.height = Math.min(92, ta.scrollHeight) + 'px';
      });
      ta.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(ta); }
      });
      if (!S.chat.sending) ta.focus();
    }
    scrollBottom('.chat-body');
  },
});

async function sendChat(ta) {
  ta = ta || $('#chatInput');
  const text = (ta ? ta.value : '').trim();
  if (!text || S.chat.sending) return;
  ta.value = '';
  ta.style.height = 'auto';
  askChat(text);
}

/* 统一的提问入口：真实调用 /api/chat，返回结果解析为结构化卡片 */
async function askChat(text) {
  if (!text || S.chat.sending) return;
  S.chat.messages.push({ role: 'user', text });
  S.chat.sending = true;
  render();
  try {
    const res = await post('/api/chat', { session_id: S.chat.sessionId, message: text });
    S.chat.sending = false;
    if (!res.ok) {
      S.chat.messages.push({ role: 'assistant', text: '⚠️ ' + (res.error || '请求失败'), plain: true });
    } else {
      S.chat.sessionId = res.session_id;
      S.chat.trace = res.trace;
      S.chat.refs = res.references;
      S.chat.messages.push({
        role: 'assistant',
        card: true,
        parsed: parseAnswer(res.reply),
        refs: res.references,
        model: genModel(res.trace),
        text: res.reply,
      });
      refreshCounts();
      S.wb.loaded = false;      // 出现新会话 → 线索池需重取
    }
  } catch (err) {
    S.chat.sending = false;
    S.chat.messages.push({ role: 'assistant', text: '⚠️ 网络异常：' + err.message, plain: true });
  }
  if (cur().name === 'chat') render();
}

/* ==========================================================================
   三、客户详情（意向分析）
   ========================================================================== */
const LD = { id: null, lead: null, session: null, openHistory: false };

async function ensureLeadDetail(id) {
  if (LD.id !== id) { LD.id = id; LD.session = null; LD.openHistory = false; LD.lead = S.wb.items.find((l) => l.session_id === id) || null; }
  if (LD.session) return;
  const res = await api('/api/session/' + encodeURIComponent(id));
  if (res.ok) { LD.session = res.session; LD.lead = res.lead || LD.lead; }
  if (cur().name === 'lead') render();
}

VIEWS.lead = (params) => {
  const id = params.id;
  const lead = (LD.id === id && LD.lead) || S.wb.items.find((l) => l.session_id === id);
  if (!lead) {
    ensureLeadDetail(id);
    return { html: `<div class="page"><div class="page-head">${navBar('客户详情')}</div>
      <div class="page-body">${emptyState('正在读取客户分析…')}</div></div>` };
  }
  const risk = lead.risk || {};
  const session = LD.id === id ? LD.session : null;
  const history = (session && session.history) || [];
  const region = session ? regionTag(history) : '本地';
  const found = (risk.evidence && risk.evidence.found) || [];
  const missing = (risk.evidence && risk.evidence.missing) || [];
  const win = risk.win_probability || { low: 0, high: 0 };
  const topFactors = (lead.score_detail || []).slice(0, 3);
  const strong = (lead.tags || []).filter((t) => /起诉|仲裁|委托|律师|诉讼/.test(t));

  const rows = [
    {
      icon: 'i-target', label: '用户诉求',
      text: `${lead.demands.length ? '核心诉求为「' + lead.demands.join('、') + '」' : '希望了解相关法律规定'}` +
        `${lead.max_amount ? `，涉案金额约 ${lead.max_amount.toLocaleString()} 元` : ''}` +
        `${lead.grade === '高' ? '；维权意愿强烈，已进入行动准备阶段。' : '。'}`,
    },
    {
      icon: 'i-tag', label: '案件关键点',
      text: `${found.length ? '已有凭证：' + found.join('、') : '暂未识别到可用凭证'}；` +
        `${missing.length ? '待补充：' + missing.slice(0, 3).join('、') : '证据链相对完整'}。`,
    },
    {
      icon: 'i-alert', label: '风险评估',
      text: `证据覆盖率 ${Math.round(((risk.evidence && risk.evidence.coverage) || 0) * 100)}%，` +
        `${riskText(risk.risk_level)}；胜诉概率区间 ${Math.round(win.low * 100)}% ~ ${Math.round(win.high * 100)}%（模型估算）。` +
        `${missing.length ? '存在举证瑕疵，需先行固定证据。' : ''}`,
    },
    {
      icon: 'i-spark', label: '意向判断',
      text: `综合得分 ${lead.score}/100，评定为「${gradeText(lead.grade)}」。` +
        `${strong.length ? `命中强意向信号：${strong.join('、')}。` : ''}` +
        `咨询 ${lead.turns} 轮，${lead.grade === '高' ? '多次追问程序与费用，建议优先跟进。' : '可继续培育。'}`,
    },
  ];

  return {
    html: `
    <div class="page">
      <div class="page-head">${navBar('客户详情')}</div>
      <div class="page-body">
        <div class="card">
          <div class="kv-grid">
            <div class="kv-item"><div class="k">咨询时间</div><div class="v">${icon('i-clock')}${esc(fmtDay(lead.created_at || lead.updated_at))}</div></div>
            <div class="kv-item"><div class="k">纠纷类型</div><div class="v">${icon('i-tag')}${esc(lead.tags[0] || '未明确')}</div></div>
            <div class="kv-item"><div class="k">地域标签</div><div class="v">${icon('i-pin')}${esc(region)}</div></div>
            <div class="kv-item"><div class="k">客户意向</div><div class="v"><span class="badge ${gradeCls(lead.grade)}">${gradeText(lead.grade)}</span></div></div>
          </div>
        </div>

        <div class="section">
          <div class="section-head">${icon('i-doc')}AI意向分析报告<span class="right">${esc(lead.model ? lead.model.model_label : 'DeepSeek-V3')}</span></div>
          <div class="card">
            ${rows.map((r) => `
              <div class="report-row">
                <div class="dot">${icon(r.icon)}</div>
                <div>
                  <div class="label">${esc(r.label)}</div>
                  <div class="text">${esc(r.text)}</div>
                </div>
              </div>`).join('')}
          </div>
        </div>

        <div class="section">
          <div class="section-head">${icon('i-check')}建议跟进方向</div>
          <div class="card">
            <ul class="ai-list">
              ${lead.followups.slice(0, 3).map((f) => `<li>${esc(f)}</li>`).join('')}
            </ul>
          </div>
        </div>

        <div class="section">
          <div class="card" style="padding:14px 16px 6px">
            <div class="score-panel">
              <div>
                <div class="num">${lead.score}<span>/100</span></div>
              </div>
              <div class="grow">
                <div class="badge ${gradeCls(lead.grade)}">${gradeText(lead.grade)}</div>
                <div class="sub">跟进状态：${esc(lead.follow_status || '待跟进')} · 咨询 ${lead.turns} 轮</div>
              </div>
            </div>
            ${topFactors.map((d) => `<div class="factor"><span>${esc(d.factor)}</span><b>+${d.score}</b></div>`).join('')}
          </div>
        </div>

        <div class="section">
          <button class="collapse-head ${LD.openHistory ? 'open' : ''}" data-act="lead-history">
            ${icon('i-list', 'lead')}原始咨询记录
            <span class="right muted" style="font-size:12px;font-weight:500">共 ${history.filter((m) => m.role === 'user').length} 轮</span>
            ${icon('i-down', 'arrow')}
          </button>
          ${LD.openHistory ? `<div class="card">
            ${history.length ? history.map((m, i) => `
              <div class="history-item ${m.role}">
                <div class="who">${m.role === 'user' ? '客户' : '法律AI'}${m.ts ? `<span class="muted" style="font-weight:400">${esc(fmtTime(m.ts))}</span>` : ''}</div>
                <div class="txt ${m.role === 'user' ? '' : 'clamp'}">${esc(String(m.content).slice(0, 400))}</div>
              </div>`).join('') : '<div class="muted" style="font-size:12.5px">暂无对话记录。</div>'}
          </div>` : ''}
        </div>

        <div class="section">
          <div class="note-box">
            <textarea id="leadNote" placeholder="添加跟进记录">${esc(getNote(id) || (session && session.follow_note) || '')}</textarea>
            <div class="btn-row" style="margin-top:10px">
              <button class="btn ghost" data-act="lead-note-save" data-id="${esc(id)}">保存跟进记录</button>
            </div>
          </div>
        </div>

        <button class="btn primary block" style="margin-top:16px" data-act="lead-contacted" data-id="${esc(id)}">
          ${lead.follow_status === '已联系' ? '已标记为已沟通（点击取消）' : '标记为已沟通'}
        </button>
      </div>
    </div>`,
    after: () => ensureLeadDetail(id),
  };
};

/* ==========================================================================
   四、律师工作台 / 客户
   ========================================================================== */
function statTiles(st) {
  return `
  <div class="stat-row">
    <div class="stat">
      <div class="top">${icon('i-spark')}<span>今日新增线索</span></div>
      <div class="val">${st.todayCount}</div>
      <div class="viz">${ring({ pct: st.todayShare, size: 58, width: 7, label: `今日占近7日 ${st.todayShare}%` })}</div>
      <div class="cap">近7日 ${st.recent} 条</div>
    </div>
    <div class="stat">
      <div class="top">${icon('i-users')}<span>高意向客户</span></div>
      <div class="val" style="color:var(--accent)">${st.high}</div>
      <div class="viz">${ring({ pct: st.highShare, size: 58, width: 7, warm: true, label: `高意向占比 ${st.highShare}%` })}</div>
      <div class="cap">占全部线索 ${st.highShare}%</div>
    </div>
    <div class="stat">
      <div class="top">${icon('i-chart')}<span>${esc(st.top.name)}</span></div>
      <div class="val">${st.top.share}<small>%</small></div>
      <div class="viz">${bars(st.cats.map((c, i) => ({
        label: c.slice(0, 2), full: c, value: st.catCount[i],
        share: st.total ? Math.round((st.catCount[i] / st.total) * 100) : 0,
      })))}</div>
      <div class="cap">案件类型分布</div>
    </div>
  </div>`;
}

function filterBar() {
  const f = S.wb.filters;
  const opt = (v, label, sel) => `<option value="${v}" ${sel === v ? 'selected' : ''}>${label}</option>`;
  return `
  <div class="filter-bar">
    <div class="filter-select">
      <select data-act-change="wb-filter" data-k="category">
        ${opt('', '案件类型', f.category)}
        ${opt('labor', '劳动纠纷', f.category)}
        ${opt('marriage', '婚姻家事', f.category)}
        ${opt('contract', '合同纠纷', f.category)}
        ${opt('loan', '民间借贷', f.category)}
      </select>${icon('i-down')}
    </div>
    <div class="filter-select">
      <select data-act-change="wb-filter" data-k="grade">
        ${opt('', '意向等级', f.grade)}${opt('高', '高意向', f.grade)}${opt('中', '中意向', f.grade)}${opt('低', '低意向', f.grade)}
      </select>${icon('i-down')}
    </div>
    <div class="filter-select">
      <select data-act-change="wb-filter" data-k="time">
        ${opt('', '咨询时间', f.time)}${opt('today', '今日', f.time)}${opt('7d', '近7天', f.time)}${opt('30d', '近30天', f.time)}
      </select>${icon('i-down')}
    </div>
  </div>`;
}

function leadCard(l) {
  return `
  <div class="lead-card" data-act="lead-open" data-id="${esc(l.session_id)}">
    <div class="hd">
      <span class="cid">客户ID：${shortId(l.session_id)}</span>
      <span class="badge ${gradeCls(l.grade)}">${gradeText(l.grade)}</span>
    </div>
    <div class="row"><span class="k">案件标签：</span><span class="v" style="display:block">${esc((l.tags || []).slice(0, 3).join(' · ') || '未明确')}</span></div>
    <div class="row"><span class="k">咨询摘要：</span><span class="v">${esc(l.summary)}</span></div>
    <div class="row"><span class="k">咨询时间：</span><span class="v" style="display:block">${esc(fmtDay(l.created_at || l.updated_at))}</span></div>
    <div class="foot">
      <span class="t">${esc(l.follow_status || '待跟进')} · 综合 ${l.score} 分</span>
      <button class="btn primary mini" data-act="lead-open" data-id="${esc(l.session_id)}">查看报告</button>
    </div>
  </div>`;
}

function workbenchPage(active) {
  const st = wbStats();
  const items = S.wb.filtered;
  const list = items.length
    ? items.map(leadCard).join('')
    : S.wb.loaded
      ? emptyState('当前筛选条件下暂无线索', '可清空筛选，或到「咨询」页发起一次真实咨询', !S.wb.items.length)
      : emptyState('线索加载中…');
  return `
  <div class="page">
    <div class="page-head">
      ${navBar('律师工作台')}
      <div style="padding:0 16px">${filterBar()}</div>
    </div>
    <div class="page-body">
      ${statTiles(st)}
      ${list}
    </div>
    ${wbTabs(active)}
  </div>`;
}

VIEWS.workbench = () => ({
  html: workbenchPage('leads'),
  after: () => ensureLeads(),
});

VIEWS.customers = () => {
  const mine = S.wb.filtered.filter((l) => l.follow_status && l.follow_status !== '待跟进');
  const st = wbStats();
  return {
    html: `
    <div class="page">
      <div class="page-head">${navBar('我的客户')}</div>
      <div class="page-body">
        <div class="card" style="margin-bottom:14px">
          <div class="kv-grid">
            <div class="kv-item"><div class="k">跟进中客户</div><div class="v">${mine.length} 位</div></div>
            <div class="kv-item"><div class="k">线索总量</div><div class="v">${st.total} 条</div></div>
          </div>
        </div>
        ${mine.length ? mine.map(leadCard).join('')
          : emptyState('暂无跟进中的客户', '在「线索」列表打开报告，点击「标记为已沟通」即转入客户池')}
      </div>
      ${wbTabs('customers')}
    </div>`,
    after: () => ensureLeads(),
  };
};

async function ensureLeads() {
  if (S.wb.loaded || S.wb.loading) return;
  await loadLeads(true);
  const n = cur().name;
  if (n === 'workbench' || n === 'customers') render();
}

/* ==========================================================================
   五、我的（身份 + 系统状态 + 演示工具）
   ========================================================================== */
VIEWS.me = () => {
  const h = S.health;
  const kb = (h && h.kb) || {};
  const catNames = { labor: '劳动纠纷', marriage: '婚姻家事', contract: '合同纠纷', loan: '民间借贷' };
  const tiers = (h && h.models) || {};
  // 「我的」可能从首页组或工作台组进入——底部标签栏跟随进来时的那一组
  const inWb = S.stack.slice(0, -1).some((v) => v.name === 'workbench' || v.name === 'customers');
  return {
    html: `
    <div class="page">
      <div class="page-head">${navBar('我的')}</div>
      <div class="page-body">
        <div class="card" style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
          <div class="entry-icon" style="width:54px;height:54px;border-radius:16px">${icon('i-user')}</div>
          <div style="flex:1">
            <div style="font-size:16px;font-weight:700">${esc(S.me.role)}</div>
            <div class="muted" style="font-size:12.5px;margin-top:4px">
              ${S.chat.sessionId ? '当前会话 ' + esc(S.chat.sessionId) : '尚未开始咨询'}
            </div>
          </div>
        </div>

        <div class="section">
          <div class="section-head">${icon('i-spark')}系统状态</div>
          <div class="card">
            <div class="factor"><span>模型接入模式</span><b style="color:var(--ink)">${esc((h && h.llm_mode) || '加载中')}</b></div>
            <div class="factor"><span>知识库版本</span><b style="color:var(--ink)">${esc(kb.version || '—')}</b></div>
            <div class="factor"><span>法条 / 案例</span><b style="color:var(--ink)">${kb.statutes || 0} / ${kb.cases || 0} 条</b></div>
            <div class="factor"><span>向量检索后端</span><b style="color:var(--ink)">${esc((h && h.embedder && (h.embedder.backend || h.embedder.name)) || '—')}</b></div>
            ${Object.entries(kb.by_category || {}).map(([k, v]) =>
              `<div class="factor"><span>${esc(catNames[k] || k)}</span><b style="color:var(--ink)">${v} 条</b></div>`).join('')}
          </div>
        </div>

        <div class="section">
          <div class="section-head">${icon('i-chart')}MoMA 模型路由</div>
          <div class="card">
            ${Object.entries(tiers).map(([t, label]) =>
              `<div class="factor"><span>${esc(t)} 档位</span><b style="color:var(--ink)">${esc(label)}</b></div>`).join('')}
          </div>
        </div>

        <div class="section">
          <div class="section-head">${icon('i-doc')}演示工具</div>
          <div class="card" style="padding:4px 16px">
            <button class="sheet-item" data-act="wb-seed">
              ${icon('i-spark')}生成演示线索
              <span class="r">写入样例咨询${icon('i-right')}</span>
            </button>
            <button class="sheet-item" data-act="me-trace">
              ${icon('i-list')}查看最近一次工作流时序
              <span class="r">${S.chat.trace ? '可用' : '需先咨询'}${icon('i-right')}</span>
            </button>
            <button class="sheet-item danger" data-act="me-reset">
              ${icon('i-alert')}清空演示数据
              <span class="r">${icon('i-right')}</span>
            </button>
          </div>
        </div>

        <div class="legal-note">
          智能律询通 MVP v1.0 · AI 小宝 gogogo 团队<br>
          AI内容仅供参考，不构成正式法律意见
        </div>
      </div>
      ${inWb ? wbTabs('me') : homeTabs('me')}
    </div>`,
  };
};

/* ==========================================================================
   浮层：工作流时序 / 合规声明 / 律师登录 / 更多
   ========================================================================== */
function traceSheet() {
  const trace = S.chat.trace;
  if (!trace) {
    return `<div class="sheet-grab"></div><h3>工作流时序</h3>
      <p class="sub">发起一次咨询后，这里会实时展示端到端每一步的埋点。</p>`;
  }
  const steps = trace.map((s) => {
    let extra = '';
    if (s.model) {
      extra += `<div class="m">MoMA 路由 → <b>${esc(s.model.model_label)}</b>（${esc(s.model.model)} · ${esc(s.model.provider)}）
        · ${s.model.latency_ms}ms · SLA ${s.model.sla_ms}ms ${s.model.sla_ok ? '✅' : '⚠️'}<br>${esc(s.model.route_reason)}</div>`;
    }
    if (s.tool_call && s.tool_call.hit_count) {
      const refs = s.tool_call.results.map((r) => r.law
        ? `<div class="ref">📖 ${esc(r.law + r.article)}《${esc(r.title)}》· 相关度 ${r.relevance}</div>`
        : `<div class="ref">⚖️ ${esc(r.case_no)} → ${esc(r.result)} · 相关度 ${r.relevance}</div>`).join('');
      extra += `<div style="margin-top:5px">${refs}</div>`;
    }
    if (s.step === 5 && s.output && s.output.risks) {
      extra += s.output.risks.map((r) => `<div class="ref">[${esc(r.level)}风险] ${esc(r.point)}</div>`).join('');
    }
    return `<div class="trace-step">
      <div class="t">${s.step === 'M' ? '♻️' : s.step + '.'} ${esc(s.name)}</div>
      <div class="d">${esc(s.detail)}</div>${extra}
    </div>`;
  }).join('');
  return `<div class="sheet-grab"></div>
    <h3>工作流时序</h3>
    <p class="sub">用户输入 → 意图识别 → 工具调用 → 生成回答 → 风险提示</p>
    <div class="sheet-body">${steps}</div>`;
}

function legalSheet() {
  return `<div class="sheet-grab"></div>
    <h3>合规与免责声明</h3>
    <p class="sub">智能律询通 · MVP v1.0</p>
    <div class="sheet-body">
      <ul class="ai-list">
        <li>本系统输出由 AI 基于公开法律文本与示例案例自动生成，<b>仅供参考，不构成正式法律意见</b>。</li>
        <li>法条依据公开法律法规整理；案例为演示用虚构样例，实际引用请核实裁判文书原文。</li>
        <li>所有胜诉概率区间为模型估算，不构成对案件结果的承诺。</li>
        <li>B 端线索分析基于用户咨询语义，涉及个人信息已做匿名化处理（消费者-XXXX）。</li>
        <li>复杂案件建议线下委托执业律师，由律师结合完整证据材料出具意见。</li>
      </ul>
    </div>`;
}

/* ==========================================================================
   动作绑定
   ========================================================================== */
on('nav-back', () => back());
on('sheet-close', () => closeSheet());
on('nav-legal', () => openSheet(legalSheet()));

on('nav-more', () => {
  const inChat = cur().name === 'chat';
  openSheet(`
    <div class="sheet-grab"></div>
    <h3>更多操作</h3>
    <p class="sub">智能律询通 · 演示环境</p>
    <div class="sheet-list">
      <button class="sheet-item" data-act="chat-trace">${icon('i-list')}工作流时序<span class="r">${icon('i-right')}</span></button>
      <button class="sheet-item" data-act="nav-legal">${icon('i-shield')}合规与免责声明<span class="r">${icon('i-right')}</span></button>
      <button class="sheet-item" data-act="go-home">${icon('i-home')}回到首页<span class="r">${icon('i-right')}</span></button>
      ${inChat && S.chat.messages.length > 1 ? `<button class="sheet-item" data-act="chat-clear">${icon('i-spark')}新建对话<span class="r">${icon('i-right')}</span></button>` : ''}
    </div>`);
});

on('chat-trace', () => { closeSheet(); setTimeout(() => openSheet(traceSheet()), 180); });

on('go-home', () => { home(); });
on('go-chat', () => {
  if (cur().name === 'chat') return;
  go('chat');
});
on('go-me', () => { go('me'); });
on('go-workbench', () => { if (cur().name !== 'workbench') root('workbench'); });
on('go-customers', () => { if (cur().name !== 'customers') root('customers'); });

on('chat-send', () => sendChat());
on('chat-chip', (el) => askChat(el.dataset.q));
on('chat-voice', () => toast('演示环境未接入语音识别，请直接输入问题'));
on('chat-clear', () => {
  closeSheet();
  S.chat = { sessionId: null, messages: [{ role: 'assistant', text: '您好，我是智能律询通法律智能体，解读您的问题。' }], sending: false, trace: null, refs: null };
  render();
});

on('lawyer-login', () => {
  openSheet(`
    <div class="sheet-grab"></div>
    <h3>律师登录认证</h3>
    <p class="sub">演示环境：直接点击登录即可进入工作台</p>
    <div class="field"><label>执业证号</label><input value="13XXXXXXX0000" readonly></div>
    <div class="field"><label>手机号</label><input value="156****8563" readonly></div>
    <button class="btn primary block" data-act="login-submit" style="margin-top:6px">登录并进入工作台</button>`);
});
on('login-submit', () => {
  S.me.role = '执业律师';
  closeSheet();
  setTimeout(() => root('workbench'), 160);
});

on('wb-filter', (el) => {
  S.wb.filters[el.dataset.k] = el.value;
  const reload = el.dataset.k === 'category' || el.dataset.k === 'grade';
  if (reload) {
    S.wb.loaded = false;
    loadLeads(true).then(() => { if (/workbench|customers/.test(cur().name)) render(); });
  } else {
    applyTimeFilter();
    render();
  }
});

on('lead-open', (el) => {
  const id = el.dataset.id;
  if (!id) return;
  go('lead', { id });
});

on('lead-history', () => {
  LD.openHistory = !LD.openHistory;
  render();
});

on('lead-note-save', async (el) => {
  const id = el.dataset.id;
  const ta = $('#leadNote');
  const note = ta ? ta.value.trim() : '';
  setNote(id, note);
  const res = await post('/api/leads/note', { session_id: id, note });
  toast(res.ok ? '跟进记录已保存' : '已保存在本地（服务端未响应）');
});

on('lead-contacted', async (el) => {
  const id = el.dataset.id;
  const lead = LD.lead || S.wb.items.find((l) => l.session_id === id) || {};
  const next = lead.follow_status === '已联系' ? '待跟进' : '已联系';
  const res = await post('/api/leads/status', { session_id: id, status: next });
  if (res.ok) {
    if (LD.lead && LD.lead.session_id === id) LD.lead.follow_status = next;
    const it = S.wb.items.find((l) => l.session_id === id);
    if (it) it.follow_status = next;
    toast(next === '已联系' ? '已标记为已沟通，转入客户池' : '已取消标记');
    render();
  } else {
    toast(res.error || '操作失败');
  }
});

on('wb-seed', async () => {
  toast('正在通过真实引擎生成演示线索…', 6000);
  const res = await post('/api/demo/seed', {});
  if (res.ok) {
    S.wb.loaded = false;
    await refreshCounts();
    await loadLeads(true);
    toast(`已生成 ${res.created} 条演示线索`);
    if (/workbench|customers/.test(cur().name)) render();
  } else {
    toast(res.error || '生成失败');
  }
});

on('me-trace', () => {
  if (!S.chat.trace) { toast('请先到「咨询」页发起一次咨询'); return; }
  openSheet(traceSheet());
});

on('me-reset', () => {
  openSheet(`
    <div class="sheet-grab"></div>
    <h3>清空演示数据</h3>
    <p class="sub">将删除全部会话、线索与跟进记录，不可撤销。</p>
    <div class="btn-row">
      <button class="btn ghost" style="flex:1" data-act="sheet-close">取消</button>
      <button class="btn primary" style="flex:1" data-act="me-reset-ok">确认清空</button>
    </div>`);
});
on('me-reset-ok', async () => {
  await post('/api/admin/reset', {});
  closeSheet();
  S.chat = { sessionId: null, messages: [{ role: 'assistant', text: '您好，我是智能律询通法律智能体，解读您的问题。' }], sending: false, trace: null, refs: null };
  S.wb.loaded = false;
  S.wb.items = [];
  S.wb.filtered = [];
  LD.id = null; LD.lead = null; LD.session = null;
  await refreshCounts();
  toast('演示数据已清空');
  if (cur().name !== 'chat') render();
});

/* 初始问候语 */
S.chat.messages.push({ role: 'assistant', text: '您好，我是智能律询通法律智能体，解读您的问题。' });

