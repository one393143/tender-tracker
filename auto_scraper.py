import requests
from bs4 import BeautifulSoup
import csv
import os
import json
from urllib.parse import quote
from datetime import datetime, timedelta

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

def scrape_task(task):
    task_id = task.get('id', 'default')
    keyword = task.get('keyword', '')
    types = task.get('types', ["招標公告"]) # 預設只查招標公告
    
    encoded_keyword = quote(keyword)
    all_data = []

    print(f"🚀 開始執行任務: [{keyword}], 搜尋過去30天 ({start_date_str} ~ {end_date_str})")

    session = requests.Session()
    try:
        session.get("https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic", headers=headers, timeout=10)
    except:
        print("連線首頁失敗")
        return

    # 針對這個任務勾選的多種「招標類型」，分別發送請求
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
                        if len(cols) >= 9:
                            org_name = cols[1].text.strip()
                            case_info = cols[2].text.strip().replace('\t', '').replace('\n', ' ')
                            date = cols[6].text.strip()
                            budget = cols[8].text.strip()
                            # 加入招標類型作為第一欄標籤
                            all_data.append([t_name, date, org_name, case_info, budget])
        except Exception as e:
            print(f"    ❌ 查詢 {t_name} 發生錯誤: {e}")

    # 存檔 (每個任務獨立一個 CSV)
    os.makedirs('data', exist_ok=True)
    filename = f"data/task_{task_id}.csv"
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['招標類型', '公告日期', '機關名稱', '標案案號與名稱', '預算金額'])
        writer.writerows(all_data)
        
    print(f"✅ 任務 [{keyword}] 完成，共 {len(all_data)} 筆，存入 {filename}\n")


if __name__ == "__main__":
    # 讀取任務清單設定檔
    tasks_file = 'data/tasks.json'
    
    # 如果還沒有設定檔，建立一個預設的作為範例
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(tasks_file):
        default_tasks = [
            {"id": "1", "keyword": "IGBT", "types": ["招標公告", "公開徵求"]}
        ]
        with open(tasks_file, 'w', encoding='utf-8') as f:
            json.dump(default_tasks, f, ensure_ascii=False, indent=2)

    # 載入並執行所有任務
    with open(tasks_file, 'r', encoding='utf-8') as f:
        tasks = json.load(f)
        
    print(f"讀取到 {len(tasks)} 個自動任務。準備執行...")
    for task in tasks:
        scrape_task(task)
