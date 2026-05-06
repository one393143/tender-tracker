import requests
from bs4 import BeautifulSoup
import csv
import os
import json
import glob
import random
import time
import smtplib  # 👈 寄信模組
from email.mime.text import MIMEText  # 👈 信件內容模組
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote
from datetime import datetime, timedelta

# --- 資料庫相關設定 ---
DATABASE_FILE = 'data/database.csv'
# 基本欄位（來自搜尋列表）
DB_BASE_HEADERS = ['搜尋關鍵字', '招標類型', '公告日期', '機關名稱', '標案案號', '標案名稱', '採購性質', '截止投標', '預算金額', '連結']
# 詳細欄位（來自個別標案頁面）
DB_DETAIL_HEADERS = ['機關地址', '聯絡人', '聯絡電話', '電子郵件信箱', '決標方式', '附加說明', '詳細資料狀態']
DB_HEADERS = DB_BASE_HEADERS + DB_DETAIL_HEADERS
# 唯一鍵：這三欄組合一致才算「完全相同」，任一不同就是不同記錄
DB_UNIQUE_KEYS = ['招標類型', '標案案號', '公告日期']
# 詳細爬蟲設定（保守值，避免觸發驗證碼）
DETAIL_MAX_PER_RUN = 5    # 每次排程最多補充幾筆詳細資料
DETAIL_MIN_DELAY  = 15   # 最短間隔（秒）
DETAIL_MAX_DELAY  = 25   # 最長間隔（秒，隨機抖動）

# --- 1. 自動計算過去 30 天的日期 ---
today = datetime.now()
thirty_days_ago = today - timedelta(days=30)

start_date_str = thirty_days_ago.strftime("%Y/%m/%d")
end_date_str = today.strftime("%Y/%m/%d")

encoded_start = quote(start_date_str, safe='')
encoded_end = quote(end_date_str, safe='')

# --- 2. 模擬瀏覽器 Header ---
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 政府採購網的招標類型代碼對應
TYPE_MAP = {
    "招標公告": "TENDER_DECLARATION",
    "公開徵求": "TENDER_PUBLIC_REQ",
    "公開閱覽": "READINGS",
    "政府採購預告": "PREDICTION"
}

# --- 3. 寄信功能函數 (已更新為支援多收件者) ---
def send_notification(task_count, total_records, details_text):
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    receiver_emails_raw = os.environ.get('EMAIL_RECEIVER')

    if not sender_email or not sender_password or not receiver_emails_raw:
        print("⚠️ 未完整設定 Email 機密變數 (USER, PASS, 或 RECEIVER)，跳過寄送通知信。")
        return

    # 將逗號隔開的字串轉為清單，並去除空格
    receiver_list = [email.strip() for email in receiver_emails_raw.split(',')]

    print(f"📧 準備寄送系統通知信至: {', '.join(receiver_list)}")
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_emails_raw # 在郵件軟體中顯示所有收件者
    msg['Subject'] = f"🔔 政府採購網自動查詢完成 (發現 {total_records} 筆)"

    # 取得 Repo 資訊來動態生成網址 (由 GitHub Actions 自動提供)
    repo_full_name = os.environ.get('GITHUB_REPOSITORY', 'your-username/tender-tracker')
    owner = repo_full_name.split('/')[0]
    repo_name = repo_full_name.split('/')[1]
    dashboard_url = f"https://{owner}.github.io/{repo_name}/scheduled.html"

    body = (
        f"您的自動採購查詢排程已執行完畢！\n\n"
        f"🕒 查詢區間：{start_date_str} ~ {end_date_str}\n"
        f"📊 執行任務數：{task_count} 項\n"
        f"🎯 總計標案數：{total_records} 筆\n\n"
        f"--- 各任務詳細統計 ---\n{details_text}\n"
        f"👉 請至您的管理中心查看詳細資料：\n{dashboard_url}"
    )
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        # 使用 to_addrs 參數傳入清單，確保每個人都收到
        server.send_message(msg, to_addrs=receiver_list)
        server.quit()
        print("✅ 通知信寄送成功！")
    except Exception as e:
        print(f"❌ 寄信失敗：{e}")


