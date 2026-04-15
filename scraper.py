import requests
from bs4 import BeautifulSoup
import csv
import os
import sys
from urllib.parse import quote

# 1. 接收外部參數 (從 GitHub Actions 傳入)
keyword = sys.argv[1] if len(sys.argv) > 1 else "IGBT"
start_date = sys.argv[2] if len(sys.argv) > 2 else "2025/05/01"
end_date = sys.argv[3] if len(sys.argv) > 3 else "2025/05/31"

# URL 編碼處理 (避免中文字或斜線造成網址解析錯誤)
encoded_keyword = quote(keyword)
encoded_start = quote(start_date, safe='')
encoded_end = quote(end_date, safe='')

# 2. 完整還原政府採購網需要的必填參數 (加入 dateType 與 tenderType)
url = (
    f"https://web.pcc.gov.tw/prkms/tender/common/basic/readTenderBasic?"
    f"pageSize=50&firstSearch=true&searchType=basic&isBinding=N&isLogIn=N&level_1=on"
    f"&tenderName={encoded_keyword}&tenderType=TENDER_DECLARATION&tenderWay=TENDER_WAY_ALL_DECLARATION"
    f"&dateType=isDate&tenderStartDate={encoded_start}&tenderEndDate={encoded_end}"
)

# 3. 偽裝成 Mac 的 Chrome 瀏覽器，避免被政府網站的防火牆阻擋
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

def scrape():
    print(f"🔗 正在請求網址: {url}")
    
    # 建立 Session，模擬真人先踩首頁拿 Cookie，再進入搜尋頁
    session = requests.Session()
    try:
        session.get("https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic", headers=headers, timeout=10)
        response = session.get(url, headers=headers, timeout=10)
    except Exception as e:
        print(f"❌ 連線發生錯誤: {e}")
        return
    
    if response.status_code != 200:
        print(f"❌ 無法存取網站，狀態碼: {response.status_code}")
        return

    # 解析 HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', {'id': 'tpam'})
    
    if not table:
        print("⚠️ 找不到表格 (id='tpam')。可能是沒有符合條件的標案，或是被網站防爬機制擋住了。")
        return

    rows = table.find_all('tr')
    data_list = []

    # 4. 擷取所需欄位 (跳過第0列的標題)
    for row in rows[1:]:
        cols = row.find_all('td')
        # 確保有抓到足夠的欄位才去解析
        if len(cols) >= 10:
            org_name = cols[1].text.strip()
            
            # cols[2] 通常包含： 案號 <br> 案名連結
            case_no = cols[2].contents[0].strip()
            
            nature = cols[5].text.strip()     # 採購性質
            date = cols[6].text.strip()       # 公告日期
            deadline = cols[7].text.strip()   # 截止投標
            budget = cols[8].text.strip()     # 預算金額
            
            # 從最後一欄擷取「連結」與「標案名稱」(躲開 JavaScript 混淆)
            link_tag = cols[9].find('a')
            link = f"https://web.pcc.gov.tw{link_tag['href']}" if link_tag else ""
            case_name = ""
            if link_tag and 'title' in link_tag.attrs:
                case_name = link_tag['title'].replace('檢視 標案名稱:', '').strip()
            
            data_list.append([date, org_name, case_no, case_name, nature, deadline, budget, link])

    # 5. 確保資料夾存在並存檔
    os.makedirs('data', exist_ok=True)
    with open('data/results.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['公告日期', '機關名稱', '標案案號', '標案名稱', '採購性質', '截止投標', '預算金額', '連結'])
        writer.writerows(data_list)
        
    print(f"✅ 成功記錄 {len(data_list)} 筆資料，已存入 data/results.csv")

if __name__ == "__main__":
    scrape()
