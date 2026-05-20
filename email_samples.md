# 政府採購自動化追蹤系統 — 郵件發送模擬範本

本文件模擬了系統在執行完畢且篩選出全新標案時，自動寄發給老闆與管理階層的兩封郵件範本。

---

## 範本一：系統總結通知信 (System Summary Notification)

* **寄件者 (`From`)**：`procurement-tracker@yourdomain.com`
* **收件者 (`To`)**：`boss@yourdomain.com` (僅寄送給 `EMAIL_RECEIVER` 清單中的主要收件者)
* **郵件主旨 (`Subject`)**：`[系統通知] 政府採購網自動追蹤排程執行報告 (共 12 筆)`

### 郵件內文 (純文字格式)

```text
您好：

政府採購網自動追蹤系統已於今日執行完畢，以下為本次排程之執行報告：

■ 查詢設定與統計
- 查詢區間：2026/04/20 ~ 2026/05/20
- 追蹤關鍵字項目：3 組
- 本次新增標案總數：12 筆

■ 關鍵字追蹤詳細結果：
- [IGBT]: 找到 5 筆
- [二極體]: 找到 4 筆
- [匯流排]: 找到 3 筆

■ 系統儀表板：
請至以下連結檢視完整資料與歷史紀錄：
https://allspoon.github.io/tender-tracker/scheduled.html

此信件為系統自動發送，請勿直接回覆。
```

---

## 範本二：全新標案警示信 (New Tender Alert)

* **寄件者 (`From`)**：`procurement-tracker@yourdomain.com`
* **收件者 (`To`)**：`boss@yourdomain.com, team@yourdomain.com` (同步發送予清單中所有指定收件者)
* **郵件主旨 (`Subject`)**：`標案提醒：2筆新採購案`

### 郵件內文 (純文字格式)

```text
您好：

政府採購網追蹤系統於本次排程中，篩選出 2 筆新增之採購標案。相關明細如下，供您參考：

1. 【國防部軍醫局】 二極體雷射等3項
   - 標案案號：NB15090P073
   - 公告日期：115/05/08
   - 預算金額：TWD 1,550,000
   - 標案連結：https://web.pcc.gov.tw/prkms/urlSelector/common/tpam?pk=NzEyMTQwMDI=

2. 【衛生福利部臺中醫院】 動力中心空調設備電力匯流排汰換案
   - 標案案號：TH115061
   - 公告日期：115/04/13
   - 預算金額：TWD 733,525
   - 標案連結：https://web.pcc.gov.tw/prkms/urlSelector/common/tpam?pk=NzExOTM1OTU=

詳細標案清單與歷史數據，請至系統儀表板查閱：
https://allspoon.github.io/tender-tracker/scheduled.html

本郵件為自動化系統發送，如有任何疑問請洽系統管理人員。
```
