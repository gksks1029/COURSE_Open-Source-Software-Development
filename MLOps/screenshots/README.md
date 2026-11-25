# 執行結果截圖

本目錄保存 Iris 服務就緒、V1／V2 推論、Canary 分流與 Autoscaling 的執行畫面。LLM 跨機推論的結果收錄於 [回應摘要](../results/submitted/llm/chat-response-summary.json)。

| 圖片 | 驗證內容 | 對應資料 |
| --- | --- | --- |
| [01-ready.png](01-ready.png) | `sklearn-iris`、`sklearn-iris-v2` 皆為 READY=True | [服務快照](../results/submitted/inference/) |
| [02-inference-v1.png](02-inference-v1.png) | V1 路徑、HTTP 200、`predictions: [1, 1]` | [手動呼叫回應](../results/submitted/inference/screenshot-v1-response.json) |
| [03-inference-v2.png](03-inference-v2.png) | V2 路徑、HTTP 200、shape／datatype／data | [手動呼叫回應](../results/submitted/inference/screenshot-v2-response.json) |
| [04-canary-counts.png](04-canary-counts.png) | 舊版 800 次、新版 200 次，總計 1,000 次，零失敗 | [Canary 統計](../results/submitted/canary/summary.json) |
| [05-autoscaling.png](05-autoscaling.png) | Ready replicas 1→3→1，84,325 次請求，零失敗 | [副本時序](../results/submitted/autoscaling/replicas.csv)、[統計](../results/submitted/autoscaling/summary.json) |

## 畫面重現流程

下列指令於 `MLOps/` 目錄執行，執行前須完成 [環境建置](../docs/SETUP.md)。
重新執行會產生新的 run、請求數與 revision。

### 環境與推論 baseline

```bash
source scripts/env.sh
bash scripts/lab.sh resume &&
bash scripts/lab.sh models &&
bash scripts/lab.sh inference
```

`inference` 將主服務恢復為模型 v1 baseline。後續流程依序為服務狀態、協定測試、Canary、升版與負載測試。

### 服務狀態

```bash
kubectl --context kind-kserve -n lab2 get isvc sklearn-iris sklearn-iris-v2
```

確認 `sklearn-iris` 與 `sklearn-iris-v2` 的 `READY` 均為 `True`。

### V1 Protocol

```bash
curl --silent --show-error --fail \
  -H 'Host: sklearn-iris.lab2.example.com' \
  -H 'Content-Type: application/json' \
  --data-binary @inputs/iris-v1.json \
  --output .state/screenshot-v1.json \
  --write-out 'HTTP status: %{http_code}\n' \
  http://localhost:8080/v1/models/sklearn-iris:predict &&
python3 -m json.tool .state/screenshot-v1.json
```

預期回應為 HTTP 200，`predictions` 為 `[1, 1]`。

### V2 Protocol

```bash
curl --silent --show-error --fail \
  -H 'Host: sklearn-iris-v2.lab2.example.com' \
  -H 'Content-Type: application/json' \
  --data-binary @inputs/iris-v2.json \
  --output .state/screenshot-v2.json \
  --write-out 'HTTP status: %{http_code}\n' \
  http://localhost:8080/v2/models/sklearn-iris-v2/infer &&
python3 -m json.tool .state/screenshot-v2.json
```

預期回應為 HTTP 200，`model_name` 為 `sklearn-iris-v2`，`outputs[0]` 的 `shape` 為 `[2]`、`datatype` 為 `INT64`、`data` 為 `[1, 1]`。

### Canary 請求數統計

```bash
bash scripts/lab.sh canary
```

`PREV=80`、`LATEST=20` 為兩個 revision 的設定比例。實際請求數會隨抽樣波動，分流是否通過以該輪報告為準。

### Autoscaling

```bash
bash scripts/lab.sh promote &&
bash scripts/lab.sh autoscale &&
python3 scripts/show-autoscaling.py
```

摘要指令讀取最新完成的實驗，從 CSV 擷取 baseline、load、cooldown 的代表樣本與副本數，並列出請求數及失敗數。

實測結果摘要可離線重現：

```bash
python3 scripts/show-autoscaling.py --run results/submitted/autoscaling
```

摘要僅整理保存的數值，不執行模型推論或產生新的負載。
