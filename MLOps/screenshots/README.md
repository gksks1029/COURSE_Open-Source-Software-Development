# 執行結果截圖 — 待補

目前尚待補齊作業要求的執行結果截圖。
請從實際執行結果擷取下列圖片，放在本目錄；完成後更新 MLOps README 的狀態與圖片連結。

| 建議檔名 | 必須看得到的內容 | 可對照的實測證據 |
| --- | --- | --- |
| `01-ready.png` | `sklearn-iris`、`sklearn-iris-v2` 的 READY=True | [服務狀態](../results/submitted/inference/) |
| `02-inference-v1.png` | V1 呼叫與 HTTP 200、`predictions: [1,1]` | [V1 回應](../results/submitted/inference/v1-response.json) |
| `03-inference-v2.png` | V2 呼叫與 HTTP 200、output shape／datatype／data | [V2 回應](../results/submitted/inference/v2-response.json) |
| `04-canary-counts.png` | 舊版 806／新版 194、總數 1,000、零失敗 | [Canary 統計](../results/submitted/canary/summary.json) |
| `05-autoscaling.png` | baseline／load／cooldown 的副本變化 1→3→1 | [副本時序](../results/submitted/autoscaling/replicas.csv) |

請保留服務／revision 名稱、指令或結果檔來源，使圖片能與原始資料對應。若重新執行，使用新一輪實際結果，不要將新截圖與舊計數混稱為同一輪。
圖中避免顯示 kubeconfig、憑證、token 或其他無關視窗。

若要查看已保存的原始結果，可在 `MLOps/` 目錄執行下列唯讀指令；它們只顯示歷史記錄，不代表重新執行模型或負載：

```bash
python3 -m json.tool results/submitted/canary/summary.json
python3 -m json.tool results/submitted/autoscaling/summary.json
python3 -c 'import json; print(json.dumps(json.loads(json.load(open("results/submitted/inference/v1-response.json"))["body"]), indent=2))'
python3 -c 'import json; print(json.dumps(json.loads(json.load(open("results/submitted/inference/v2-response.json"))["body"]), indent=2))'
```

在已配置本目錄工具與 kubeconfig 的實驗環境中，可用 `source scripts/env.sh` 後執行 `kubectl --context kind-kserve -n lab2 get isvc` 查看目前服務狀態。
Canary／升版會改變當下的流量配置；需要 80／20 的現場畫面時，依主 README 順序重做並在 promote 前截圖。
