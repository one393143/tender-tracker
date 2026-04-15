
import requests
from bs4 import BeautifulSoup
import csv
import os
import sys
from urllib.parse import quote

# 接收外部參數 (如果沒有傳遞，就用預設值)
keyword = sys.argv[1] if len(sys.argv) > 1 else "IGBT"
start_date = sys.argv[2] if len(sys.argv) > 2 else "2025/05/01"
end_date = sys.argv[3] if len(sys.argv) > 3 else "2025/05/31"

# URL 編碼處理日期
encoded_start = quote(start_date, safe='')
encoded_end = quote(end_date, safe='')

url = f"https://web.pcc.gov.tw/prkms/tender/common/basic/readTenderBasic?pageSize=50&firstSearch=true&searchType=basic&tenderName={keyword}&tenderStartDate={encoded_start}&tenderEndDate={encoded_end}"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape():
    print(f"開始搜尋: {keyword}, 期間: {start_date} ~ {end_date}")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("無法存取網站")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', {'id': 'tpam'})
    
    if not table:
        print("找不到資料或被網站阻擋")
        return

    rows = table.find_all('tr')
    data_list = []

    for row in rows[1:]:
        cols = row.find_all('td')
        if len(cols) > 5:
            org_name = cols[1].text.strip()
            case_info = cols[2].text.strip().replace('\t', '').replace('\n', ' ')
            date = cols[6].text.strip()
            budget = cols[8].text.strip()
            data_list.append([date, org_name, case_info, budget])

    # 儲存到專案中的 data 資料夾
    os.makedirs('data', exist_ok=True)
    with open('data/results.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['公告日期', '機關名稱', '標案案號與名稱', '預算金額'])
        writer.writerows(data_list)
    print(f"成功記錄 {len(data_list)} 筆資料，已存入 data/results.csv")

if __name__ == "__main__":
    scrape()
