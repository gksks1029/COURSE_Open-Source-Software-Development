# 環境建置與重現

所有指令在 repository 的 `MLOps/` 目錄執行。此文件說明操作方式，不會自動修改主機或部署。

## 1. 前提與固定版本

本次使用 Ubuntu 24.04、Linux x86_64、rootless Podman 4.9.3、cgroup v2、使用者層級 systemd。
需要既有的 `podman`、`systemd-run`、`curl`、`tar`、`sha256sum`、`rg`、Python 3，以及可下載 image／chart 的網路。
腳本不自動安裝系統套件，也不執行 sudo。

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

這是本次實驗的固定版本組合，不代表最新版或正式環境選版建議。
各元件採固定版本，設定見 [versions.env](../environment/versions.env)。

## 2. 主機檢查與唯一可能需要 sudo 的操作

先檢查，不需要 sudo：

```bash
podman info
systemctl --user is-system-running
sysctl fs.inotify.max_user_instances fs.inotify.max_user_watches
```

實驗曾因 `max_user_instances=128` 不足，使控制器出現 `too many open files`。
`resume` 要求上限至少為 512；若目前已達到這個值，無須再次修改。

若確定需要調整，先保存原值，再由操作者自行執行 sudo：

```bash
(umask 077; mkdir -p .state)
if [ ! -e .state/inotify-before.conf ]; then
  sysctl fs.inotify.max_user_instances > .state/inotify-before.conf
fi
cat .state/inotify-before.conf

# 僅在目前值低於 512、且操作者同意調整時執行。
sudo sysctl -w fs.inotify.max_user_instances=512
```

需要 sudo 的原因：這會修改主機核心參數。上限按 real UID 計算，並非只影響 KServe；提高上限不會重啟其他程式或關閉既有監聽，但允許後續使用更多核心資源，不能保證零間接影響。
不修改 `max_user_watches`，也不寫入 `/etc`；重開機後依主機原有設定恢復。不要用 `sysctl --system`，避免重新套用其他參數。

## 3. 全新建立 cluster

若同一個使用者已有名稱為 `kserve` 的 kind cluster，請改看下一節，避免重複安裝平台。

```bash
bash scripts/install-tools.sh
bash scripts/create-cluster.sh
bash scripts/install-platform.sh
bash scripts/install-metrics.sh
bash scripts/lab.sh resume
```

- 工具放在 `.tools/bin/`，不安裝到系統目錄。
- kubeconfig 與 Helm 本機狀態放在 `.state/`，不覆寫 `~/.kube/config`。
- kind 使用本專案的 Podman 設定覆寫檔，調整日誌 driver 與 PID 上限，不改寫主機 `/etc/containers/`。
- quick-install 明確使用 `-s`，選擇 Knative／Serverless 模式。
- metrics-server 在此 kind 實驗加入 `--kubelet-insecure-tls`，原因是本機 kubelet 憑證限制；此例外不應直接套用正式環境。

`install-platform.sh` 呼叫官方 `helm install`，不適合直接用於已有相同 release 的 cluster。安裝失敗時先檢查紀錄，勿以刪除 cluster 當成預設修復方式。

## 4. 沿用原實驗的 cluster

這份提交版本沒有攜帶原工作目錄的工具與 kubeconfig。若從原先 `kserve/` 工作目錄改用本目錄，先準備本目錄的工具：

```bash
bash scripts/install-tools.sh
source scripts/env.sh
kind get clusters
podman ps -a --filter name=kserve-control-plane
```

如果既有節點容器是停止狀態，先啟動；若已 running 就跳過：

```bash
podman start kserve-control-plane
```

匯出既有 cluster 的 kubeconfig 到本目錄，再確認 release：

```bash
bash scripts/create-cluster.sh
helm list --kube-context kind-kserve -n kserve --all
```

