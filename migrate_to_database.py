"""
migrate_to_database.py
======================
一次性資料遷移腳本：
將 data/ 目錄下所有現有的 task_*.csv 與 results.csv 中的歷史資料，
合併進永久資料庫 data/database.csv。

使用方式：
  python migrate_to_database.py

可以在 GitHub Actions 的 auto_scraper.yml 中，於執行 auto_scraper.py 之前先跑一次，
或在本機執行一次後將 database.csv commit 上去即可，後續無須再執行此腳本。
"""

import csv
import os
import glob

DATABASE_FILE = 'data/database.csv'
DB_HEADERS = ['搜尋關鍵字', '招標類型', '公告日期', '機關名稱', '標案案號', '標案名稱', '採購性質', '截止投標', '預算金額', '連結']
DB_UNIQUE_KEYS = ['招標類型', '標案案號', '公告日期']

def load_existing_database():
    """讀取現有 database.csv，回傳 dict {unique_key: row_dict}"""
    existing = {}
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = tuple(row.get(k, '').strip() for k in DB_UNIQUE_KEYS)
                existing[key] = row
        print(f"  📂 已載入現有資料庫：{len(existing)} 筆")
    return existing


def write_database(records_dict):
    """將 records_dict 依公告日期排序後寫入 database.csv"""
    os.makedirs('data', exist_ok=True)
    all_rows = list(records_dict.values())
    try:
        all_rows.sort(key=lambda r: r.get('公告日期', ''), reverse=True)
    except Exception:
        pass

    with open(DATABASE_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=DB_HEADERS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"  💾 已寫入 {DATABASE_FILE}，共 {len(all_rows)} 筆")


def migrate_task_csv(filepath, existing_records):
    """
    從 task_*.csv 讀取資料（欄位：招標類型,公告日期,機關名稱,標案案號,標案名稱,採購性質,截止投標,預算金額,連結）
    並合併進 existing_records。
    回傳 (新增筆數, 略過筆數)
    """
    added = 0
    skipped = 0
    # 從檔名猜測關鍵字（無法得知，留空）
    keyword_hint = ''

    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for row in reader:
                # task_*.csv 欄位：招標類型, 公告日期, 機關名稱, 標案案號, 標案名稱, 採購性質, 截止投標, 預算金額, 連結
                record = {
                    '搜尋關鍵字': row.get('搜尋關鍵字', keyword_hint).strip(),
                    '招標類型':   row.get('招標類型', '').strip(),
                    '公告日期':   row.get('公告日期', '').strip(),
                    '機關名稱':   row.get('機關名稱', '').strip(),
                    '標案案號':   row.get('標案案號', '').strip(),
                    '標案名稱':   row.get('標案名稱', '').strip(),
                    '採購性質':   row.get('採購性質', '').strip(),
                    '截止投標':   row.get('截止投標', '').strip(),
                    '預算金額':   row.get('預算金額', '').strip(),
                    '連結':       row.get('連結', '').strip(),
                }
                key = tuple(record.get(k, '') for k in DB_UNIQUE_KEYS)
                if not any(key):  # 空行跳過
                    continue
                if key not in existing_records:
                    existing_records[key] = record
                    added += 1
                else:
                    skipped += 1
    except Exception as e:
        print(f"  ⚠️  讀取 {filepath} 失敗：{e}")

    return added, skipped


def migrate_results_csv(filepath, existing_records):
    """
    從舊版 results.csv 讀取資料（欄位：公告日期,機關名稱,標案案號,標案名稱,採購性質,截止投標,預算金額,連結，無招標類型欄）
    招標類型統一填入「招標公告」（舊版 scraper 預設）。
    """
    added = 0
    skipped = 0

    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                record = {
                    '搜尋關鍵字': '',
                    '招標類型':   row.get('招標類型', '招標公告').strip() or '招標公告',
                    '公告日期':   row.get('公告日期', '').strip(),
                    '機關名稱':   row.get('機關名稱', '').strip(),
                    '標案案號':   row.get('標案案號', '').strip(),
                    '標案名稱':   row.get('標案名稱', '').strip(),
                    '採購性質':   row.get('採購性質', '').strip(),
                    '截止投標':   row.get('截止投標', '').strip(),
                    '預算金額':   row.get('預算金額', '').strip(),
                    '連結':       row.get('連結', '').strip(),
                }
                key = tuple(record.get(k, '') for k in DB_UNIQUE_KEYS)
                if not any(key):
                    continue
                if key not in existing_records:
                    existing_records[key] = record
                    added += 1
                else:
                    skipped += 1
    except Exception as e:
        print(f"  ⚠️  讀取 {filepath} 失敗：{e}")

    return added, skipped


if __name__ == '__main__':
    print("🚀 開始資料遷移：將現有 CSV 歷史資料匯入永久資料庫...\n")

    existing_records = load_existing_database()

    total_added = 0
    total_skipped = 0

    # 處理所有 task_*.csv
    task_files = sorted(glob.glob('data/task_*.csv'))
    if task_files:
        print(f"\n📁 找到 {len(task_files)} 個任務 CSV 檔案，開始合併...")
        for filepath in task_files:
            added, skipped = migrate_task_csv(filepath, existing_records)
            total_added += added
            total_skipped += skipped
            print(f"  ✅ {os.path.basename(filepath)}: 新增 {added} 筆，略過重複 {skipped} 筆")
    else:
        print("  ℹ️  沒有找到 task_*.csv 檔案")

    # 處理舊版 results.csv（若存在）
    results_path = 'data/results.csv'
    if os.path.exists(results_path):
        print(f"\n📁 找到舊版 results.csv，開始合併...")
        added, skipped = migrate_results_csv(results_path, existing_records)
        total_added += added
        total_skipped += skipped
        print(f"  ✅ results.csv: 新增 {added} 筆，略過重複 {skipped} 筆")

    # 寫出資料庫
    print(f"\n💾 正在寫入資料庫...")
    write_database(existing_records)

    print(f"\n🎉 遷移完成！")
    print(f"   總計新增: {total_added} 筆")
    print(f"   略過重複: {total_skipped} 筆")
    print(f"   資料庫總筆數: {len(existing_records)} 筆")
    print(f"\n📌 請將 data/database.csv commit 並 push 到 GitHub，之後 auto_scraper.py 會自動維護這個檔案。")
