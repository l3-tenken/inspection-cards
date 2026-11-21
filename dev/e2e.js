// アプリの画面で 読み込み → 入力 → 書き出し を通す確認 (Claude Code での確認用。クラウドの Playwright の Chromium を使う)。
// 書き出したファイルは dev/verify.py で元と比べる。
//
// 使い方 (先に python dev/serve.py 8765 を起動しておく):
//   node dev/e2e.js <設定.json> <点検表.xlsm> <書き出し先.xlsm> [--sheet シート名] [--values 値.json] [--prev] [--shot 画像フォルダ]
//     --values  入力する値 ({"行番号": "値", ...})。数値はテンキー、選択式はボタン、それ以外は入力欄に入れる
//     --prev    残りの数値の項目を、前回値で埋める (テンキーの Enter = 空欄なら前回値で確定)
//     --shot    列選択の画面と入力画面のスクリーンショットを保存する
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const args = process.argv.slice(2);
  const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args.splice(i, 2)[1] : null; };
  const flag = (k) => { const i = args.indexOf(k); if (i >= 0) args.splice(i, 1); return i >= 0; };
  const sheetName = opt('--sheet');
  const valuesFile = opt('--values');
  const shot = opt('--shot');
  const usePrev = flag('--prev');
  const [prof, xlsx, outFile] = args;
  if (!prof || !xlsx || !outFile) { console.log('使い方: node dev/e2e.js <設定.json> <点検表.xlsm> <書き出し先.xlsm> [--sheet シート名] [--values 値.json] [--prev] [--shot フォルダ]'); process.exit(2); }
  const values = valuesFile ? JSON.parse(fs.readFileSync(valuesFile, 'utf8')) : {};

  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1024, height: 1300 } });
  p.on('pageerror', (e) => console.log('画面のエラー:', e.message));
  await p.goto('http://localhost:8765/app/');
  await p.waitForSelector('input[accept*=json]', { state: 'attached' });
  await p.locator('input[accept*=json]').setInputFiles(prof);
  await p.waitForTimeout(800);
  await p.locator('input[accept*=xlsm]').setInputFiles(xlsx);
  await p.waitForSelector('select', { timeout: 15000 });
  await p.waitForTimeout(1500);
  const sel = p.locator('select');
  if (sheetName) { await sel.nth(1).selectOption(sheetName); await p.waitForTimeout(1500); }
  console.log('列の選択肢:', (await sel.nth(2).locator('option').allTextContents()).slice(-3).join(' / '));
  console.log((await p.locator('.setup-info').innerText()).replace(/\n+/g, ' | '));
  if (shot) await p.screenshot({ path: path.join(shot, 'setup.png') });
  if (await p.getByText('入力をはじめる').isDisabled()) { console.log('入力を始められません'); await b.close(); process.exit(1); }
  await p.getByText('入力をはじめる').click();
  await p.waitForTimeout(1500);

  // 値を入れる
  for (const [row, v] of Object.entries(values)) {
    const card = p.locator(`.card[data-row="${row}"]`);
    if (!(await card.count())) { console.log(`${row} 行のカードがありません (条件で隠れている・対象外など)`); continue; }
    const btn = card.locator('button', { hasText: String(v) });
    const input = card.locator('input');
    if (await card.locator('input[data-keypad]').count()) {
      await card.locator('input[data-keypad]').click();
      for (const ch of String(v)) await p.keyboard.press(ch);
      await p.keyboard.press('Enter');
    } else if (await btn.count()) {
      await btn.first().click();
    } else if (await input.count()) {
      await input.first().fill(String(v));
    } else {
      console.log(`${row} 行に入力できません`);
    }
    await p.waitForTimeout(100);
  }
  if (usePrev) {
    const rows = await p.$$eval('.card[data-row]', (ns) => ns.filter((n) => !n.hidden && n.querySelector('input[data-keypad]') && !n.querySelector('input[data-keypad]').value).map((n) => n.dataset.row));
    for (const row of rows) {
      await p.locator(`.card[data-row="${row}"] input[data-keypad]`).click();
      await p.keyboard.press('Enter');
    }
  }
  await p.keyboard.press('Escape');
  if (shot) await p.screenshot({ path: path.join(shot, 'cards.png'), fullPage: true });

  await p.getByText('書き出し', { exact: true }).click();
  await p.waitForTimeout(1500);
  const [dl] = await Promise.all([p.waitForEvent('download'), p.getByText('ダウンロード').click()]);
  await dl.saveAs(outFile);
  console.log('書き出し:', outFile, `(${dl.suggestedFilename()})`);
  await b.close();
})();
