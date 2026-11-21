// アプリ (app/profile.js) と確認用スクリプト (dev/check_profile.py) が同じカードを組み立てるかを比べる (Claude Code での保守用)。
// profile.js の規則を変えたら、check_profile.py も直してこれで確かめる。
//
// 使い方 (先に python dev/serve.py 8765 を起動しておく):
//   node dev/check_app.js <設定.json> <点検表.xlsm> [シート名]
// 終了コード: 0 = 一致 / 1 = 違いあり
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

(async () => {
  const [prof, xlsx, sheetArg] = process.argv.slice(2);
  if (!prof || !xlsx) { console.log('使い方: node dev/check_app.js <設定.json> <点検表.xlsm> [シート名]'); process.exit(2); }
  const pyArgs = [path.join(__dirname, 'check_profile.py'), prof, xlsx, '--json', ...(sheetArg ? ['--sheet', sheetArg] : [])];
  let pyOut;
  try { pyOut = execFileSync('python3', ['-I', ...pyArgs], { encoding: 'utf8' }); } catch (e) { pyOut = e.stdout; }
  const py = JSON.parse(pyOut);
  const sheetName = sheetArg || py.sheet;

  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('http://localhost:8765/app/');
  const js = await p.evaluate(async ([pj, bytes, sheetName]) => {
    const X = await import('/app/xlsx.js');
    const P = await import('/app/profile.js');
    const wb = await X.openWorkbook(new Uint8Array(bytes).buffer);
    const sheet = await X.loadSheet(wb, wb.sheets.find((s) => s.name === sheetName));
    const r = P.buildProfileCards(sheet, JSON.parse(pj));
    return {
      warnings: r.warnings, nextCol: X.colName(r.nextCol), targetCol: X.colName(r.targetCol),
      items: r.items.map((c) => ({
        row: c.row, type: c.type, options: c.options || null, locked: c.locked, section: c.section, label: c.label,
        compact: !!c.compact, optional: !!c.optional, formula: c.formula || null, keepFormula: !!c.keepFormula,
        cond: Object.fromEntries(Object.entries(c.cond).map(([k, v]) => [k, v.option ?? v.text])), prev: c.prev, rangeText: c.rangeText,
      })),
    };
  }, [fs.readFileSync(prof, 'utf8'), [...fs.readFileSync(xlsx)], sheetName]);
  await b.close();

  const diffs = [];
  const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  if (!eq(js.warnings, py.warnings)) diffs.push(`警告: app=${JSON.stringify(js.warnings)} py=${JSON.stringify(py.warnings)}`);
  if (js.nextCol !== py.nextCol) diffs.push(`新しい記録の列: app=${js.nextCol} py=${py.nextCol}`);
  const pyItems = py.items.filter((c) => !c.excluded);
  if (!eq(js.items.map((c) => c.row), pyItems.map((c) => c.row))) diffs.push('カードの行・順番が違う');
  const byRow = new Map(pyItems.map((c) => [c.row, c]));
  for (const c of js.items) {
    const q = byRow.get(c.row);
    if (!q) continue;
    const qv = { ...q, options: q.options || null, compact: !!q.compact, optional: !!q.optional, formula: q.formula || null, keepFormula: !!q.keepFormula };
    for (const k of Object.keys(c)) if (!eq(c[k], qv[k])) diffs.push(`${c.row} 行 ${k}: app=${JSON.stringify(c[k])} py=${JSON.stringify(qv[k])}`);
  }
  console.log(`シート: ${sheetName} / カード ${js.items.length} 枚 / 警告 ${js.warnings.length} 件 / 新しい記録の列 ${js.nextCol}`);
  console.log(diffs.length ? `違い ${diffs.length} 件:\n  ${diffs.slice(0, 50).join('\n  ')}` : 'アプリと check_profile.py の結果は一致');
  process.exit(diffs.length ? 1 : 0);
})();
