// 外観 (配色) の切り替えと、iPad で見ながら作るカスタム外観 (名前を付けて 3 件まで保存)。
// 用意した外観は style.css の html[data-theme="…"]。カスタムは html[data-theme="custom-N"] に、
// 色などを CSS 変数として html の style に直接入れる (描画前に index.html でも同じことをする)。
import { el } from './dom.js';

export const THEMES = [['', '標準'], ['apricot', 'アプリコット'], ['navy', '紺と薄黄']];
const SLOTS = 3;
const STORE = 'customThemes'; // [{ name, settings, vars } | null] × 3

// 「元にする外観」の値 (用意した外観にだいたい合わせたもの)
const PRESETS = {
  '': {
    bg: '#f3f5f8', surface: '#ffffff', text: '#1b1f24', muted: '#5f6b7a', line: '#d9dee5', primary: '#1f6feb', primaryText: '#ffffff', chip: '#eef1f5',
    radius: 14, cardShadow: 0, cardBorder: true,
    kpBg: '#ffffff', kpText: '#1b1f24', key: '#f3f5f8', keyText: '#1b1f24', keyFn: '#eef1f5', next: '#1f6feb', nextText: '#ffffff', depth: 0,
  },
  apricot: {
    bg: '#fff3e8', surface: '#fffcf8', text: '#3a2a20', muted: '#8a7262', line: '#f5dcc6', primary: '#f07c2e', primaryText: '#ffffff', chip: '#ffe9d6',
    radius: 22, cardShadow: 2, cardBorder: false,
    kpBg: '#fffcf8', kpText: '#3a2a20', key: '#fff4ea', keyText: '#3a2a20', keyFn: '#fbe3cc', next: '#f07c2e', nextText: '#ffffff', depth: 2,
  },
  navy: {
    bg: '#fdf8e1', surface: '#fffdf3', text: '#1c2a4a', muted: '#6a7090', line: '#ece3b8', primary: '#1f3a6e', primaryText: '#fff8d6', chip: '#f7efc8',
    radius: 16, cardShadow: 2, cardBorder: false,
    kpBg: '#1f3a6e', kpText: '#fff8d6', key: '#fbf3d2', keyText: '#1c2a4a', keyFn: '#f3e6ab', next: '#f7d65e', nextText: '#1c2a4a', depth: 2,
  },
};

// 画面に並べる設定の項目
const GROUPS = [
  ['画面', [
    ['bg', '背景', 'color'], ['surface', 'カード・ヘッダー', 'color'], ['text', '文字', 'color'], ['muted', '補助の文字', 'color'],
    ['line', '線・入力欄の枠', 'color'], ['chip', '札 (区分・前回など)', 'color'],
    ['primary', 'ボタン・入力中の枠', 'color'], ['primaryText', 'ボタンの文字', 'color'],
    ['radius', '角の丸み', 'range', 0, 28], ['cardShadow', 'カードの影', 'range', 0, 3], ['cardBorder', 'カードの枠線', 'check'],
  ]],
  ['テンキー', [
    ['kpBg', 'パネル', 'color'], ['kpText', 'パネルの文字', 'color'],
    ['key', '数字キー', 'color'], ['keyText', 'キーの文字', 'color'], ['keyFn', 'BS・戻る・進む・閉じる', 'color'],
    ['next', 'Enter', 'color'], ['nextText', 'Enter の文字', 'color'],
    ['depth', 'キーの立体感', 'range', 0, 3],
  ]],
];

// ---------------- 色の計算 ----------------
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const hex = (c) => `#${c.map((v) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('')}`;
/** a と b を混ぜる (t = b の割合) */
const mix = (a, b, t) => { const x = rgb(a), y = rgb(b); return hex(x.map((v, i) => v + (y[i] - v) * t)); };
const isDark = (c) => { const [r, g, b] = rgb(c); return 0.299 * r + 0.587 * g + 0.114 * b < 128; };

