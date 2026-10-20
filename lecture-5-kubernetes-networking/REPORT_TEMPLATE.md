# Отчёт о лабораторной №5 — Kubernetes Networking

## 0. Выбор CNI

**Выбор:** Cilium. **Обоснование:** CNI с NetworkPolicy, eBPF, Hubble. **Установленная версия Cilium:** ______. **Kubernetes:** ______.

**Подтверждения:** скриншоты состояния Pod и статуса узлов.

## 1. Сеть Pod

Ноды и IP Pod: ______. Интерфейс `eth0`, значение `iflink`: ______. Найденный veth/аналог в datapath: ______. Прямой доступ разных нод: ______.

## 2. Service и хаос

Тип Service: NodePort. Host-port: 18080. Node-port: 30080.

Режим kube-proxy: ______ (подтвердить config/logs).

EndpointSlice до/после удаления Pod: ______.

Общее количество запросов: ______. Успешных: ______. Ошибок: ______. Что происходило при удалениях: ______.

График: `lab-work/results/availability.svg`.

## 3. Матрица доступа

| Source | Destination | Expected | Actual | Evidence |
|---|---|---|---|---|
| client | api | ALLOW | ... | ... |
| intruder | api | DENY | ... | ... |
| api | PostgreSQL | ALLOW | ... | ... |
| worker | PostgreSQL | ALLOW | ... | ... |
| intruder | PostgreSQL | DENY | ... | ... |
| worker | api | DENY | ... | ... |

**Служебные исключения:** CoreDNS, CNPG operator → instance manager, PostgreSQL → kube-apiserver, Prometheus → `/metrics`, external → NodePort.

## 4. Zero Trust

Перечень применённых NetworkPolicy/CiliumNetworkPolicy: ______. Обоснование направлений/портов: ______.

## 5. Проверка заказов

POST `/order` создал заказ: ______. Worker перевёл в `processed`: ______. Доказательство через логи/запросы: ______.

## 6. Скрытая поломка

**Наблюдаемый симптом:** ______.

**Где искали:** Hubble (source/destination/port/verdict/reason): ______.

**Настоящая причина:** ______. **Исправление:** ______.

**Результат повторной полной матрицы:** ______.

## 7. Метрики и алерты

- `ShopPolicyDrops`: смысл, порог, фактическое состояние ______.
- `ShopTcpResets`: смысл, порог, фактическое состояние ______.
- `ShopDnsFailures`: смысл, порог, фактическое состояние ______.

Запросы PromQL, источник метрик, скриншоты дашборда: ______.

**Подтверждённый Firing:** ______ (алерт, момент, чем вызван, скриншот).

## Итог

Вывод об отказоустойчивости Service: ______. Вывод о реальном применении default-deny: ______. Как Hubble помог найти проблему: ______.
