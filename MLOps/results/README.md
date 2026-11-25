# 實測結果索引

`submitted/` 保存實驗的測試資料與摘要，包含 HTTP 回應、服務狀態、請求日誌及副本數時序。

| 目錄 | 主要內容 |
| --- | --- |
| [environment/](submitted/environment/) | 環境恢復結果、Helm release、ingress 與 webhook 就緒探測 |
| [models/](submitted/models/) | sklearn 版本、模型訓練參數與輸出 |
| [inference/](submitted/inference/) | V1／V2 請求與回應、服務狀態、截圖手動呼叫回應 |
| [canary/](submitted/canary/) | 1,000 筆請求、queue-proxy 日誌、800／200 分流統計 |
| [promotion/](submitted/promotion/) | 100 筆請求與日誌，新版流量比例 100% |
| [autoscaling/](submitted/autoscaling/) | 84,325 筆請求、零失敗、Ready replicas 1→3→1 |
| [llm/](submitted/llm/) | Qwen 0.5B 跨機 Chat Completion 回應摘要 |

## 資料格式與核對方式

### 模型推論

`v1-response.json` 與 `v2-response.json` 為自動測試結果；`status` 為 HTTP 狀態，`body` 為原始 JSON 回應字串，`ok` 為 client 檢查結果。
`screenshot-v1-response.json` 與 `screenshot-v2-response.json` 為截圖中的手動 curl 呼叫所保存的回應。自動測試與手動呼叫具有各自的請求 ID。
服務與 Knative 狀態快照分別保存於 `sklearn-iris*.json`，對應截圖中的 revision。

### Canary 與升版

`requests.csv` 記錄每筆 client 結果；queue-proxy 日誌包含 `lab2_run`、`seq`、revision 與 HTTP status。
`summary.json` 為 client 成功請求與 server 日誌逐筆核對後的統計。
Canary 對應 revision `00004`／`00005`，請求數分別為 800／200；升版後 100 筆請求皆進入 revision `00005`。
升版的 InferenceService 與 Knative 快照皆顯示新版流量比例 100%。

### Autoscaling

`requests.csv` 記錄 84,325 筆請求及其結果，`load-summary.json` 保存請求數與延遲摘要。
`replicas.csv` 包含完整取樣時序：

| 欄位 | 說明 |
| --- | --- |
| `timestamp` | 原始取樣時間 |
| `phase` | baseline、load 或 cooldown |
| `revision` | 本輪測試的服務 revision |
| `desired` | Deployment 期望副本數 |
| `ready` | Deployment 已就緒副本數 |
| `kpa_desired` | KPA 期望副本數 |
| `kpa_actual` | KPA 回報實際副本數 |

本輪使用 revision `00006`，Ready replicas 從 1 增至 3，負載結束後降回 1。
`latency_ms` 為 client 觀察的 HTTP 請求耗時，包含傳輸與服務處理時間，不等同於純模型計算時間。

### LLM 跨機推論

`chat-response-summary.json` 摘錄 Windows 測試端在 WSL 執行 `curl` 的輸出。`http_status` 記錄 HTTP 200，`body.model` 為 `qwen-05b`，`body.choices[0]` 保存生成文字與結束原因。`body.usage` 記錄 35 個輸入 token 與 70 個輸出 token，合計 105 個。 [回應摘要](submitted/llm/chat-response-summary.json) · [對應請求 JSON](../inputs/qwen-chat.json)

## 副本數曲線

[replicas.png](submitted/autoscaling/replicas.png) 由 [replicas.csv](submitted/autoscaling/replicas.csv) 產生，與 [Autoscaling 截圖](../screenshots/05-autoscaling.png) 使用同一輪資料。

圖表重建指令於 `MLOps/` 目錄執行，環境需具備 matplotlib；此操作不連線 cluster 或重新執行負載：

```bash
python3 scripts/plot-autoscaling.py
```

新一輪實驗結果另存於 `results/<stage>/<run>/`。
