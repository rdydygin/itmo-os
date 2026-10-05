# Read vs Write, Cache, 10M, Rand

Основной отчёт: [краткий PDF на ГОСТ-шаблоне](output/pdf/report-gost.pdf), 3 страницы, включая титульный лист. [Исходник Typst](report/main.typ), [описание шаблона и сборки](report/README.md). Подробный анализ сохранён отдельно в [REPORT.md](REPORT.md).

Сборка краткого отчёта: `bash scripts/build-report.sh` (требуется Typst 0.14+).

Полный повтор эксперимента (Python 3.12+, clang, POSIX):

```sh
bash scripts/run.sh
# На Linux, при необходимости закрепления на доступном ядре:
bash scripts/run.sh --core 2
```

Повтор перезаписывает результаты и заново генерирует графы. Скрипт устанавливает зависимости в `out/venv`. `out/` содержит только воспроизводимые бинарники, графы и окружение; в сдаваемых материалах они не нужны. Требуется генератор `../util/graphgen.py` из репозитория курса.

- `scripts/experiment.py prepare`: сборка и генерация двух графов с проверкой.
- `scripts/experiment.py collect` (после `prepare`, с исходными графами): прогрев, пилот, выбор N, перемешанные финальные запуски обоих методов, мониторинг и проверка изменения всех значений.
- `scripts/analyze.py`: только обработка CSV, t-интервалы, статистика диагностических запусков и графики.
- `report/generate.py`: генерация подробных `REPORT.md` и `output/pdf/report.pdf` по готовым результатам анализа.
- `scripts/build-report.sh`: сборка короткого ГОСТ-отчёта из `report/main.typ`.
- `results/graph_traverse-{read,write}.csv` и `results/graph_traverse_mmap-{read,write}.csv`: четыре сырые серии.
- `results/measurements.csv`: те же измерения в фактическом порядке запуска.
- `results/warmup.csv`, `pilot.csv`, `diagnostics.csv`: дополнительные серии, не включённые в финальную статистику.
- `results/plan.json`: протокол, пилотная оценка N и фактический N.
- `results/environment-*.json`: паспорта и снимки окружения.
- `results/runs.log`: успешность и покрытие всех обходов, вывод time.
- `results/verification.json`: проверка точного инкремента каждой вершины и неизменности структуры.
- `figures/`: средние с ДИ, наложенные плотности и последовательность измерений.

Cache Write измеряет буферизованное обновление, без гарантии завершения записи на носитель. Не следует трактовать результат как устойчивую пропускную способность SSD.

Проверка CSV и пересчёт ДИ, рендер страниц PDF в `out/pdf-preview`:

```sh
out/venv/bin/python scripts/verify.py
```

Основной отчёт использует измерения на адаптере от 05.10.2026. Предыдущая серия от 04.10.2026 сохранена в `results/battery-baseline/`; дополнительные логи питания и System Trace - в `results/mac-diagnostics/`. Данные разных дней не объединяются. Эти дополнительные материалы исторические: полный повтор основного скрипта не пересоздаёт мониторинг Instruments и powermetrics.

System Trace разобран: [подробности для защиты](TRACE_ANALYSIS.md), экспорт `results/system-trace/`, скрипты `scripts/export_traces.sh` и `scripts/analyze_traces.py`.

Обработка и оформление выполняются отдельно:

```sh
out/venv/bin/python scripts/analyze.py
out/venv/bin/python report/generate.py
bash scripts/build-report.sh
```

`analyze.py` сохраняет `summary.json`, `summary.csv`, четыре CSV серий, `diagnostics-summary.json` и графики. Markdown и PDF этот скрипт не изменяет.