def merge_into_database(new_rows_with_keyword):
    """
    將新抓到的資料合併進 database.csv，以 DB_UNIQUE_KEYS 作為唯一鍵去重。
    new_rows_with_keyword: list of dict，每個 dict 的 key 對應 DB_HEADERS
    回傳: (新增筆數, 略過重複筆數)
    """
    os.makedirs('data', exist_ok=True)
    existing_records = {}  # key: (招標類型, 標案案號, 公告日期) -> row dict

    # 讀取現有資料庫
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                unique_key = tuple(row.get(k, '').strip() for k in DB_UNIQUE_KEYS)
                existing_records[unique_key] = row

    added_count = 0
    skipped_count = 0

    for row in new_rows_with_keyword:
        unique_key = tuple(row.get(k, '').strip() for k in DB_UNIQUE_KEYS)
        if unique_key not in existing_records:
            existing_records[unique_key] = row
            added_count += 1
        else:
            skipped_count += 1

    # 依照公告日期由新到舊排序後寫回
    all_rows = list(existing_records.values())
    try:
        all_rows.sort(key=lambda r: r.get('公告日期', ''), reverse=True)
    except Exception:
        pass  # 排序失敗時保持原順序

    with open(DATABASE_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=DB_HEADERS, extrasaction='ignore')
        writer.writeheader()
        # 確保每筆資料都有完整欄位（舊資料沒有詳細欄位時補空字串）
        for r in all_rows:
            for h in DB_HEADERS:
                r.setdefault(h, '')
            writer.writerow(r)

    return added_count, skipped_count


def scrape_task(task):
    task_id = str(task.get('id', 'default'))
    keyword = task.get('keyword', '')
    types = task.get('types', ["招標公告"])

    encoded_keyword = quote(keyword)
    all_data = []  # list of list，欄位順序: [招標類型, 公告日期, 機關名稱, 標案案號, 標案名稱, 採購性質, 截止投標, 預算金額, 連結]

    print(f"🚀 開始執行任務: [{keyword}], 搜尋過去30天 ({start_date_str} ~ {end_date_str})")

    session = requests.Session()
    try:
        session.get("https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic", headers=headers, timeout=10)
    except Exception:
        print("連線首頁失敗")
        return 0

    for t_name in types:
        tender_type_code = TYPE_MAP.get(t_name, "TENDER_DECLARATION")
        print(f"  👉 正在查詢: {t_name}")

        url = (
            f"https://web.pcc.gov.tw/prkms/tender/common/basic/readTenderBasic?"
            f"pageSize=100&firstSearch=true&searchType=basic&isBinding=N&isLogIn=N&level_1=on"
            f"&tenderName={encoded_keyword}&tenderType={tender_type_code}&tenderWay=TENDER_WAY_ALL_DECLARATION"
            f"&dateType=isDate&tenderStartDate={encoded_start}&tenderEndDate={encoded_end}"
        )

        try:
            response = session.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', {'id': 'tpam'})
                if table:
                    rows = table.find_all('tr')
                    for row in rows[1:]:
                        cols = row.find_all('td')
                        if len(cols) >= 10:
                            org_name = cols[1].text.strip()

                            # cols[2] 案號
                            case_no = cols[2].contents[0].strip()

                            nature = cols[5].text.strip()
                            date = cols[6].text.strip()
                            deadline = cols[7].text.strip()
                            budget = cols[8].text.strip()

                            # 由最後一欄擷取連結與標案名稱 (閃避 JS 混淆)
                            link_tag = cols[9].find('a')
                            link = f"https://web.pcc.gov.tw{link_tag['href']}" if link_tag else ""
                            case_name = ""
                            if link_tag and 'title' in link_tag.attrs:
                                case_name = link_tag['title'].replace('檢視 標案名稱:', '').strip()

                            all_data.append([t_name, date, org_name, case_no, case_name, nature, deadline, budget, link])
        except Exception as e:
            print(f"    ❌ 查詢 {t_name} 發生錯誤: {e}")

    # --- 寫入本次查詢結果 (task_*.csv，每次覆蓋，僅保留近30天) ---
    os.makedirs('data', exist_ok=True)
    filename = f"data/task_{task_id}.csv"
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['招標類型', '公告日期', '機關名稱', '標案案號', '標案名稱', '採購性質', '截止投標', '預算金額', '連結'])
        writer.writerows(all_data)

    print(f"  📄 本次結果已存入 {filename}（{len(all_data)} 筆）")

    # --- 合併進永久資料庫 (database.csv) ---
    # 將 list of list 轉換為 list of dict 以便 merge 函式使用
    rows_for_db = []
    for row in all_data:
        # row 欄位順序: [招標類型, 公告日期, 機關名稱, 標案案號, 標案名稱, 採購性質, 截止投標, 預算金額, 連結]
        rows_for_db.append({
            '搜尋關鍵字': keyword,
            '招標類型':   row[0],
            '公告日期':   row[1],
            '機關名稱':   row[2],
            '標案案號':   row[3],
            '標案名稱':   row[4],
            '採購性質':   row[5],
            '截止投標':   row[6],
            '預算金額':   row[7],
            '連結':       row[8],
        })

    added, skipped = merge_into_database(rows_for_db)
    print(f"  🗄️ 資料庫更新: 新增 {added} 筆，略過重複 {skipped} 筆\n")

    print(f"✅ 任務 [{keyword}] 完成，共抓到 {len(all_data)} 筆\n")
    return len(all_data)


