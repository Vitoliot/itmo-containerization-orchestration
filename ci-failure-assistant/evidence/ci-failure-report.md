# Отчёт о сбое CI

## Подтверждённые факты

- Запуск [GitHub Actions №39821630472](https://github.com/Vitoliot/itmo-containerization-orchestration/actions/runs/39821630472) в репозитории `Vitoliot/itmo-containerization-orchestration` завершился со статусом `failure`.
- Job `validate-required-configuration` завершился с кодом `1` до запуска тестов.
- В журнале failed job присутствует сообщение `DATABASE_URL is not set`.
- Анализировался commit [`25f9ce9eebaaa5685bcf5e9cf4340ec10afd9b9f`](https://github.com/Vitoliot/itmo-containerization-orchestration/commit/25f9ce9eebaaa5685bcf5e9cf4340ec10afd9b9f).

## Гипотезы

- **Высокая уверенность:** workflow не получил обязательную переменную `DATABASE_URL`. Наблюдаемые признаки полностью совпадают со сценарием `CI-ENV-001` из локального runbook.
- **Средняя уверенность:** секрет отсутствует в настройках репозитория или выбранного environment либо недоступен событию, запустившему workflow.
- **Низкая уверенность:** секрет существует, но не передан в окружение job из-за ошибки в workflow-файле.

## Рекомендуемые действия

1. Проверить, что workflow обращается к `${{ secrets.DATABASE_URL }}` и передаёт значение в окружение нужного job.
2. Проверить наличие секрета в настройках репозитория или environment и доступность секрета для события, запустившего workflow.
3. После исправления повторно запустить failed jobs. Не выводить значение `DATABASE_URL` в журнал выполнения.

## Владелец и эскалация

- Владелец: Platform Team — команда, отвечающая за CI platform и `.github/workflows/`.
- Канал эскалации: `#platform-oncall`.
- Ассистент не изменяет секреты и не перезапускает job самостоятельно.

## Источники

- [GitHub Actions run 39821630472](https://github.com/Vitoliot/itmo-containerization-orchestration/actions/runs/39821630472)
- [GitHub commit 25f9ce9eebaaa5685bcf5e9cf4340ec10afd9b9f](https://github.com/Vitoliot/itmo-containerization-orchestration/commit/25f9ce9eebaaa5685bcf5e9cf4340ec10afd9b9f)
- [`CI-ENV-001` в каталоге известных ошибок](../runbooks/known-errors.md#ci-env-001-отсутствует-обязательная-переменная-окружения)
- [Карта владельцев сервисов](../runbooks/service-owners.md)
