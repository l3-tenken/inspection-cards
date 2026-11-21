---
name: inspection-profile
description: 点検カードの設定ファイル (点検表ごとの JSON) を作る・直す。点検表 (.xlsx/.xlsm)・設定ファイル (.json)・作業まとめ (.md) が添付され、「設定ファイルを作って」「直して」「〇〇品種の点検カード」などと頼まれたときに使う。
---

# 設定ファイルを作る・直す

手順の本体は `docs/設定ファイルの作り方.md` (ほかの AI と共通)。まずそれを全部読み、その「B. AI の手順」に従う。
あわせて `CLAUDE.md` の「守ること」と、`README.md` の「設定ファイル」を読む。

Claude Code ならではの進め方:

1. `main` を取り込む (`git fetch origin main` → 作業ブランチを `origin/main` から作る)
2. 添付ファイルはリポジトリの外 (スクラッチパッド) にコピーして扱う。点検表はダミーも含めてコミットしない
3. 補足の列を消したダミーを作る。セルを消すときは ZIP 内のシート XML から該当列の `<c>` を空にする
   (openpyxl で保存し直すと式の計算済みの値が消え、実物と違うファイルになるため)。
   実物で先の列に前もって値 (式・「-」) が入っている行は、ダミーにも同じように入れる
4. 設定ファイルを作り、`python dev/check_profile.py <設定> <ダミー> --sheet <シート>` で警告 0 件にする
5. `python dev/serve.py 8765 --ext <ダミーのフォルダ> --out <書き出し先>` を起動し、
   `node dev/e2e.js <設定> <ダミー> <書き出し.xlsm> --sheet <シート> [--values 値.json] --prev` で画面を通して書き出す。
   `python dev/verify.py <ダミー> <書き出し> <列> <シート> <前回の列>` で違いが対象列だけか確かめる
6. 設定では直せないとき: アプリを直す (CLAUDE.md に従う。`app/sw.js` の `VERSION` を上げる)。
   `app/profile.js` を変えたら `dev/check_profile.py` も同じ規則に直し、`node dev/check_app.js <設定> <ダミー> <シート>` で一致を確かめる。
   新しい設定の項目は README.md・`docs/設定ファイルの作り方.md` の「C. 補足の書き方」にも足す。PR を作って `main` にマージする
7. 設定ファイルと作業まとめを `SendUserFile` で送り、保管を頼む (GitHub には上げない)。
   作業まとめは添付されたものに追記する (なければ新しく作る)
