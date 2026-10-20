# Лабораторная №5 — Kubernetes Networking: Zero Trust с доказательствами

**Авторский проект:** [Vitoliot/itmo-containerization-orchestration](https://github.com/Vitoliot/itmo-containerization-orchestration)  
**Требования:** [оригинальное задание лабораторной №5](https://github.com/KeladKaal/containerization-and-orchestration/blob/main-rus/lecture-5-kubernetes-networking/lab.md)

В этой папке находится **автономное продолжение лабораторных №2 и №3**: Helm-чарт `shop`, работающие API/worker/PostgreSQL, Cilium/Hubble, NetworkPolicy, тесты хаоса, тесты матрицы доступа, сценарий случайной сетевой неисправности и сетевые алерты. Файлы из лабораторной №3 менять не нужно.

> **Важно:** эти исходники и команды подготовлены по репозиторию, но ещё не запускались в вашем Kubernetes-кластере. Некоторые детали сети (в частности, NodePort/NAT, метки CloudNativePG, доступ к Kubernetes API и метки Prometheus) нужно подтвердить экспериментально. Исходные данные, реальные графики, скриншоты и результаты проверок в архив **не подделаны**.

## Требования к машине

- Linux (Ubuntu) или WSL2 с доступом к Docker; рекомендуемый объём памяти — 8–12 ГиБ для трёх нод kind и мониторинга.
- Docker, kind, `kubectl`, Helm 3, Python 3 и Bash; интернет для загрузки образов и Helm-чартов.
- Команды ниже выполняются **из каталога `lecture-5-kubernetes-networking/`**.
- Не запускайте новый `kind` поверх работающего старого тяжёлого кластера при недостатке памяти.

Пример проверки инструментов:

```bash
bash lab-work/scripts/preflight.sh
```

## Схема и выбор CNI (часть 0)

```text
                    [external client :18080]
                              |
                         kind NodePort
                              | 30080 / 8080
    [nettest/client] --DNS--> [shop-shop-api] <--- Prometheus (:8080/metrics)
                              |      (3 replicas)
                              v 5432
                         [PostgreSQL] <----5432---- [worker] (2 replicas)
                           CloudNativePG
                  [Cilium NetworkPolicy/eBPF]
                [Hubble] --> Prometheus --> Grafana
```

Выбран **Cilium**, потому что он применяет Kubernetes NetworkPolicy, использует eBPF и даёт сетевую наблюдаемость с Hubble. В отличие от него стандартный kindnet не реализует NetworkPolicy. В эксперименте оставляем kube-proxy (`kubeProxyReplacement: false`), чтобы отдельно изучить роль Service/EndpointSlice/kube-proxy.

### Шаг 1 — kind из трёх узлов

```bash
kind create cluster --name lab5 --config lab-work/kind-config.yaml
kubectl config use-context kind-lab5
kubectl get nodes -o wide
```

Ноды пока могут быть `NotReady` — CNI ещё отсутствует.

### Шаг 2 — установить Cilium + Hubble

```bash
helm repo add cilium https://helm.cilium.io/
helm repo update
helm upgrade --install cilium cilium/cilium \
  --version 1.20.3 -n kube-system \
  -f lab-work/cilium-values.yaml \
  --wait --timeout 10m
kubectl get nodes
kubectl -n kube-system get pods -l k8s-app=cilium
kubectl -n kube-system get pods -l k8s-app=hubble-relay
```

В `cilium-values.yaml` пока стоит `serviceMonitor.enabled: false`: до установки Prometheus Operator соответствующих CRD нет. Само Hubble уже включено. Совместимость версии Cilium с установленной версией Kubernetes сверяйте с [таблицей поддержки](https://docs.cilium.io/en/stable/operations/system_requirements/).

### Шаг 3 — диагностические Pod и сеть (часть 1)

```bash
kubectl apply -f lab-work/nettest-pods.yaml
kubectl wait -n nettest --for=condition=Ready pod --all --timeout=180s
kubectl get pods -n nettest -o wide
kubectl exec -n nettest test-a -- ip -d addr show eth0
kubectl exec -n nettest test-a -- ip route
kubectl exec -n nettest test-a -- cat /sys/class/net/eth0/iflink
POD_IP=$(kubectl get pod test-b -n nettest -o jsonpath='{.status.podIP}')
kubectl exec -n nettest test-a -- ping -c 3 "$POD_IP"
docker exec lab5-worker ip -o link show
```

Запишите IP Pod `test-a` и `test-b`, их ноды, `eth0`, `iflink` и найденный интерфейс на ноде. Реализация datapath у Cilium может отличаться от обычной иллюстрации пары veth — документируйте **наблюдаемую** конфигурацию, а не ожидаемую.

## Шаг 4 — уже существующая инфраструктура из лабораторной №2/3

Здесь поднимается **одна** копия существующего стека мониторинга, а не дополнительный Prometheus внутри `shop`:

```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace --wait --timeout 8m
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n observability --create-namespace \
  -f lab-work/monitoring/metrics-values.yaml --wait --timeout 12m
```

После установки CRD включите `ServiceMonitor` Cilium/Hubble:

```bash
helm upgrade cilium cilium/cilium --version 1.20.3 -n kube-system \
  -f lab-work/cilium-values.yaml \
  --set prometheus.serviceMonitor.enabled=true \
  --set operator.prometheus.serviceMonitor.enabled=true \
  --set hubble.metrics.serviceMonitor.enabled=true \
  --wait --timeout 10m
kubectl get servicemonitor -A
```

Сбор сетевых метрик проверяется в Prometheus запросами `hubble_flows_processed_total` и `hubble_drop_total`. У DNS-метрик потребуется включение L7-перехвата DNS (соответствующий Helm-шаблон подготовлен в `shop`).

## Шаг 5 — сборка и установка shop

Образы этого проекта соответствуют существующему префиксу `ghcr.io/vitoliot` из прежней лабораторной; публикация в GHCR не обязательна, так как `kind load` загружает их локально.

```bash
docker build -t ghcr.io/vitoliot/shop-api:lab5 lab-work/services/api
docker build -t ghcr.io/vitoliot/shop-worker:lab5 lab-work/services/worker
kind load docker-image ghcr.io/vitoliot/shop-api:lab5 --name lab5
kind load docker-image ghcr.io/vitoliot/shop-worker:lab5 --name lab5

helm lint lab-work/chart/shop
helm template shop lab-work/chart/shop -n app > /tmp/shop-baseline.yaml
helm upgrade --install shop lab-work/chart/shop -n app --create-namespace \
  --wait --timeout 12m
kubectl get pods,svc,endpointslice -n app -o wide
kubectl get cluster shop-postgres -n app
```

В `values.yaml` **сначала стоит `networkPolicy.enabled: false`**. Так можно проверить обычную плоскую сеть перед включением запретов. CloudNativePG создаёт app-secret `shop-postgres-app` с паролем, который берут оба Deployment. В `values.yaml` секретов нет.

Ожидаются `3/3` API, `2/2` worker и `shop-postgres` healthy. Если Pod застрял из-за отсутствующего Secret, проверьте `kubectl get secret -n app shop-postgres-app`, CR `Cluster` и журналы CloudNativePG. Если Pod `Pending`, проверьте StorageClass `standard` и свободные ресурсы.

Проверьте API по NodePort:

```bash
curl -i http://127.0.0.1:18080/health
curl -s http://127.0.0.1:18080/whoami
```

`/whoami` возвращает имя конкретного Pod, поэтому позволяет видеть смену endpoints. Тестируем настоящую бизнес-цепочку:

```bash
bash lab-work/scripts/order-check.sh
```

Скрипт создаёт заказ через API по **DNS имени Service**, затем проверяет, что worker обработал его в PostgreSQL. У API есть `POST /order`, `GET /orders/{id}`, `/health`, `/metrics`, `/slow`, `/fail`, `/load` и `/whoami`. `/load` вызывает localhost одного Pod; для тестов отказоустойчивости его **не используйте**.

## Часть 2 — NodePort и непрерывность при хаосе Pod

В `values.yaml` выставлен `api.service.type: NodePort` с `nodePort: 30080`; kind пробрасывает `30080` контейнера control-plane на хостовый `127.0.0.1:18080`. `ClusterIP` предоставляет внутренний виртуальный IP; `NodePort` открывает порт нод; `LoadBalancer` интегрируется с внешним балансировщиком; headless (`clusterIP: None`) публикует endpoints через DNS без обычного ClusterIP-балансирования.

Сначала убедитесь, что `nettest/client` обращается к Service:

```bash
kubectl exec -n nettest client -- curl -fsS http://shop-shop-api.app.svc.cluster.local:8080/health
kubectl get endpointslice -n app -l kubernetes.io/service-name=shop-shop-api -o wide
```

Откройте **два терминала** из каталога лабораторной:

```bash
# Терминал 1: постоянная нагрузка клиента по DNS, сохранение каждого результата
bash lab-work/scripts/availability.sh 500 0.4

# Терминал 2: выбираем и удаляем Pod, ждём готовности между удалениями
bash lab-work/scripts/chaos.sh 20
```

Параллельно можно смотреть `kubectl get pod -n app -o wide -w`. После завершения построить график:

```bash
python3 lab-work/scripts/plot_availability.py
# Откройте lab-work/results/availability.svg в браузере
```

График показывает успешные и неуспешные запросы и вертикальные отметки удаления Pod. **Не заявляйте 0 ошибок, если CSV фиксирует ошибки.** Если ошибки есть — проанализируйте EndpointSlice, readiness, graceful shutdown и повторные попытки; `preStop` задержка снижает риск, но не гарантирует нулевые сбои.

В отчёте объясните роли DNS (Service name), Service (стабильный ClusterIP/маршрутизация), EndpointSlice (список доступных endpoints), kube-proxy (`iptables`/`nftables`/`IPVS` в зависимости от режима и версии) и Cilium (Pod-to-Pod сеть). Проверка режима kube-proxy:

```bash
kubectl -n kube-system get cm kube-proxy -o jsonpath='{.data.config\.conf}'
kubectl -n kube-system logs -l k8s-app=kube-proxy --tail=100
```

## Часть 3 — спроектированная матрица доступа

| Источник | Назначение | Порт | Ожидаемый результат |
|---|---|---|---|
| `nettest/client` | API | 8080 | ALLOW |
| Внешний клиент через NodePort | API | 30080/8080 | ALLOW |
| API | PostgreSQL | 5432 | ALLOW |
| worker | PostgreSQL | 5432 | ALLOW |
| `nettest/intruder` | API | 8080 | DENY |
| `nettest/intruder` | PostgreSQL | 5432 | DENY |
| worker | API | 8080 | DENY |
| API/worker/PG | CoreDNS | 53 TCP/UDP | ALLOW |
| Prometheus | API `/metrics` | 8080 | ALLOW |
| CloudNativePG operator | PostgreSQL instance manager | 8000 | ALLOW |
| PostgreSQL | Kubernetes API | API-server port | ALLOW (Cilium entity) |

Для сценария используется **один экземпляр PostgreSQL**. Для нескольких экземпляров потребуется отдельно разрешить репликацию/служебные PostgreSQL соединения; не считайте матрицу для `instances: 1` production-ready.

## Часть 4 — включаем zero-trust

Политики находятся в `lab-work/chart/shop/templates/`:

- `networkpolicy-default-deny.yaml`: полный deny ingress/egress для namespace `app`;
- `networkpolicy-dns.yaml`: UDP/TCP к CoreDNS;
- `networkpolicy-api.yaml`: ingress от `nettest/client` и Prometheus, egress к PostgreSQL;
- `networkpolicy-worker.yaml`: разрешён только egress к PostgreSQL;
- `networkpolicy-postgres.yaml`: ingress от API/worker на 5432 и CNPG operator на 8000;
- `ciliumnetworkpolicy-postgres-api.yaml`: egress PostgreSQL к специальной сущности `kube-apiserver` без нестабильного ipBlock;
- `ciliumnetworkpolicy-api-nodeport.yaml`: клиентский NodePort снаружи (world/host/remote-node) только к API:8080;
- `ciliumnetworkpolicy-dns-observe.yaml`: L7-наблюдаемость DNS для Hubble.

Это **Helm-шаблоны чарта `shop`**, как требует задание; дополнительные CiliumNetworkPolicy нужны для доступа к kube-apiserver и к внешним адресам без грубого `allow-all`.

Перед включением проверьте реальные метки:

```bash
kubectl get pods -n app --show-labels
kubectl get pods -n kube-system -l k8s-app=kube-dns --show-labels
kubectl get pods -n observability --show-labels
kubectl get pods -n cnpg-system --show-labels
```

Особенно проверьте метки `app.kubernetes.io/name=postgres`, `app.kubernetes.io/instance=shop`, а также `app.kubernetes.io/name=prometheus`. Если они отличаются, скорректируйте selectors. **Нельзя считать NetworkPolicy работающей только потому, что Kubernetes принял YAML.**

```bash
helm template shop lab-work/chart/shop -n app \
  --set networkPolicy.enabled=true > /tmp/shop-zero-trust.yaml
helm upgrade shop lab-work/chart/shop -n app \
  -f lab-work/chart/shop/values.yaml \
  --set networkPolicy.enabled=true
kubectl get networkpolicy,ciliumnetworkpolicy -n app
kubectl get pods -n app
```

Если NodePort после этого недоступен, проверьте `hubble observe` и фактический source identity после NAT; его нельзя угадывать заранее. Некоторые host-to-Pod потоки обходят обычную семантику policy. При необходимости уточните CNP, сохраняя правило `intruder → API = DENY`.

## Часть 5 — тестовая матрица

```bash
bash lab-work/scripts/test-matrix.sh
# Результат: lab-work/results/matrix.csv
bash lab-work/scripts/order-check.sh
```

`test-matrix.sh` запускает проверки из разных Pod и сопоставляет **expected/actual**. Если появляется FAIL — сначала исправьте селекторы, ingress/egress, DNS и служебные правила CNPG, затем продолжайте. Для Hubble:

```bash
kubectl -n kube-system port-forward svc/hubble-ui 12000:80
# http://127.0.0.1:12000
```

Матрица не ограничивается одной проверкой: после каждого исправления повторяйте все строки. Дополнительно можно проверить `kubectl get cluster shop-postgres -n app` и Prometheus Targets — метрики не должны исчезать после запрета.

## Часть 6 — скрытая поломка и расследование

```bash
bash lab-work/scripts/inject-fault.sh
bash lab-work/scripts/order-check.sh   # симптом
bash lab-work/scripts/test-matrix.sh  # конкретная стрелка матрицы
```

Внутри скрипта случайно выбирается **одна** из четырёх поломок: нет API egress к БД, нет worker egress к БД, разрешён порт 5433 вместо 5432, отключён DNS. Выбранный вариант сохранён в `lab-work/results/.fault-answer.txt`; до завершения расследования не заглядывайте туда.

В Hubble найдите `DROPPED`/`POLICY_DENIED` по Source, Destination, Destination port и reason. Для CLI `hubble observe --namespace app --verdict DROPPED --follow` потребуется отдельно установленный [Hubble CLI](https://docs.cilium.io/en/stable/observability/hubble/setup/#install-the-hubble-client); UI доступен через port-forward выше. Снимите скриншот конкретной блокировки.

Восстановление базовых политик:

```bash
bash lab-work/scripts/recover.sh
bash lab-work/scripts/test-matrix.sh
bash lab-work/scripts/order-check.sh
```

В README/отчёте зафиксируйте не только найденную настройку, но цепочку **симптом → flow → причина → исправление → зелёная матрица**.

## Часть 7 — мониторинг сети и три алерта

Cilium экспортирует `hubble_flows_processed_total`, `hubble_drop_total`, `hubble_tcp_flags_total`, `hubble_dns_responses_total`. Шаблон `PrometheusRule` содержит:

1. **`ShopPolicyDrops`** — рост пакетов с причиной `Policy denied`, приоритет warning;
2. **`ShopTcpResets`** — устойчивое увеличение TCP RST (не любой RST означает неисправность);
3. **`ShopDnsFailures`** — DNS-ответы с ошибочным `rcode`, приоритет warning.

Готовый шаблон дашборда находится в `lab-work/monitoring/grafana-dashboard.json`: в Grafana откройте **Dashboards → New → Import**, загрузите JSON и выберите Prometheus в поле источника данных. Графики заполняются реальными метриками после запуска тестов.

Примеры запросов для Grafana:

```promql
sum(rate(hubble_flows_processed_total{source_namespace="app"}[1m]))
```

```promql
sum(rate(hubble_drop_total{source_namespace="app"}[1m]))
```

```promql
sum by (flag)(rate(hubble_tcp_flags_total{source_namespace="app"}[5m]))
```

```promql
sum by (rcode)(rate(hubble_dns_responses_total{source_namespace="app"}[5m]))
```

Проверьте названия меток и значений `reason`/`rcode` **по реальным сериям**, при необходимости адаптируйте выражения. Сложность L7 DNS наблюдаемости связана с Cilium DNS proxy и его выбором endpoints. Подтвердите, что запросы действительно присутствуют, а не просто что панель создана.

```bash
kubectl get servicemonitor,prometheusrule -A
kubectl -n observability get svc | grep -E 'grafana|prometheus'
kubectl -n observability port-forward svc/kube-prometheus-stack-grafana 13000:80
# http://127.0.0.1:13000
```

Пароль Grafana, если создан автоматически, получите из Kubernetes Secret, **не храните в Git**:

```bash
kubectl get secret -n observability kube-prometheus-stack-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d; echo
```

Для демонстрации `Firing` повторяйте разрешённые/запрещённые запросы из `intruder`, пока правило не пройдёт окно оценки и `for`-интервал. Затем найдите алерт в Prometheus → Alerts. Если требуется доставлять warning в webhook, маршрутизацию Alertmanager настраивайте отдельно: в старой лабе webhook был выбран только для `severity=critical`.

## Что показать в отчёте

Скопируйте [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md), заполните **фактическими** результатами и приложите снимки в `screenshots/`:

1. Выбор CNI + `kubectl get nodes` и `veth/eth0` + ping разных нод.
2. NodePort + EndpointSlice + проверка режима kube-proxy.
3. График `results/availability.svg`, события удаления Pod и анализ потерянных/успешных запросов.
4. Проектная матрица, YAML ресурсов политики и `results/matrix.csv`.
5. Доказательство бизнес-цепочки API → PostgreSQL ← worker.
6. Заблокированный flow Hubble, гипотеза и диагностика скрытого отказа, восстановление.
7. Dashboard Cilium/Hubble + три алерта и хотя бы один реальный `Firing`.

## Частые неисправности

- **`Pending` у PostgreSQL**: StorageClass, PVC, ограничения памяти, operator.
- **DNS не работает после включения deny**: проверить `kubectl get pod -n kube-system --show-labels`, `shop-dns`, `shop-dns-observe`, Hubble и CoreDNS.
- **API/worker не видит PostgreSQL**: селекторы `inheritedMetadata`, оба направления ingress/egress, CNPG Secret, DNS.
- **CloudNativePG становится unhealthy**: проверьте разрешение operator → manager `:8000` и PostgreSQL → kube-apiserver через CNP.
- **Нет метрик Hubble**: проверьте ServiceMonitor selectors, `hubble.metrics.enabled`, наличие CRD и targets Prometheus.
- **NodePort не отвечает при strict policy**: проверить NAT/source identity и фактические правила Cilium, не открывать всю namespace наугад.
- **Все Pod API удалены слишком быстро**: chaos-скрипт ждёт восстановления между удалениями, но он не заменяет настройку graceful shutdown.

## Справочные ссылки

- [Установка Cilium через Helm](https://docs.cilium.io/en/stable/installation/k8s-install-helm/)
- [Cilium: мониторинг и Hubble metrics](https://docs.cilium.io/en/stable/observability/metrics/)
- [Cilium: default-deny и специальные сущности](https://docs.cilium.io/en/stable/security/policy/intro/)
- [CloudNativePG: app Secret и подключение к БД](https://cloudnative-pg.io/docs/1.27/applications/)
- [Kubernetes: NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
