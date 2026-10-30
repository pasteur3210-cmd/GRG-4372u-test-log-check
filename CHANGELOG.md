# CHANGELOG

## V1.5.12 (2026-10-30)
- 單機 Summary 查詢加入 PCB Seq / RF Board ID 的精確索引，支援 `MO26100236-00014`。
- 保留既有 MAC 與產品 SN 查詢方式。
- 若一個 PCB Seq 對應多個 MAC，顯示 TRACEABILITY CONFLICT，不任意合併設備。
- 保留既有的 MES 取證、RF 對應、複測判定及各測站規則，沒有變更測試 Limit 或 PASS/FAIL 規則。
- 新增 6 項回歸測試。
