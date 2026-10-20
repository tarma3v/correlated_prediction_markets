# Первая неделя H1-H3

Для знакомства с темой начните с [разбора перед встречей на 25-30 минут](MEETING_BRIEF_RU.md), также доступна [версия для чтения в браузере](MEETING_BRIEF_RU.html). Далее откройте [план семи сессий](WEEK1_PLAN_RU.md) и [notebook с объяснениями](week1_experiment.ipynb). Он пересчитывает сохранённый эксперимент без загрузки модели и без платных API.

## Что подготовлено

- **E01, H2-H3:** одна Qwen3-4B, одинаковые тексты, direct/structured, повторная оценка, критик и числовая проверка. 16 искусственных решаемых пар, 4 проверки отказа и 4 реальные неразмеченные пары. [Протокол](PROTOCOL_RU.md), [результаты](RESULTS_RU.md).
- **Подготовка H1:** TF-IDF и MiniLM на 323 Kalshi-контрактах, заголовки против доступного контекста. [40 пар для слепой разметки](h1_queue/blind_queue.jsonl), [описание и воспроизведение](h1_queue/README.md). Межплощадочный recall здесь не измеряется.
- Все исходные ответы и неудачные попытки сохранены. Нет независимого human gold, untouched holdout или подтверждения H1-H3.

## Самый короткий запуск

Из корня репозитория, Python 3.11 или новее. Для этого шага достаточно стандартной библиотеки:

```bash
python3 experiments/week1/prepare.py --check
python3 -m unittest discover -s experiments/week1 -p 'test_*.py' -v
python3 experiments/week1/evaluate.py --run experiments/week1/results/observed --output tmp/week1-rescore
```

Первая команда проверяет сохранённые входы, вторая проверяет математику и метрики, третья заново вычисляет таблицу из 96 сохранённых вызовов. Это **пересчёт результатов**, а не повторная генерация ответов модели. Строки `false_forbidden=0/0` означают отсутствие выданных запретов, а не идеальную precision.

Чтобы открыть notebook в новом окружении, команды ниже используют установленный Python 3.11. Для первых трёх команд пересчёта достаточно Python 3.11 или новее; модельные зависимости закреплены для 3.11:

```bash
python3.11 -m venv .venv-week1-notebook
.venv-week1-notebook/bin/python -m pip install -r experiments/week1/requirements-notebook.txt
.venv-week1-notebook/bin/jupyter lab experiments/week1/week1_experiment.ipynb
```

В Jupyter выберите **Restart Kernel and Run All Cells**. Notebook читает сохранённые ответы, проверяет hashes, пересчитывает метрики и разбирает один пример ошибки. Он не запускает модель скрытым образом.

## Повторить именно LLM inference

Использованный backend требует **macOS на Apple Silicon**. Это ограничение данного runner; offline scoring и логика от него не зависят. GPU/Linux runner в этот первый опыт не включён.

В существующем окружении с локальным cache:

```bash
comparison/.venv-llm/bin/python experiments/week1/run_llm.py --output tmp/week1-llm-rerun
python3 experiments/week1/evaluate.py --run tmp/week1-llm-rerun
```

На новом Apple Silicon компьютере:

```bash
python3.11 -m venv .venv-week1-llm
.venv-week1-llm/bin/python -m pip install -r experiments/week1/requirements-mlx.txt
.venv-week1-llm/bin/python experiments/week1/run_llm.py --download --output tmp/week1-llm-rerun
python3 experiments/week1/evaluate.py --run tmp/week1-llm-rerun
```

`--download` скачивает только закреплённую публичную модель, платных вызовов нет. Веса занимают несколько гигабайт и не входят в Git. Выбирайте новую выходную папку: runner отказывается перезаписывать существующий результат. Даже при greedy decoding совпадение байт между разным железом и версиями библиотек не гарантировано; сравнивайте ответы, hashes входов и зафиксированную среду.

## Как читать результат

1. Сначала проверьте число строк и ошибки JSON/schema. Не называйте невалидный ответ осознанным отказом.
2. Сравните **coverage**, число точно решённых пар и **false forbidden**. Затем посмотрите recall запретов: константа «всё возможно» тоже не выдаёт ложных запретов.
3. Для H3 откройте переходы: `repaired_known_error` и `to_abstain_from_wrong` означают разные действия.
4. Посмотрите исходный текст, ответ и свидетель конкретной ошибки. `rule_only` служит верхним контролем для поддерживаемого искусственного языка, а не конкурентом на естественных договорах.
5. Реальные пары анализируйте отдельно. Без независимой разметки у них нет accuracy; истинность ограничений ещё предстоит установить.

**Первое самостоятельное действие:** пройти notebook до примера со строгим и нестрогим порогом, вручную проверить значение ровно на границе и объяснить, почему одно из `01` или `10` возможно. После этого разобрать 2-3 реальные пары из слепой очереди по [инструкции](../../protocol/annotation_guide.md), сохранив `unknown` там, где правил недостаточно.

## Что зафиксировано

`config.json` и `prompts/` задают сравнения; `data/manifest.json` содержит hashes; `results/observed/` содержит raw outputs, среду и пересчитанные метрики. Начальная диагностика `v0` остановлена после 30 вызовов с 19 ошибками схемы и сохранена в `results/format_calibration_v0/`. В `v1` явно задана JSON-схема и повторены все 24 пары во всех четырёх ветках, не только неудачные строки. Просмотренные данные остаются development.