/** 設定から CSS 変数を作る。入力済の緑・範囲外の赤・注意の黄土色は意味を変えないよう固定 (暗い地なら明るめ) */
export function themeVars(s) {
  const dark = isDark(s.surface);
  const [ok, ng, warn] = dark ? ['#4cc26c', '#ff6b6b', '#e0b341'] : ['#1a7f37', '#c62828', '#9a6700'];
  const d = Number(s.depth) || 0;
  const sh = Number(s.cardShadow) || 0;
  const a = dark ? 2 : 1; // 暗い地では影を濃く
  const grad = (c) => (d ? `linear-gradient(180deg, ${mix(c, '#ffffff', 0.12 * d)} 0%, ${mix(c, '#000000', 0.04 * d)} 100%)` : c);
  return {
    '--bg': s.bg, '--surface': s.surface, '--text': s.text, '--muted': s.muted, '--line': s.line,
    '--primary': s.primary, '--primary-text': s.primaryText, '--chip': s.chip, '--radius': `${s.radius}px`,
    '--ok': ok, '--ng': ng, '--warn': warn,
    '--ok-bg': mix(s.surface, ok, 0.14), '--ng-bg': mix(s.surface, ng, 0.14), '--warn-bg': mix(s.surface, warn, 0.16),
    'color-scheme': dark ? 'dark' : 'light',
    '--c-card-border': s.cardBorder ? s.line : 'transparent',
    '--c-card-shadow': sh ? `0 ${sh}px ${4 + sh * 4}px rgb(0 0 0 / ${(0.04 + sh * 0.035) * a})` : 'none',
    '--c-kp-bg': s.kpBg, '--c-kp-text': s.kpText,
    '--c-kp-muted': mix(s.kpBg, s.kpText, 0.7), '--c-kp-line': mix(s.kpBg, s.kpText, 0.25),
    '--c-key-bg': grad(s.key), '--c-key-text': s.keyText, '--c-key-border': mix(s.key, '#000000', 0.1),
    '--c-keyfn-bg': grad(s.keyFn),
    '--c-next-bg': grad(s.next), '--c-next-text': s.nextText, '--c-next-border': mix(s.next, '#000000', 0.1),
    '--c-key-shadow': d ? `inset 0 1px 0 rgb(255 255 255 / ${0.2 * d}), 0 ${Math.ceil(d / 2) + 1}px ${d + 2}px rgb(0 0 0 / ${0.07 + 0.06 * d})` : 'none',
  };
}

// ---------------- 保存と適用 ----------------
export function loadSlots() {
  try {
    const a = JSON.parse(localStorage.getItem(STORE) || '[]');
    return Array.from({ length: SLOTS }, (_, i) => (a[i]?.settings ? a[i] : null));
  } catch { return Array(SLOTS).fill(null); }
}
function saveSlots(slots) {
  try { localStorage.setItem(STORE, JSON.stringify(slots)); return true; } catch { return false; }
}
export const currentTheme = () => { try { return localStorage.getItem('theme') || ''; } catch { return ''; } };

// html の style に入れた変数を消す (--topbar-h など、ほかの用途の変数は残す)
const VAR_KEYS = Object.keys(themeVars(PRESETS['']));
function clearVars() { for (const k of VAR_KEYS) document.documentElement.style.removeProperty(k); }
function setVars(vars) { for (const [k, v] of Object.entries(vars)) document.documentElement.style.setProperty(k, v); }

/** 画面に反映するだけ (記憶しない)。key: '' / 'apricot' / 'navy' / 'custom-N' / 'custom-edit' (vars を渡す) */
function showTheme(key, vars) {
  clearVars();
  const m = /^custom-(\d)$/.exec(key);
  if (m) {
    const slot = loadSlots()[m[1]];
    if (!slot) key = ''; // 消された保存先を選んでいたら標準に戻す
    else vars = slot.vars;
  }
  if (key) document.documentElement.dataset.theme = key;
  else delete document.documentElement.dataset.theme;
  if (key.startsWith('custom') && vars) setVars(vars);
  return key;
}

/** 外観を切り替えて記憶する */
export function applyTheme(key) {
  key = showTheme(key);
  try { localStorage.setItem('theme', key); } catch {}
}

