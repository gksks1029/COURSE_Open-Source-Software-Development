# 執行結果截圖

本目錄保存服務就緒、V1／V2 推論、Canary 分流與 Autoscaling 的執行畫面。

| 圖片 | 驗證內容 | 對應資料 |
| --- | --- | --- |
| [01-ready.png](01-ready.png) | `sklearn-iris`、`sklearn-iris-v2` 皆為 READY=True | [服務快照](../results/submitted/inference/) |
| [02-inference-v1.png](02-inference-v1.png) | V1 路徑、HTTP 200、`predictions: [1, 1]` | [手動呼叫回應](../results/submitted/inference/screenshot-v1-response.json) |
| [03-inference-v2.png](03-inference-v2.png) | V2 路徑、HTTP 200、shape／datatype／data | [手動呼叫回應](../results/submitted/inference/screenshot-v2-response.json) |
| [04-canary-counts.png](04-canary-counts.png) | 舊版 800 次、新版 200 次，總計 1,000 次，零失敗 | [Canary 統計](../results/submitted/canary/summary.json) |
| [05-autoscaling.png](05-autoscaling.png) | Ready replicas 1→3→1，84,325 次請求，零失敗 | [副本時序](../results/submitted/autoscaling/replicas.csv)、[統計](../results/submitted/autoscaling/summary.json) |

## 畫面重現流程

下列指令用於重現相同驗證項目的畫面，執行前須完成 [環境建置](../docs/SETUP.md)。
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

畫面包含命令、服務名稱、URL 與 READY 欄位，對應 `01-ready.png`。

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

畫面包含 API 路徑、HTTP 200 與預測結果，對應 `02-inference-v1.png`。

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

畫面包含 API 路徑、HTTP 200、`model_name`，以及 outputs 的 `shape: [2]`、`datatype: INT64`、`data: [1, 1]`，對應 `03-inference-v2.png`。

### Canary 請求數統計

```bash
bash scripts/lab.sh canary
```

畫面包含 `PREV=80`、`LATEST=20`、兩個 revision 的實際計數、總請求數、失敗數及 PASS，對應 `04-canary-counts.png`。
流量分配具有抽樣波動，新的實測計數以該輪結果為準。Canary 截圖及原始資料須在 promote 前保存。

### Autoscaling

```bash
bash scripts/lab.sh promote &&
bash scripts/lab.sh autoscale &&
python3 scripts/show-autoscaling.py
```

摘要指令讀取最新完成的實驗，從實際 CSV 擷取 baseline、load、cooldown 的代表樣本，對應 `05-autoscaling.png`。
畫面包含結果來源、revision、各階段副本數、總請求數、失敗數與 PASS。

實測結果摘要可離線重現：

```bash
python3 scripts/show-autoscaling.py --run results/submitted/autoscaling
```

摘要僅整理保存的數值，不執行模型推論或產生新的負載。
