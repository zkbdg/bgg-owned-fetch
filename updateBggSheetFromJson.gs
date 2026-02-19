/**
 * スプレッドシートを開いた時に実行される関数
 * 専用メニューを作成します
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🎲 BGG管理')
    .addItem('最新データに更新', 'updateBggSheetFromJson')
    .addToUi();
}

/**
 * GitHubのJSONからデータを取得し、シートを更新します。
 */
function updateBggSheetFromJson() {
  const JSON_URL = 'https://raw.githubusercontent.com/zkbdg/bgg-owned-fetch/main/bgg_collection.json';
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('bgg-collection') || ss.insertSheet('bgg-collection');

  const headers = [
    "ゲーム名", "プレイ回数", "最終プレイ日", "マイ評価", "平均評価", "ベイズ平均", 
    "Board Game Rank", "Family Game Rank", "Weight", "最小人数", "最大人数", 
    "プレイ時間", "出版年", "デザイナー", "メカニクス", "カテゴリー", "タイプ", "ステータス", "ID"
  ];

  const response = UrlFetchApp.fetch(JSON_URL);
  const data = JSON.parse(response.getContentText());

  const statusOrder = { "owned": 1, "preordered": 2, "wishlist": 3, "previouslyowned": 4 };

  const formatNum = (val) => {
    if (val === undefined || val === null || val === "" || val === "NaN" || val == 0) return "";
    if (!isNaN(val)) return Math.round(parseFloat(val) * 100) / 100;
    return val;
  };

  const extractValue = (obj) => {
    return (obj && typeof obj === 'object' && obj.hasOwnProperty('value')) ? obj.value : obj;
  };

  let finalRows = data.map(item => {
    const stats = item.stats || {};
    const rating = stats.rating || {};
    let ranksArray = [];
    if (rating.ranks && rating.ranks.rank) {
      ranksArray = Array.isArray(rating.ranks.rank) ? rating.ranks.rank : [rating.ranks.rank];
    }
    const getRankValue = (type) => {
      const r = ranksArray.find(r => r.name === type);
      const val = r ? extractValue(r) : "N/A";
      return (val !== "0" && val !== "Not Ranked") ? val : "N/A";
    };

    const isExpansion = (item.type === "boardgameexpansion");
    const numPlays = isExpansion ? "N/A" : (extractValue(item.numplays) || 0);
    const lastPlay = isExpansion ? "N/A" : (item.lastplay || "");

    return [
      extractValue(item.name),        // [0]
      numPlays,                       // [1]
      lastPlay,                       // [2]
      extractValue(rating.value),     // [3]
      formatNum(extractValue(rating.average)),     // [4]
      formatNum(extractValue(rating.bayesaverage)), // [5]
      getRankValue('boardgame'),      // [6] Board Game Rank
      getRankValue('familygames'),    // [7]
      formatNum(item.weight),         // [8] Weight
      stats.minplayers,               // [9] 最小人数
      stats.maxplayers,               // [10]
      stats.playingtime,              // [11]
      extractValue(item.yearpublished),// [12]
      (item.designers || []).join(', '),
      (item.mechanics || []).join(', '),
      (item.categories || []).join(', '),
      item.type || "",
      item.status || "",              // [17]
      item.objectid                   // [18]
    ];
  });

  // ソート処理
  finalRows.sort((a, b) => {
    const orderA = statusOrder[a[17]] || 99;
    const orderB = statusOrder[b[17]] || 99;
    if (orderA !== orderB) return orderA - orderB;
    const dateA = a[2], dateB = b[2];
    const isNoDateA = (!dateA || dateA === "N/A" || dateA.toString().trim() === "");
    const isNoDateB = (!dateB || dateB === "N/A" || dateB.toString().trim() === "");
    if (isNoDateA && isNoDateB) return a[0].localeCompare(b[0]);
    if (isNoDateA) return 1;
    if (isNoDateB) return -1;
    if (dateA > dateB) return -1;
    if (dateA < dateB) return 1;
    return a[0].localeCompare(b[0]);
  });

  sheet.clear();
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  
  if (finalRows.length > 0) {
    const range = sheet.getRange(2, 1, finalRows.length, headers.length);
    range.setValues(finalRows);

    const richTextValues = finalRows.map(row => [
      SpreadsheetApp.newRichTextValue().setText(row[0]).setLinkUrl(`https://boardgamegeek.com/boardgame/${row[18]}`).build()
    ]);
    sheet.getRange(2, 1, finalRows.length, 1).setRichTextValues(richTextValues);

    const bgColors = [], fontColors = [], fontWeights = [];
    finalRows.forEach((row) => {
      const status = row[17];
      let defaultBg = (status === "preordered") ? "#e6ffed" : (status === "wishlist") ? "#fff3e0" : (status === "previouslyowned") ? "#f5f5f5" : null;
      const rBg = [], rFont = [], rWeight = [];
      row.forEach((cell, i) => {
        let cBg = defaultBg, cFont = "#000000", cWeight = "normal";
        if (i >= 3 && i <= 5 && cell !== "" && !isNaN(cell)) {
          const s = parseFloat(cell); cFont = "#ffffff";
          if (s < 5) cBg = "#f44336"; else if (s < 7) cBg = "#9575cd"; else if (s < 8) cBg = "#2196f3"; else if (s < 9) cBg = "#4caf50"; else cBg = "#1b5e20";
        }
        if ((i === 6 || i === 7) && cell !== "N/A" && !isNaN(cell) && parseInt(cell) <= 100) { cFont = "#ff0000"; cWeight = "bold"; }
        if (i === 8 && cell !== "" && !isNaN(cell)) {
          const w = parseFloat(cell); cWeight = "bold";
          if (w < 3.0) cFont = "#4caf50"; else if (w < 4.0) cFont = "#ffa000"; else cFont = "#f44336";
        }
        rBg.push(cBg); rFont.push(cFont); rWeight.push(cWeight);
      });
      bgColors.push(rBg); fontColors.push(rFont); fontWeights.push(rWeight);
    });
    range.setBackgrounds(bgColors); range.setFontColors(fontColors); range.setFontWeights(fontWeights);

    // --- 【修正】表示形式の設定 ---
    // マイ評価・平均評価・ベイズ平均（D-F列）は小数点2位
    sheet.getRange(2, 4, finalRows.length, 3).setNumberFormat("0.00");
    // Board Game Rank (G列)・Family Game Rank (H列) は整数
    sheet.getRange(2, 7, finalRows.length, 2).setNumberFormat("0");
    // Weight (I列) は小数点2位
    sheet.getRange(2, 9, finalRows.length, 1).setNumberFormat("0.00");
    // 最小・最大人数・時間・年 (J-M列) は整数
    sheet.getRange(2, 10, finalRows.length, 4).setNumberFormat("0");
  }

  sheet.setFrozenRows(1); sheet.setFrozenColumns(1);
  const widths = [250, 80, 100, 60, 70, 100, 120, 120, 80, 80, 80, 90, 60, 150, 250, 200, 100, 100, 60];
  widths.forEach((w, i) => sheet.setColumnWidth(i + 1, w));
  sheet.getRange(1, 1, sheet.getLastRow(), headers.length).setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold").setHorizontalAlignment("center").setBackground("#f3f3f3");
  
  SpreadsheetApp.getUi().alert('書式を修正して更新しました！');
}
