# 環境建置與重現

所有指令於 repository 的 `MLOps/` 目錄執行。

## 1. 環境前提與版本

初始建置環境採 Ubuntu 24.04、Linux x86_64、rootless Podman 4.9.3、cgroup v2 與使用者層級 systemd。主機目前的作業系統版本與跨機測試端配置見 [LLM 實驗環境](LLM.md#實驗環境)。
必要工具包含 `podman`、`systemd-run`、`curl`、`tar`、`sha256sum`、`rg` 與 Python 3；建置過程需下載 container image 及 Helm chart。
工具及 cluster 本機狀態分別存放於 `.tools/` 與 `.state/`。

| 元件 | 版本 |
| --- | --- |
| kind | v0.29.0 |
| Kubernetes／kubectl | v1.31.9 |
| Helm | v3.18.6 |
| KServe | v0.16.0 |
| Istio | 1.27.1 |
| Knative Operator／Serving | v1.15.7／1.15.2 |
| cert-manager | v1.16.1 |
| Gateway API CRDs | v1.2.1 |
| metrics-server | v0.7.2 |

版本設定收錄於 [versions.env](../environment/versions.env)，用於重現本實驗的固定版本組合。

## 2. 主機檢查

```bash
podman info
systemctl --user is-system-running
sysctl fs.inotify.max_user_instances fs.inotify.max_user_watches
```

`resume` 要求 `fs.inotify.max_user_instances` 至少為 512。限制不足或控制器回報檔案數錯誤時，處理方式見 [Troubleshooting](#7-troubleshooting)。

## 3. 全新建立 cluster

此流程適用於尚無 `kserve` cluster 的環境；既有 cluster 的操作方式見下一節。

```bash
bash scripts/install-tools.sh &&
bash scripts/create-cluster.sh &&
bash scripts/install-platform.sh &&
bash scripts/install-metrics.sh &&
bash scripts/lab.sh resume
```

| 項目 | 設定 |
| --- | --- |
| 工具目錄 | `.tools/bin/` |
| kubeconfig | `.state/kubeconfig`，不覆寫 `~/.kube/config` |
| Helm 本機狀態 | `.state/helm/` |
| Podman 覆寫設定 | 專案內 `environment/containers.conf` |
| KServe 模式 | quick-install `-s`，使用 Knative／Serverless |
| 模型 namespace | `lab2` |

metrics-server 在 kind 中使用 `--kubelet-insecure-tls`，以配合本機 kubelet 憑證設定；此設定僅用於本機實驗。
`install-platform.sh` 使用官方 `helm install` 流程，已有相同 release 的 cluster 不適用重複安裝。

## 4. 沿用既有 cluster

### 工具與節點狀態

```bash
bash scripts/install-tools.sh
source scripts/env.sh
kind get clusters
podman ps -a --filter name=kserve-control-plane
```

既有節點容器處於停止狀態時，執行：

```bash
podman start kserve-control-plane
```

### kubeconfig 與 release

```bash
bash scripts/create-cluster.sh
helm list --kube-context kind-kserve -n kserve --all
```

`create-cluster.sh` 將既有 cluster 的 kubeconfig 匯出至本目錄，並等待節點就緒。
KServe release 為 `deployed` 時，後續使用 `bash scripts/lab.sh resume` 恢復環境；release 為 `failed` 時，依 Troubleshooting 處理。

實驗目錄搬移後，`start-ingress.sh` 會檢查暫時服務的啟動路徑，將舊路徑替換為目前目錄。
入口服務名稱為 `kserve-lab2-ingress.service`，透過 `127.0.0.1:8080` 執行 port-forward；此服務不設定開機自動啟動。
kind 未配置外部 LoadBalancer，ingress Service 的 EXTERNAL-IP 顯示 `<pending>` 屬此架構的預期狀態。

## 5. 執行作業

### 環境恢復與推論

```bash
bash scripts/lab.sh resume &&
bash scripts/lab.sh models &&
bash scripts/lab.sh inference
```

### Canary 分流

```bash
bash scripts/lab.sh canary
```

### 升版與 Autoscaling

Canary 原始結果及截圖保存後，執行：

```bash
bash scripts/lab.sh promote &&
bash scripts/lab.sh autoscale
```

各階段依序操作，避免多個程序同時修改相同服務。步驟及驗收標準見 [MLOps README](../README.md)，畫面重現方式見 [截圖說明](../screenshots/README.md)。
已完成的模型 Job 可重複使用；訓練來源與既有 ConfigMap 不一致時，腳本會拒絕覆寫。

## 6. 停止與清理

停止 cluster 並保留容器資料：

```bash
source scripts/env.sh
systemctl --user stop kserve-lab2-ingress.service
podman stop --time 60 kserve-control-plane
```

`--time 60` 設定該次停止操作的等待時間，不改變容器預設值。
逾時採用 SIGKILL 後，下一次啟動需由 `resume` 驗證 Kubernetes API、節點及實際 HTTP 路由。

移除專用 cluster 及節點內全部實驗資料：

```bash
kind delete cluster --name kserve
```

## 7. Troubleshooting

### too many open files

**問題：** 控制器出現 `too many open files`、Pod 進入 CrashLoopBackOff，或 `resume` 回報 inotify instance 上限不足。

**除錯指令：**

```bash
source scripts/env.sh
sysctl fs.inotify.max_user_instances fs.inotify.max_user_watches
kubectl --context kind-kserve -n kserve logs deployment/kserve-controller-manager -c manager --tail=50
```

錯誤可能來自檔案描述符或 inotify 限制。此環境曾在 node 檔案描述符上限足夠時，因 inotify instance 上限為 128 而失敗。
確認限制來源後，保存原值並暫時調整 instance 上限：

```bash
(umask 077; mkdir -p .state)
if [ ! -e .state/inotify-before.conf ]; then
  sysctl fs.inotify.max_user_instances > .state/inotify-before.conf
fi
sudo sysctl -w fs.inotify.max_user_instances=512
```

此操作不修改 `max_user_watches` 或 `/etc`。上限已達 512 但錯誤持續時，需重新確認原因，避免反覆增加限制。
停止實驗並確認目前用量允許後，還原原值：

```bash
cat .state/inotify-before.conf
sudo sysctl -p "$(pwd)/.state/inotify-before.conf"
```

### Helm release 為 failed

控制器啟動問題排除後，以原版本及既有設定恢復 release：

```bash
kubectl --context kind-kserve -n kserve rollout restart deployment/kserve-controller-manager &&
kubectl --context kind-kserve -n kserve rollout status deployment/kserve-controller-manager --timeout=300s &&
helm upgrade kserve oci://ghcr.io/kserve/charts/kserve \
  --kube-context kind-kserve --namespace kserve \
  --version v0.16.0 --reuse-values --wait --timeout 10m
kubectl --context kind-kserve create namespace lab2 --dry-run=client -o yaml \
  | kubectl --context kind-kserve apply -f -
```

### 重啟後 READY=True，但入口回傳 503

Ready 條件可能保留自前次執行，控制器仍需取得 leader lease 並更新路由。
環境驗證在最多 180 秒內探測實際 GET，對連線錯誤與 404／502／503／504 暫時等待；HTTP 200 另檢查預期內容。
探測記錄位於 `results/environment/ingress-*/attempts.json`。此機制僅用於啟動檢查，正式模型 POST 與負載測試不重試失敗請求。

**除錯指令：**

```bash
source scripts/env.sh
kubectl --context kind-kserve -n lab2 get pods,svc,endpoints
kubectl --context kind-kserve -n knative-serving logs deployment/net-istio-controller --tail=50
journalctl --user -u kserve-lab2-ingress.service -n 30
```

### failed calling webhook：connection refused

API Server 連至 `kserve-webhook-server-service:443` 被拒絕，表示 admission webhook 服務路徑尚未就緒。
重啟初期 Kubernetes API 暫時不可達，可能造成控制器重新啟動。Deployment 狀態檢查通過不代表 API Server 已能完成 webhook 呼叫；Job／PVC 正常亦不代表 InferenceService 可以建立。

**除錯指令：**

```bash
source scripts/env.sh
kubectl --context kind-kserve -n kserve get pods,svc,endpoints
kubectl --context kind-kserve -n kserve logs deployment/kserve-controller-manager -c manager --tail=50
kubectl --context kind-kserve -n lab2 apply --dry-run=server -f environment/smoke-test.yaml
```

環境驗證在實際套用資源前，等待 server-side dry run 通過，期限為 180 秒，記錄位於 `results/environment/webhook-*/attempts.json`。
暫時性 webhook 連線錯誤可於期限內重試；YAML 或驗證錯誤直接失敗。webhook 與 failurePolicy 維持原設定。
連續階段以 `&&` 串接，確保前一步失敗時停止後續操作。

## 8. 參考來源

- [KServe v0.16.0 quick-install](https://github.com/kserve/kserve/blob/v0.16.0/hack/quick_install.sh)
- [kind v0.29.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.29.0)
- [kind rootless Podman 指引](https://kind.sigs.k8s.io/docs/user/rootless/)
- [KServe sklearn runtime 協定](https://github.com/kserve/kserve/blob/v0.16.0/config/runtimes/kserve-sklearnserver.yaml)
- [Knative 1.15.2 請求日誌設定](https://github.com/knative/serving/blob/knative-v1.15.2/config/core/configmaps/observability.yaml)