/** ホームの外観の選択 (用意した外観 + 保存したカスタム) と、カスタマイズの画面へのボタン */
export function themePicker(onCustomize) {
  const cur = document.documentElement.dataset.theme || '';
  const items = [...THEMES, ...loadSlots().map((s, i) => (s ? [`custom-${i}`, s.name] : null)).filter(Boolean)];
  const btns = items.map(([k, label]) => el('button', {
    class: `seg${k === cur ? ' on' : ''}`,
    onclick: () => {
      applyTheme(k);
      btns.forEach((b, i) => b.classList.toggle('on', items[i][0] === k));
    },
  }, label));
  return el('div', { class: 'theme-row' },
    el('div', { class: 'segs' }, btns),
    el('button', { class: 'btn', onclick: onCustomize }, '🎨 カスタマイズ'));
}

// ---------------- カスタマイズの画面 ----------------
/** 見本: カード (入力済・入力中・範囲外・選択式) と、押しても動かないテンキー */
function preview() {
  const chips = (...c) => el('div', { class: 'chips' }, c.map((t) => (Array.isArray(t)
    ? el('span', { class: 'chip prev' }, el('span', { class: 'prev-label' }, '前回'), el('span', { class: 'prev-value' }, t[0]))
    : el('span', { class: 'chip' }, t))));
  const card = (state, title, ref, chipEl, body, status) => el('div', { class: 'card', dataset: { state } },
    el('div', { class: 'card-head' }, el('div', { class: 'card-title' }, title), el('div', { class: 'card-ref' }, ref)),
    chipEl, body, status ? el('div', { class: 'status' }, status) : null);
  const field = (value, cls = '') => el('input', { class: `field big ${cls}`, value, placeholder: '数値', readonly: true, tabindex: -1 });
  const key = (t, cls = '') => el('div', { class: `key ${cls}` }, t);
  return el('div', { class: 'cz-preview' },
    el('div', { class: 'cz-bar' },
      el('div', { class: 'segs' }, el('span', { class: 'seg on' }, 'すべて'), el('span', { class: 'seg' }, '未入力')),
      el('span', { class: 'btn' }, '一覧'), el('span', { class: 'btn primary' }, '書き出し')),
    el('div', { class: 'cz-cards' },
      card('ok', '吐出圧力', 'F4', chips('区分 ポンプ', ['0.42']), field('0.41')),
      card('empty', '液面', 'F7', chips('区分 タンク', ['55']), field('', 'keypad-target')),
      card('ng', '軸受温度', 'F5', chips('管理 0～60', ['48']), field('72'), '管理値外'),
      card('ok', '異音', 'F6', chips(['良']), el('div', { class: 'choices' },
        el('span', { class: 'choice on' }, '良'), el('span', { class: 'choice' }, '否')))),
    el('div', { class: 'keypad keypad-preview' },
      el('div', { class: 'keypad-side' },
        el('div', { class: 'keypad-label' },
          el('div', { class: 'keypad-title' }, '液面'),
          el('div', { class: 'keypad-prev' }, el('span', { class: 'prev-label' }, '前回'), el('span', { class: 'prev-value' }, '55'))),
        el('div', { class: 'keypad-nav' }, key('▲', 'nav'), key('▼', 'nav')),
        key('閉じる', 'close')),
      el('div', { class: 'keypad-keys' },
        key('7'), key('8'), key('9'), key('-'), key('4'), key('5'), key('6'), key('BS', 'fn'),
        key('1'), key('2'), key('3'), key('Enter', 'next'), key('0', 'zero'), key('.'))));
}