# ═══════════════════════════════════════════════════════════════
# 詳細資訊爬蟲（保守版，避免觸發驗證碼）
# ═══════════════════════════════════════════════════════════════

DETAIL_HEADERS_REQ = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Referer": "https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic",
}

def _detail_clean(text):
    return ' '.join((text or '').split()).strip()

def _find_field(soup, table_class, label):
    tbl = soup.find('table', class_=table_class)
    if not tbl:
        return ''
    for row in tbl.find_all('tr'):
        cells = row.find_all(['th', 'td'])
        if len(cells) >= 2 and _detail_clean(cells[0].get_text()) == label:
            return _detail_clean(cells[1].get_text(' '))
    return ''

def _extract_prkms(soup):
    """從新版 prkms 詳細頁解析所有詳細欄位"""
    result = {h: '' for h in DB_DETAIL_HEADERS}
    result['機關地址']     = _find_field(soup, 'tb_01', '機關地址')
    result['聯絡人']       = _find_field(soup, 'tb_01', '聯絡人')
    result['電子郵件信箱'] = _find_field(soup, 'tb_01', '電子郵件信箱')
    tbl01 = soup.find('table', class_='tb_01')
    if tbl01:
        for row in tbl01.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2 and _detail_clean(cells[0].get_text()) == '聯絡電話':
                result['聯絡電話'] = _detail_clean(cells[1].get_text(' '))
                break
    result['決標方式'] = _find_field(soup, 'tb_05', '決標方式')
    tbl07 = soup.find('table', class_='tb_07')
    if tbl07:
        note_parts, in_note = [], False
        for row in tbl07.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if not cells:
                continue
            label = _detail_clean(cells[0].get_text())
            if label == '附加說明':
                in_note = True
                for c in cells[1:]:
                    t = _detail_clean(c.get_text())
                    if t and t not in note_parts:
                        note_parts.append(t)
            elif in_note and len(cells) == 1:
                t = _detail_clean(cells[0].get_text())
                if t and t not in note_parts:
                    note_parts.append(t)
            elif in_note:
                break
        result['附加說明'] = ' | '.join(note_parts)
    if result['機關地址'] or result['聯絡人']:
        result['詳細資料狀態'] = '✅ 已擷取'
    else:
        result['詳細資料狀態'] = '⚠️ prkms但欄位空白'
    return result

