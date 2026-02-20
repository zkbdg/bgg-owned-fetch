function updateBggSheetFromJson() {
  const JSON_URL = 'https://raw.githubusercontent.com/zkbdg/bgg-owned-fetch/main/bgg_collection.json';
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName('bgg-collection') || ss.insertSheet('bgg-collection');

  // --- 1. 初期化（フィルタと書式をクリア） ---
  if (sheet.getFilter()) { sheet.getFilter().remove(); }
  sheet.clear(); 
  sheet.clearConditionalFormatRules(); // 既存の条件付き書式をリセット

  const headers = ["ゲーム名", "プレイ回数", "最終プレイ日", "マイ評価", "平均評価", "ベイズ平均", "Board Game Rank", "Family Game Rank", "Weight", "最小人数", "最大人数", "プレイ時間", "出版年", "デザイナー", "メカニクス", "カテゴリー", "タイプ", "ステータス", "ID"];

  const response = UrlFetchApp.fetch(JSON_URL);
  const data = JSON.parse(response.getContentText());
  const statusOrder = { "owned": 1, "preordered": 2, "wishlist": 3, "previouslyowned": 4 };

  const formatNum = (val) => (val && !isNaN(val)) ? Math.round(parseFloat(val) * 100) / 100 : "";
  const extractValue = (obj) => (obj && typeof obj === 'object' && obj.hasOwnProperty('value')) ? obj.value : obj;

  let finalRows = data.map(item => {
    const stats = item.stats || {};
    const rating = stats.rating || {};
    let ranksArray = Array.isArray(rating.ranks?.rank) ? rating.ranks.rank : [rating.ranks?.rank];
    const getRank = (type) => {
      const r = ranksArray.find(r => r && r.name === type);
      const val = extractValue(r);
      return (val && val !== "0" && val !== "Not Ranked") ? val : "N/A";
    };
    const isExp = (item.type === "boardgameexpansion");
    return [
      extractValue(item.name), isExp ? "N/A" : (extractValue(item.numplays) || 0), isExp ? "N/A" : (item.lastplay || ""),
      extractValue(rating.value), formatNum(extractValue(rating.average)), formatNum(extractValue(rating.bayesaverage)),
      getRank('boardgame'), getRank('familygames'), formatNum(item.weight),
      stats.minplayers, stats.maxplayers, stats.playingtime, extractValue(item.yearpublished),
      (item.designers || []).join(', '), (item.mechanics || []).join(', '), (item.categories || []).join(', '),
      item.type || "", item.status || "", item.objectid
    ];
  });

  // ソート
  finalRows.sort((a, b) => {
    const orderA = statusOrder[a[17]] || 99, orderB = statusOrder[b[17]] || 99;
    if (orderA !== orderB) return orderA - orderB;
    const dateA = a[2], dateB = b[2];
    const isNoA = (!dateA || dateA === "N/A"), isNoB = (!dateB || dateB === "N/A");
    if (isNoA && isNoB) return a[0].localeCompare(b[0]);
    if (isNoA) return 1; if (isNoB) return -1;
    return dateB.localeCompare(dateA) || a[0].localeCompare(b[0]);
  });

  // --- 2. データ流し込み ---
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  if (finalRows.length > 0) {
    const totalRows = finalRows.length;
    const range = sheet.getRange(2, 1, totalRows, headers.length);
    range.setValues(finalRows);

    // リンク
    const richTexts = finalRows.map(row => [
      SpreadsheetApp.newRichTextValue().setText(row[0]).setLinkUrl(`https://boardgamegeek.com/boardgame/${row[18]}`).build()
    ]);
    sheet.getRange(2, 1, totalRows, 1).setRichTextValues(richTexts);

    // 数値形式
    sheet.getRange(2, 4, totalRows, 3).setNumberFormat("0.00");
    sheet.getRange(2, 7, totalRows, 2).setNumberFormat("0");
    sheet.getRange(2, 9, totalRows, 1).setNumberFormat("0.00");
    sheet.getRange(2, 10, totalRows, 4).setNumberFormat("0");

    // --- 3. 【新機能】条件付き書式の設定 ---
    const rules = [];
    const fullRange = sheet.getRange(2, 1, totalRows, headers.length);
    const ratingRange = sheet.getRange(2, 4, totalRows, 3); // D-F列
    const rankRange = sheet.getRange(2, 7, totalRows, 2);   // G-H列
    const weightRange = sheet.getRange(2, 9, totalRows, 1); // I列

    // A: ステータス別の行背景色 (R列を参照して行全体に適用)
    // 優先順位があるため配列にプッシュ
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=$R2="preordered"').setBackground("#e6ffed").setRanges([fullRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=$R2="wishlist"').setBackground("#fff3e0").setRanges([fullRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=$R2="previouslyowned"').setBackground("#f5f5f5").setRanges([fullRange]).build());

    // B: 評価(D,E,F列)のスコア色
    const ratingColors = [
      {min: 9, max: 10, bg: "#1b5e20"}, {min: 8, max: 9, bg: "#4caf50"},
      {min: 7, max: 8, bg: "#2196f3"}, {min: 5, max: 7, bg: "#9575cd"},
      {min: 0.1, max: 5, bg: "#f44336"}
    ];
    ratingColors.forEach(c => {
      rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberBetween(c.min, c.max).setBackground(c.bg).setFontColor("#ffffff").setRanges([ratingRange]).build());
    });

    // C: ランク(G,H列) 100位以内
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberBetween(1, 100).setFontColor("#ff0000").setBold(true).setRanges([rankRange]).build());

    // D: Weight(I列) の色
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberLessThan(3.0).setFontColor("#4caf50").setBold(true).setRanges([weightRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberBetween(3.0, 4.0).setFontColor("#ffa000").setBold(true).setRanges([weightRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberGreaterThanOrEqualTo(4.0).setFontColor("#f44336").setBold(true).setRanges([weightRange]).build());

    sheet.setConditionalFormatRules(rules);

    // フィルタ設置（1行目から）
    sheet.getRange(1, 1, totalRows + 1, headers.length).createFilter();
  }

  // 装飾（最低限）
  sheet.setFrozenRows(1);
  sheet.setFrozenColumns(1);
  const widths = [250, 60, 100, 60, 70, 100, 120, 120, 80, 80, 80, 90, 60, 150, 250, 200, 100, 100, 60];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));
  sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#f3f3f3").setHorizontalAlignment("center");
  sheet.getRange(1, 1, sheet.getLastRow() || 1, headers.length).setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP);

  console.log("更新完了：条件付き書式で色分けを再現しました。");
}
