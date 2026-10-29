# GRG4372_LogInspector V1.5

Python 3.11+；安裝 requirements.txt 後執行 `python enhanced.py "達天DVT test log.zip" -o audit_output`。

輸出總 Excel、RF/BOB 等六站 Excel，新增 `GRG4372_RF_CPK_*.xlsx` 和 `GRG4372_BOB_CPK_*.xlsx`，以及 `RUN_LOG_*`、`TEST_LOG_*`、`DEBUG_RECORD_*`。

BOB 2.3~2.7 dBm、ER 12~13 dB 為雙側。EVM 只有核准 USL，計算 Ppu。各項以整體樣本σ計算屬 Ppk型態，PASS-only 存在選擇偏差，不是正式製程能力認證。缺 Log Limit 不假設相同。
