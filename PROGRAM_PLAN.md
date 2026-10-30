# 程式規劃說明書 — V1.5.12

## 需求
以 V1.5.11 為基準，新增 PCB Seq（RF Board ID）作為單機報告查詢鍵。既有 MAC／產品 SN 查詢、Log 分析、Audit 分頁與 Limit 不變。

## 索引建立
從 InformationWrite / InformationCheck 中，以來源檔 MAC、MES `pcbSeq`、MES `ksn` 建立可靠對照表；單機查詢接受 MAC、SN、PCB Seq。對於同一 PCB Seq 多 MAC，列 TRACEABILITY CONFLICT，不製作錯誤合併報告。

## 查詢程序
載入 Log -> 整批分析 -> 在單機查詢區填入 MAC / SN / PCB Seq -> 產生單機 Summary；顯示 GENERATED、NOT FOUND、DUPLICATE、TRACEABILITY CONFLICT。

## 驗收
1. `MO26100236-00014` 當其對應 MES 實際存在時可找到設備。
2. MAC／SN 既有功能不退化。
3. 缺失資料不猜測配對。
4. 無任何測試規格與判定邏輯變更。
