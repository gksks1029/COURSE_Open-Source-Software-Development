# 實測結果索引

`submitted/` 保存本次作業的原始測試資料，包括 HTTP 回應、服務狀態、請求日誌與副本數時序。

| 目錄 | 主要內容 |
| --- | --- |
| [environment/](submitted/environment/) | 平台與 HTTP 入口測試、Helm release 清單 |
| [models/](submitted/models/) | sklearn 版本、模型訓練參數與輸出 |
| [inference/](submitted/inference/) | 兩種協定請求／回應、InferenceService 與 Knative 狀態 |
| [canary/](submitted/canary/) | 1,000 筆 client 紀錄、queue-proxy 日誌、806／194 統計 |
| [promotion/](submitted/promotion/) | 100 筆請求與日誌，確認全數進新版 |
| [autoscaling/](submitted/autoscaling/) | 109,821 筆請求、零失敗、Ready replicas 1→3→1 |

## 如何解讀

- `v1-response.json`、`v2-response.json` 是 client 保存的記錄；`status` 是 HTTP 狀態，`body` 是原始 JSON 回應字串，`ok` 表示 client 檢查結果。
- Canary／promotion 的 `requests.csv` 是 client 每筆結果；queue 日誌依 `lab2_run` 與 `seq` 識別請求，`summary.json` 是核對後的 revision 計數。
- Promotion 的 `sklearn-iris.json` 曾在 InferenceService 狀態同步前保存，因此仍可能顯示 80／20；同次 [Knative 狀態](submitted/promotion/sklearn-iris-knative.json) 與 [100 筆日誌核對結果](submitted/promotion/summary.json) 已證明新版 100%。目前腳本已補上 InferenceService 流量狀態等待，不修改這份歷史快照。
- Autoscaling 的 `replicas.csv` 同時保存 desired、ready、KPA desired 與 actual；驗收依據包括真正 Ready 的副本數，不能只看 desired。
- 歷史 CSV 的 `latency_ms` 為該版本 client 的計時結果；不是純模型運算時間。Canary／promotion 執行時 client 尚有重建 opener 成本；成功的 Autoscaling 已使用重用 opener 的修正版。

## Autoscaling 圖表

[replicas.png](submitted/autoscaling/replicas.png) 從 [replicas.csv](submitted/autoscaling/replicas.csv) 產生，圖表時間轉為 Asia/Taipei。
它是原始實測資料的圖表，並非現場終端機截圖，不替代 `screenshots/` 的待補項目。

若已有 matplotlib，可離線重新產生圖表；不需要 cluster、不執行負載，也不修改原 CSV：

```bash
# 在 MLOps/ 目錄執行；matplotlib 僅供這個可選的繪圖步驟。
python3 scripts/plot-autoscaling.py
```

重跑實驗會建立 `results/<stage>/<timestamp>-<id>/`，不覆寫 `submitted/`。
