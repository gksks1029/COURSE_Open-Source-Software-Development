# Qwen 0.5B 推論服務

KServe 在 `lab2-llm` namespace 建立 `qwen-05b` InferenceService，以自訂 predictor 容器啟動 `/app/llama-server`。模型採 Qwen2.5-0.5B-Instruct 的 Q4_K_M GGUF 版本。容器會在缺少快取時從 Hugging Face 下載模型，快取目錄設為 `/tmp/llama-cache`。Knative 維持單副本，每個副本同時處理一筆請求。

Kubernetes 將模型容器的 CPU request 與 limit 都設為 4。llama.cpp 的 prompt 處理與 token 生成各使用 4 個執行緒。CPU 配額採共用排程，若未另行設定 CPU Manager，不會固定使用特定核心。推論入口為 `/openai/v1/chat/completions`。

## 實驗環境

| 裝置 | 作業系統與架構 | 用途 |
| --- | --- | --- |
| KServe 主機 | x86_64，目前為 Ubuntu 26.04.1 LTS | 執行 kind Kubernetes、KServe、Istio 與 llama.cpp 推論服務 |
| 測試端 | Windows 電腦，透過 WSL 執行 Ubuntu 20.04 | 在 WSL 終端機使用 `curl`，透過主機 IP 呼叫推論 API |

## 部署與主機驗證

先完成 [環境建置](SETUP.md)。模型下載須能從 predictor 容器連線至 Hugging Face。下列指令於 `MLOps/` 執行，`source scripts/env.sh` 會使用專案的 kubeconfig。

```bash
source scripts/env.sh
kubectl --context kind-kserve apply -f manifests/llm/qwen-05b.yaml &&
kubectl --context kind-kserve -n lab2-llm wait --for=condition=Ready \
  --timeout=10m isvc/qwen-05b
```

透過主機既有的 `127.0.0.1:8080` ingress 驗證 Chat Completion。`Host` header 由 InferenceService 狀態取得。

```bash
SERVICE_URL=$(kubectl --context kind-kserve -n lab2-llm get isvc qwen-05b -o jsonpath='{.status.url}')
SERVICE_HOSTNAME=${SERVICE_URL#*://}
printf 'Service hostname: %s\n' "$SERVICE_HOSTNAME"
curl --max-time 120 -i \
  -H "Host: $SERVICE_HOSTNAME" \
  -H 'Content-Type: application/json' \
  --data-binary @inputs/qwen-chat.json \
  http://127.0.0.1:8080/openai/v1/chat/completions
```

若服務尚未就緒，可檢查 Pod、資源排程與模型載入紀錄。

```bash
kubectl --context kind-kserve -n lab2-llm get isvc,pods
kubectl --context kind-kserve -n lab2-llm logs \
  -l serving.kserve.io/inferenceservice=qwen-05b -c kserve-container --tail=80
```

## 跨機請求

在 KServe 主機開啟另一個終端機，並於 `MLOps/` 執行下列指令。`SERVER_IP` 為測試端可達的私網或 VPN 介面 IP。TCP `18080` 以明文 HTTP 轉發至共用 Istio ingress，應限制為測試端可連線。

```bash
source scripts/env.sh
SERVER_IP='<KServe 主機的私網或 VPN IP>'
kubectl --context kind-kserve -n istio-system port-forward \
  --address "$SERVER_IP" svc/istio-ingressgateway 18080:80
```

在 Windows 電腦的 WSL Ubuntu 20.04 終端機執行下列指令。URL 指向 KServe 主機 IP 與 TCP 18080，`Host` header 指定 Istio 路由。先將 [qwen-chat.json](../inputs/qwen-chat.json) 存至 WSL 終端機的目前目錄。

```bash
SERVER_IP='<KServe 主機的 IP>'
SERVICE_HOSTNAME='<InferenceService hostname>'
curl --max-time 120 -i \
  -H "Host: $SERVICE_HOSTNAME" \
  -H 'Content-Type: application/json' \
  --data-binary @qwen-chat.json \
  "http://${SERVER_IP}:18080/openai/v1/chat/completions"
```

## 跨機測試結果

Windows 測試端從 WSL 向 KServe 主機的 `18080` 連接埠發出非串流 Chat Completion 請求。Istio 回傳 `HTTP/1.1 200 OK`，`model` 為 `qwen-05b`，`choices[0].message.content` 含生成文字，`finish_reason` 為 `stop`。回應記錄 35 個輸入 token 與 70 個輸出 token。 [跨機回應摘要](../results/submitted/llm/chat-response-summary.json)

測試結束後可在主機終端機按 Ctrl+C 停止轉發。

- [Qwen 官方 GGUF 模型](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF)
- [llama.cpp HTTP 伺服器](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