def enrich_database_details(max_per_run=DETAIL_MAX_PER_RUN):
    """
    增量補充 database.csv 中缺少詳細資料的記錄。
    排序策略：先抓最新的未補充記錄，補完後往回抓舊的，直到滿 max_per_run 筆或資料見底。
    嚴格限速：每筆間隔 DETAIL_MIN_DELAY~DETAIL_MAX_DELAY 秒（隨機），偵測驗證碼即停止。
    """
    if not os.path.exists(DATABASE_FILE):
        print("⏭️ 詳細資料補充：資料庫不存在，跳過。")
        return

    # 讀取現有資料庫
    with open(DATABASE_FILE, 'r', encoding='utf-8-sig') as f:
        all_rows = list(csv.DictReader(f))
    for r in all_rows:
        for h in DB_HEADERS:
            r.setdefault(h, '')

    # 以連結去重，找出「尚未補充且可能可以補充」的唯一 URL
    # 條件：詳細資料狀態 為空 或 非「已擷取」且非「舊版跳過」
    seen_urls = set()
    to_enrich = []  # list of (url, row_index)
    skip_statuses = {'✅ 已擷取', '⏭️ 舊版頁面(tps)', '⚠️ prkms但欄位空白'}
    for i, row in enumerate(all_rows):
        url = row.get('連結', '').strip()
        status = row.get('詳細資料狀態', '').strip()
        if url and url not in seen_urls and status not in skip_statuses:
            seen_urls.add(url)
            to_enrich.append((url, i))

    if not to_enrich:
        print("✅ 詳細資料：所有可補充記錄均已處理。")
        return

    # 依公告日期新→舊排序（先補最新的，再往回補）
    to_enrich.sort(key=lambda t: all_rows[t[1]].get('公告日期', ''), reverse=True)
    batch = to_enrich[:max_per_run]

    print(f"\n🔍 詳細資料補充：待補 {len(to_enrich)} 筆，本次最多 {max_per_run} 筆")
    print(f"   間隔: {DETAIL_MIN_DELAY}~{DETAIL_MAX_DELAY} 秒（隨機）\n")

    # 建立 Session
    detail_session = requests.Session()
    try:
        detail_session.get("https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic",
                           headers=DETAIL_HEADERS_REQ, timeout=12)
        print("   ✅ 詳細資料 Session 已建立")
        time.sleep(3)  # 建立後先等一下
    except Exception as e:
        print(f"   ⚠️ 首頁連線失敗: {e}")

    # 建立 url → detail 對應（同一 URL 只爬一次，結果套用到所有相同連結的列）
    url_detail_cache = {}
    enriched_count = 0
    captcha_hit = False

    for url, _ in batch:
        case_row = all_rows[_]
        case_no   = case_row.get('標案案號', '')
        case_name = case_row.get('標案名稱', '')[:20]
        print(f"   [{enriched_count+1}/{len(batch)}] {case_no} {case_name}")

        try:
            resp = detail_session.get(url, headers=DETAIL_HEADERS_REQ, timeout=25, allow_redirects=True)
            final_url = resp.url

            if '驗證碼' in resp.text or 'captcha' in resp.text.lower():
                print(f"   🛑 觸發驗證碼！立即停止詳細資料補充。")
                url_detail_cache[url] = {'詳細資料狀態': '🛑 觸發驗證碼'}
                captcha_hit = True
                break

            if resp.status_code != 200:
                print(f"   ❌ HTTP {resp.status_code}")
                url_detail_cache[url] = {'詳細資料狀態': f'❌ HTTP {resp.status_code}'}
            elif 'prkms' in final_url and 'tps' not in final_url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                detail = _extract_prkms(soup)
                url_detail_cache[url] = detail
                status = detail.get('詳細資料狀態', '')
                print(f"   {status} | {detail.get('聯絡人','')} | {detail.get('電子郵件信箱','')}")
                enriched_count += 1
            else:
                print(f"   ⏭️ 舊版頁面(tps)，跳過")
                url_detail_cache[url] = {'詳細資料狀態': '⏭️ 舊版頁面(tps)'}

        except Exception as e:
            print(f"   ❌ 錯誤: {e}")
            url_detail_cache[url] = {'詳細資料狀態': f'❌ 錯誤: {str(e)[:50]}'}

        # 嚴格延遲（最後一筆不用等）
        if (url, _) != batch[-1] and not captcha_hit:
            delay = random.uniform(DETAIL_MIN_DELAY, DETAIL_MAX_DELAY)
            print(f"   ⏳ 等待 {delay:.1f} 秒...\n")
            time.sleep(delay)

    # 將 detail 寫回 all_rows
    for i, row in enumerate(all_rows):
        url = row.get('連結', '').strip()
        if url in url_detail_cache:
            detail = url_detail_cache[url]
            for k, v in detail.items():
                if k in DB_DETAIL_HEADERS:
                    all_rows[i][k] = v

    # 排序後重寫資料庫
    try:
        all_rows.sort(key=lambda r: r.get('公告日期', ''), reverse=True)
    except Exception:
        pass
    with open(DATABASE_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=DB_HEADERS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n   🗄️ 詳細資料補充完成：本次新增 {enriched_count} 筆")
    if captcha_hit:
        print("   ⚠️  驗證碼觸發，下次排程將繼續從未補充的記錄開始。")


if __name__ == "__main__":
    tasks_file = 'data/tasks.json'
    
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(tasks_file):
        default_tasks = [
            {"id": "1", "keyword": "IGBT", "types": ["招標公告", "公開徵求"]}
        ]
        with open(tasks_file, 'w', encoding='utf-8') as f:
            json.dump(default_tasks, f, ensure_ascii=False, indent=2)

    with open(tasks_file, 'r', encoding='utf-8') as f:
        tasks = json.load(f)
        
    print(f"📖 讀取到 {len(tasks)} 個自動任務。準備執行...")
    
    active_task_ids = [str(task.get('id')) for task in tasks]
    
    # --- 用來記錄統計資訊的變數 ---
    total_records_found = 0
    task_details_text = ""

    # 執行所有有效任務的爬蟲
    for task in tasks:
        records_count = scrape_task(task)
        total_records_found += records_count
        task_details_text += f"- [{task.get('keyword', '未知')}]: 找到 {records_count} 筆\n"

    print("\n🧹 開始檢查是否有殘留的舊檔案...")
    existing_csv_files = glob.glob('data/task_*.csv')
    
    for filepath in existing_csv_files:
        filename = os.path.basename(filepath)
        file_task_id = filename.replace('task_', '').replace('.csv', '')
        
        if file_task_id not in active_task_ids:
            try:
                os.remove(filepath)
                print(f"  🗑️ 已刪除廢棄檔案: {filename}")
            except Exception as e:
                print(f"  ❌ 刪除檔案 {filename} 失敗: {e}")
                
    # --- 印出資料庫最新統計 ---
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8-sig') as f:
            db_total = sum(1 for _ in f) - 1
        print(f"\n🗄️ 永久資料庫 ({DATABASE_FILE}) 目前累計共 {db_total} 筆記錄。")

    # --- 補充詳細資料（每次排程追加最多 5 筆）---
    enrich_database_details(max_per_run=DETAIL_MAX_PER_RUN)

    # --- 執行完畢後，寄送通知信 ---
    send_notification(len(tasks), total_records_found, task_details_text)

    print("✨ 自動排程、清理與通知作業全數完成！")