若 `kserve` release 是 `deployed`，不要重跑平台安裝，直接執行 `bash scripts/lab.sh resume`。
若希望 ingress 的使用者服務改由本目錄管理，可先 `systemctl --user stop kserve-lab2-ingress.service`，再執行 `resume`；只會暫停本實驗的 port-forward，不需 sudo。

若 KServe release 是初次安裝逾時留下的 `failed`，先確認原因已處理，再按需執行：

```bash
kubectl --context kind-kserve -n kserve rollout restart deployment/kserve-controller-manager
kubectl --context kind-kserve -n kserve rollout status deployment/kserve-controller-manager --timeout=300s
helm upgrade kserve oci://ghcr.io/kserve/charts/kserve \
  --kube-context kind-kserve --namespace kserve \
  --version v0.16.0 --reuse-values --wait --timeout 10m
kubectl --context kind-kserve create namespace lab2 --dry-run=client -o yaml \
  | kubectl --context kind-kserve apply -f -
```

## 5. 執行作業

```bash
bash scripts/lab.sh resume
bash scripts/lab.sh models
bash scripts/lab.sh inference
bash scripts/lab.sh canary
# 先保存分流結果與截圖。
bash scripts/lab.sh promote
bash scripts/lab.sh autoscale
```

步驟與成功標準見 [MLOps README](../README.md)。不要同時執行多個階段。
模型 Job 完成後可沿用；若更改訓練程式，腳本會拒絕覆寫不同來源，不應在服務使用中直接改寫模型。

入口為 `127.0.0.1:8080`，透過使用者暫時服務 `kserve-lab2-ingress.service` 執行 port-forward。
kind 沒有外部 LoadBalancer，ingress Service 的 EXTERNAL-IP 顯示 `<pending>` 不影響此 port-forward 流程。
這不是永久開機服務；重開機後需重新恢復 cluster／入口。

重啟時，Pod Ready／InferenceService READY=True 可能保留自上次執行；控制器取得 leader lease 與路由更新仍需時間。
環境驗證會在最多 180 秒內探測實際 GET，對連線錯誤與 404／502／503／504 暫時等待；200 必須符合預期內容。記錄位於 `results/environment/ingress-*/attempts.json`。
這僅用於啟動檢查，正式模型 POST 與負載測試不會重試失敗請求。

## 6. 停止與還原

停止實驗並保留容器資料，不需要 sudo：

```bash
source scripts/env.sh
systemctl --user stop kserve-lab2-ingress.service
podman stop --time 60 kserve-control-plane
```

`--time 60` 只設定這次停止的等待時間；不是修改容器預設值。
若仍逾時採用 SIGKILL，下一次需透過 `resume` 重新驗證 API、節點與實際路由，不能只憑容器未刪除就宣稱資料完整。

若先前調整主機上限，且確認其他程式沒有依賴增加的容量，停止 cluster 後可按需還原：

```bash
cat .state/inotify-before.conf
sudo sysctl -p "$(pwd)/.state/inotify-before.conf"
```

這個 sudo 只重新載入指定備份中的核心參數。降低上限可能影響其他程式後續新增監聽；不確定用量時不要立即降低。

僅在確定不再需要所有實驗資料時，才刪除專用 cluster：

```bash
kind delete cluster --name kserve
```

## 7. 來源

- [KServe v0.16.0 quick-install](https://github.com/kserve/kserve/blob/v0.16.0/hack/quick_install.sh)
- [kind v0.29.0 與 node image digest](https://github.com/kubernetes-sigs/kind/releases/tag/v0.29.0)
- [kind rootless Podman 指引](https://kind.sigs.k8s.io/docs/user/rootless/)
- [KServe sklearn runtime 協定](https://github.com/kserve/kserve/blob/v0.16.0/config/runtimes/kserve-sklearnserver.yaml)
- [Knative 1.15.2 請求日誌設定](https://github.com/knative/serving/blob/knative-v1.15.2/config/core/configmaps/observability.yaml)
