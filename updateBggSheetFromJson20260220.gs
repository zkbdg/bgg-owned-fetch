/**
 * メイン関数：BGGからデータを取得してシートを再構築する
 */
function updateBggSheetFromJson() {
  const JSON_URL = 'https://raw.githubusercontent.com/zkbdg/bgg-owned-fetch/main/bgg_collection.json';
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName('bgg-collection') || ss.insertSheet('bgg-collection');

  // --- 1. 初期化 ---
  if (sheet.getFilter()) { sheet.getFilter().remove(); }
  sheet.clear(); 
  sheet.clearConditionalFormatRules();

  sheet.getRange("A:A").setDataValidation(null);
  const checkboxValidation = SpreadsheetApp.newDataValidation().requireCheckbox().build();
  sheet.getRange("A1").setDataValidation(checkboxValidation).setValue(false);
  sheet.getRange("B1").setValue("←チェックで更新実行").setFontSize(9).setFontColor("#666666");

  // --- 2. データ取得と整形 ---
  const response = UrlFetchApp.fetch(JSON_URL);
  const data = JSON.parse(response.getContentText());
  const statusOrder = { "owned": 1, "preordered": 2, "wishlist": 3, "previouslyowned": 4 };

  const extractValue = (obj) => (obj && typeof obj === 'object' && obj.hasOwnProperty('value')) ? obj.value : obj;
  const formatNum = (val) => (val && !isNaN(val)) ? Math.round(parseFloat(val) * 100) / 100 : "";

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
      extractValue(item.name), 
      isExp ? "N/A" : (extractValue(item.numplays) || 0), 
      isExp ? "N/A" : (item.lastplay || ""),
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

  // --- 3. 書き込み ---
  const headers = ["ゲーム名", "プレイ回数", "最終プレイ日", "マイ評価", "平均評価", "ベイズ平均", "Board Game Rank", "Family Game Rank", "Weight", "最小人数", "最大人数", "プレイ時間", "出版年", "デザイナー", "メカニクス", "カテゴリー", "タイプ", "ステータス", "ID"];
  sheet.getRange(2, 1, 1, headers.length).setValues([headers]);
  
  if (finalRows.length > 0) {
    const totalRows = finalRows.length;
    const dataRange = sheet.getRange(3, 1, totalRows, headers.length);
    dataRange.setValues(finalRows);

    // リンク付与
    const richTexts = finalRows.map(row => [
      SpreadsheetApp.newRichTextValue().setText(row[0]).setLinkUrl(`https://boardgamegeek.com/boardgame/${row[18]}`).build()
    ]);
    sheet.getRange(3, 1, totalRows, 1).setRichTextValues(richTexts);

    // --- 数値書式の適用 ---
    sheet.getRange(3, 4, totalRows, 3).setNumberFormat("0.00"); // D-F: 評価 (小数2桁)
    sheet.getRange(3, 7, totalRows, 2).setNumberFormat("0");    // G-H: ランク (整数)
    sheet.getRange(3, 9, totalRows, 1).setNumberFormat("0.00"); // I: Weight (小数2桁)
    sheet.getRange(3, 10, totalRows, 4).setNumberFormat("0");   // J-M: 人数、時間、出版年 (整数)

    // 背景色の直接設定
    const bgColors = finalRows.map(row => {
      const status = row[17];
      let color = "#ffffff";
      if (status === "preordered") color = "#e6ffed";
      else if (status === "wishlist") color = "#fff3e0";
      else if (status === "previouslyowned") color = "#f5f5f5";
      return Array(headers.length).fill(color);
    });
    dataRange.setBackgrounds(bgColors);

    // --- 4. 条件付き書式 ---
    const rules = [];
    const ratingRange = sheet.getRange(3, 4, totalRows, 3);
    const rankRange = sheet.getRange(3, 7, totalRows, 2);
    const weightRange = sheet.getRange(3, 9, totalRows, 1);

    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberBetween(1, 100).setFontColor("#ff0000").setBold(true).setRanges([rankRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberLessThan(3.0).setFontColor("#2e7d32").setBold(true).setRanges([weightRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberBetween(3.0, 4.0).setFontColor("#ef6c00").setBold(true).setRanges([weightRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberGreaterThanOrEqualTo(4.0).setFontColor("#c62828").setBold(true).setRanges([weightRange]).build());

    const ratingColors = [{min: 9, bg: "#1b5e20"}, {min: 8, bg: "#4caf50"}, {min: 7, bg: "#2196f3"}, {min: 5, bg: "#9575cd"}, {min: 0.1, bg: "#f44336"}];
    ratingColors.forEach(c => {
      rules.push(SpreadsheetApp.newConditionalFormatRule().whenNumberBetween(c.min, 10).setBackground(c.bg).setFontColor("#ffffff").setRanges([ratingRange]).build());
    });
    sheet.setConditionalFormatRules(rules);

    sheet.getRange(2, 1, totalRows + 1, headers.length).createFilter();
  }

  // --- 5. 固定・列幅調整 ---
  sheet.setFrozenRows(2);
  sheet.setFrozenColumns(1);
  const widths = [250, 60, 100, 60, 70, 100, 120, 120, 80, 80, 80, 90, 60, 150, 250, 200, 100, 100, 60];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));
  sheet.getRange(2, 1, 1, headers.length).setFontWeight("bold").setBackground("#f3f3f3").setHorizontalAlignment("center");
}

function onEditTrigger(e) {
  if (!e || !e.range) return;
  if (e.range.getA1Notation() === "A1" && e.value === "TRUE") {
    e.range.setValue(false);
    updateBggSheetFromJson();
  }
}