/** カスタマイズの画面。ui: { mount, setHeader, toast, onDone } */
export function showCustomize(ui) {
  const slots = loadSlots();
  const cur = currentTheme();
  const curSlot = /^custom-(\d)$/.exec(cur)?.[1];
  let settings = { ...(curSlot != null && slots[curSlot] ? slots[curSlot].settings : PRESETS[cur] || PRESETS['']) };
  let target = curSlot != null && slots[curSlot] ? Number(curSlot) : Math.max(0, slots.findIndex((s) => !s));
  const nameInput = el('input', { class: 'field', maxlength: 12, placeholder: '名前 (例: 夜勤用)', value: slots[target]?.name || '' });

  const render = () => showTheme('custom-edit', themeVars(settings));
  const inputs = {};
  const controls = GROUPS.map(([title, items]) => el('section', { class: 'cz-group' },
    el('h2', {}, title),
    items.map(([k, label, type, min, max]) => {
      let input;
      if (type === 'color') input = el('input', { type: 'color', class: 'cz-color' });
      else if (type === 'range') input = el('input', { type: 'range', min, max, step: 1, class: 'cz-range' });
      else input = el('input', { type: 'checkbox', class: 'cz-check' });
      input.addEventListener('input', () => {
        settings[k] = type === 'check' ? input.checked : type === 'range' ? Number(input.value) : input.value;
        render();
      });
      inputs[k] = input;
      return el('label', { class: 'cz-row' }, el('span', {}, label), input);
    })));
  const paintInputs = () => {
    for (const [k, input] of Object.entries(inputs)) {
      if (input.type === 'checkbox') input.checked = !!settings[k];
      else input.value = settings[k];
    }
  };

  // 元にする外観 (用意したもの・保存したもの) を読み込む
  const bases = [...THEMES.map(([k, label]) => [label, () => ({ ...PRESETS[k] }), null]),
    ...slots.map((s, i) => (s ? [s.name, () => ({ ...s.settings }), i] : null)).filter(Boolean)];
  const baseRow = el('div', { class: 'segs cz-wrap' }, bases.map(([label, get, slot]) => el('button', {
    class: 'seg', onclick: () => {
      settings = { ...PRESETS[''], ...get() };
      if (slot != null) { target = slot; nameInput.value = slots[slot].name; paintSlots(); }
      paintInputs(); render();
    },
  }, label)));

  // 保存先 (3 件)
  const slotRow = el('div', { class: 'segs cz-wrap' });
  const delBtn = el('button', { class: 'btn ghost danger' }, '削除');
  const paintSlots = () => {
    slotRow.replaceChildren(...slots.map((s, i) => el('button', {
      class: `seg${i === target ? ' on' : ''}`,
      onclick: () => { target = i; if (slots[i]) nameInput.value = slots[i].name; paintSlots(); },
    }, `${i + 1}: ${s ? s.name : '(空き)'}`)));
    delBtn.hidden = !slots[target];
  };
  delBtn.addEventListener('click', () => {
    const s = slots[target];
    if (!s || !confirm(`保存した外観「${s.name}」を削除しますか?`)) return;
    slots[target] = null;
    saveSlots(slots);
    if (cur === `custom-${target}`) { try { localStorage.setItem('theme', ''); } catch {} }
    nameInput.value = '';
    paintSlots();
    ui.toast(`「${s.name}」を削除しました`);
  });
  const save = () => {
    const name = nameInput.value.trim() || `カスタム${target + 1}`;
    const old = slots[target];
    if (old && !confirm(`保存先 ${target + 1} の「${old.name}」を「${name}」で上書きしますか?`)) return;
    slots[target] = { name, settings: { ...settings }, vars: themeVars(settings) };
    if (!saveSlots(slots)) { ui.toast('保存できませんでした', 'error'); return; }
    applyTheme(`custom-${target}`);
    ui.toast(`「${name}」を保存して、この外観にしました`, 'ok');
    ui.onDone();
  };
  // 保存せずに戻るときは、選んでいた外観に戻す
  const leave = () => { applyTheme(currentTheme()); ui.onDone(); };

  ui.setHeader('外観のカスタマイズ', [el('button', { class: 'btn', onclick: leave }, '戻る')]);
  ui.mount(el('div', { class: 'cz' },
    preview(),
    el('div', { class: 'cz-controls' },
      el('p', { class: 'hint' }, '色や影を変えると、見本 (カードとテンキー) にすぐ反映されます。入力済の緑・範囲外の赤は変わりません。'),
      el('section', { class: 'cz-group' }, el('h2', {}, '元にする外観'), baseRow),
      controls,
      el('section', { class: 'cz-group' },
        el('h2', {}, '名前を付けて保存 (3 件まで)'),
        slotRow, nameInput,
        el('div', { class: 'cz-actions' },
          el('button', { class: 'btn primary', onclick: save }, '保存して使う'), delBtn)))));
  paintInputs();
  paintSlots();
  render();
}
