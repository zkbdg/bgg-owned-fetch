import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"
URL = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": os.environ["BGG_COOKIE"]
}

print("Fetching BGG collection...")

# Accepted 待機
for i in range(15):
    resp = requests.get(URL, headers=headers, timeout=60)

    if resp.status_code == 202 or not resp.text.strip():
        print(f"[{i+1}/15] Waiting...")
        time.sleep(5)
        continue

    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    break
else:
    raise Exception("BGG timeout")

# ====================================
# XML → dict 再帰変換
# ====================================
def xml_to_dict(element):
    d = {}
    # 属性を dict に追加
    if element.attrib:
        d.update(element.attrib)
    # 子タグがある場合
    children = list(element)
    if children:
        for child in children:
            child_dict = xml_to_dict(child)
            # 同じタグ名が複数ある場合はリスト化
            if child.tag in d:
                if not isinstance(d[child.tag], list):
                    d[child.tag] = [d[child.tag]]
                d[child.tag].append(child_dict)
            else:
                d[child.tag] = child_dict
    else:
        # 子タグがない場合はテキストを格納
        text = element.text.strip() if element.text else None
        if text:
            d["value"] = text
    return d

# ====================================
# 全アイテムを dict に変換
# ====================================
games = [xml_to_dict(item) for item in root.findall("item")]

# 保存
with open("owned_full.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)

print(f"{len(games)} games saved to owned_full.json")
