import requests
from bs4 import BeautifulSoup
import csv
import os
import json
import glob  
import smtplib  # 👈 新增：寄信模組
from email.mime.text import MIMEText  # 👈 新增：信件內容模組
from email.mime.multipart import MIMEMultipart
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

# --- 3. 寄信功能函數 ---
def send_notification(task_count, total_records, details_text):
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    receiver_email = os.environ.get('EMAIL_RECEIVER')

    if not sender_email or not sender_password:
        print("⚠️ 未設定 Email 機密變數，跳過寄送通知信。")
        return

    print("📧 準備寄送系統通知信...")
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"🔔 政府採購網自動查詢完成 (發現 {total_records} 筆)"

    body = (
        f"您的自動採購查詢排程已執行完畢！\n\n"
        f"🕒 查詢區間：{start_date_str} ~ {end_date_str}\n"
        f"📊 執行任務數：{task_count} 項\n"
        f"🎯 總計標案數：{total_records} 筆\n\n"
        f"--- 各任務詳細統計 ---\n{details_text}\n"
        f"👉 請至您的管理中心查看詳細資料。"
    )
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print("✅ 通知信寄送成功！")
    except Exception as e:
        print(f"❌ 寄信失敗：{e}")


def scrape_task(task):
    task_id = str(task.get('id', 'default')) 
    keyword = task.get('keyword', '')
    types = task.get('types', ["招標公告"]) 
    
    encoded_keyword = quote(keyword)
    all_data = []

    print(f"🚀 開始執行任務: [{keyword}], 搜尋過去30天 ({start_date_str} ~ {end_date_str})")

    session = requests.Session()
    try:
        session.get("https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic", headers=headers, timeout=10)
    except:
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
                        if len(cols) >= 9:
                            org_name = cols[1].text.strip()
                            case_info = cols[2].text.strip().replace('\t', '').replace('\n', ' ')
                            date = cols[6].text.strip()
                            budget = cols[8].text.strip()
                            all_data.append([t_name, date, org_name, case_info, budget])
        except Exception as e:
            print(f"    ❌ 查詢 {t_name} 發生錯誤: {e}")

    os.makedirs('data', exist_ok=True)
    filename = f"data/task_{task_id}.csv"
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['招標類型', '公告日期', '機關名稱', '標案案號與名稱', '預算金額'])
        writer.writerows(all_data)
        
    print(f"✅ 任務 [{keyword}] 完成，共 {len(all_data)} 筆，存入 {filename}\n")
    return len(all_data) # 👈 回傳抓到的數量給寄信功能使用


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
                
    # --- 執行完畢後，寄送通知信 ---
    send_notification(len(tasks), total_records_found, task_details_text)
    
    print("✨ 自動排程、清理與通知作業全數完成！")
