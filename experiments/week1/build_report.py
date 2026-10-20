"""Render a descriptive report from the complete saved E01 summary, without new inference."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
run = HERE / "results/observed"
summary = json.loads((run / "summary.json").read_text())
manifest = json.loads((run / "run_manifest.json").read_text())
raw = [json.loads(line) for line in (run / "predictions.jsonl").read_text().splitlines()]
evaluated = json.loads((run / "evaluated.json").read_text())
h1 = json.loads((HERE / "h1_queue/summary.json").read_text())
assert manifest["status"] == "complete" and len(raw) == 96


def pct(number):
    return "не определена" if number is None else f"{100*number:.1f}%"


order = ["direct", "structured", "structured_checked", "repeat", "critic", "critic_checked",
         "rule_only", "always_unknown", "always_no_constraint"]
lines = [
    "# E01: результаты первого диагностического эксперимента",
    "",
    f"Завершён запуск из 96 вызовов на 24 development-парах. Модель: Qwen3-4B-Instruct-2507, MLX 4 bit. Дата UTC: {manifest['completed_at_utc'][:10]}.",
    "",
    "**Это проверка работоспособности процедуры и её ошибок на заданных условиях. H1-H3 на реальных межплощадочных рынках пока не проверены.** Нет независимой человеческой разметки, untouched holdout или оценки арбитражной доходности.",
    "",
    "## 16 искусственных задач с точным эталоном",
    "",
    "Восемь логических шаблонов в двух искусственных доменах, 64 состояния, из них 18 запрещённых. Другие четыре искусственные проверки отказа и четыре реальные пары в эту таблицу не входят.",
    "",
    "| Метод | Точно решено / 16 | Coverage состояний | Полные пары / 16 | Ложные / все выданные запреты | Recall запретов |",
    "|---|---:|---:|---:|---:|---:|",
]
for name in order:
    m = summary["methods"][name]["controlled"]
    lines.append(f"| {name} | {m['exact_pairs']}/16 | {pct(m['state_coverage'])} | {m['complete_pairs']}/16 | {m['false_forbidden']}/{m['predicted_forbidden']} | {pct(m['forbidden_recall'])} |")
lines += ["", "`0/0` в колонке запретов означает отсутствие выданных запретов, не precision=100%. Низкий false forbidden без coverage и recall не является успехом. `rule_only` разбирает специально поддерживаемый искусственный язык, поэтому его результат не показывает качество на естественных договорах.",
          "", "## Формат, evidence и свидетели", "",
          f"В финальном прогоне ошибок JSON/schema/лимита: **{sum(bool(r['error']) for r in raw)}/96**. Они сохраняются в исходных строках и не заменяются выборочными повторами.",
          "",
          "Начальная калибровка v0 остановлена после 30 вызовов: 19 ошибок схемы. Модель часто выводила свидетель строкой вместо объекта. В v1 полная JSON-схема добавлена в инструкцию, затем повторены все 24 пары во всех четырёх ветках. Это изменение интерфейса, а не доказанное улучшение семантики. [Архив v0](results/format_calibration_v0/README.md).", ""]
for method in ("structured", "repeat", "critic"):
    m = summary["methods"][method]
    ev = m["evidence_substrings"]
    counts = m["raw_model_witnesses"]
    lines.append(f"- `{method}`: точные подстроки evidence {ev['exact']}/{ev['checked']}; исходные свидетели: " +
                 ", ".join(f"`{key}`={value}" for key, value in sorted(counts.items())) + ".")
lines += ["", "Совпадение цитаты с текстом не доказывает корректность вывода. Числовые свидетели модели проверяются отдельно в [witness_audit.json](results/observed/witness_audit.json). Валидатор заново строит собственные свидетели, а не делает исходные объяснения модели автоматически верными.",
          "", "## Что изменили ветви H3", "",
          "Числа ниже относятся к отдельным состояниям, не к парам, только при двух валидных ответах. Исправление означает переход из известного неверного статуса в правильный; уход в abstain вынесен отдельно. Переходы через ошибки формата учитываются отдельно на уровне пар в summary.json.", "",
          "| Переход | Исправлено | Внесено новых ошибок | Неверный ответ → abstain | Верный ответ → abstain |",
          "|---|---:|---:|---:|---:|"]
for contrast in ("structured__structured_checked", "structured__repeat", "structured__critic", "critic__critic_checked"):
    t = summary["transitions"][contrast]
    lines.append(f"| {contrast.replace('__', ' → ')} | {t.get('repaired_known_error', 0)} | {t.get('introduced_known_error', 0)} | {t.get('to_abstain_from_wrong', 0)} | {t.get('to_abstain_from_correct', 0)} |")
lines += ["", "Полные переходы, включая выходы из abstain, и risk-coverage curves находятся в [summary.json](results/observed/summary.json). Confidence не калибрована, равные confidence включаются группой. Покрытие и ошибки на таком малом искусственном наборе не дают подтверждения H2/H3 для реальных договоров.",
          "", "## Проверки области и реальные пары", "",
          "| Метод | Валидный полный abstain на 4 scope guards | Валидный полный abstain на 4 реальных парах | Непроверенные запреты на реальных парах |",
          "|---|---:|---:|---:|"]
for name in order[:6]:
    m = summary["methods"][name]
    g, real = m["scope_guards"], m["real_unlabeled"]
    lines.append(f"| {name} | {g['valid_all_unknown']}/4 | {real['valid_all_unknown']}/4 | {real['asserted_forbidden_states_unvalidated']} |")
lines += ["", "Scope guards проверяют консервативный отказ от полного бинарного заключения при отсутствии источника или выплате 0.5. Реальные пары не имеют gold: их запреты непроверенные, а не автоматически ошибочные. Возврат unknown валидатором вне поддерживаемого языка отражает ограничение его области.",
          "", "## Фактическая стоимость", "",
          "| Процедура | Вызовы | Входные токены | Выходные токены | Время LLM, с |",
          "|---|---:|---:|---:|---:|"]
for name in ("direct", "structured", "repeat", "critic"):
    cost = summary["methods"][name]["cost"]
    lines.append(f"| {name} | {cost['llm_calls']} | {cost['input_tokens']} | {cost['output_tokens']} | {cost['llm_seconds']:.1f} |")
lines += ["", "Стоимость repeat/critic включает общий первый вызов structured, поэтому строки нельзя складывать как независимые затраты. Общий финальный запуск содержит ровно 96 уникальных вызовов. Лимит составляет 700 выходных токенов на вызов, но равный лимит не означает равный фактический расход. Калибровка v0 оплачивается вычислениями отдельно. Платных API не использовалось; время не является строгим аппаратным benchmark.",
          "", "## Подготовка H1", "",
          f"TF-IDF и MiniLM выполнены на {h1['records']} официальных Kalshi-записях из {h1['events']} событий: title и доступный context. Получено {h1['union_pairs']} уникальных кандидатов и [слепая очередь из {h1['queue_pairs']} пар](h1_queue/blind_queue.jsonl). Потерянных токенов нет. Пять текстов Polymarket сохранены отдельным инвентарём с неподтверждёнными market IDs и не включены в retrieval.",
          "",
          "Это single-venue acquisition diagnostic. Ни пересечение выдач, ни число кандидатов не измеряют H1. Для следующего эксперимента нужны полный противоположный venue-pool, межплощадочные пары и независимый просмотр небольших блоков, включая пары вне top-k.",
          "", "## Что делать дальше", "",
          "1. Воспроизвести таблицу по README и вручную разобрать одну граничную ошибку в notebook.",
          "2. Для 8-12 калибровочных пар собрать полные правила и два независимых человеческих разбора; все просмотренные пары оставить в dev.",
          "3. Зафиксировать одинаковую выразительность direct/structured, основную модель, сравнение при одинаковом coverage и разделение событий/шаблонов до построения пар.",
          "4. Только после этого переносить H2-H3 на реальный корпус и измерять H1 Recall@20.",
          "",
          "Артефакты: [протокол](PROTOCOL_RU.md), [план недели](WEEK1_PLAN_RU.md), [notebook](week1_experiment.ipynb), [96 исходных ответов](results/observed/predictions.jsonl), [manifest запуска](results/observed/run_manifest.json).", ""]
(HERE / "RESULTS_RU.md").write_text("\n".join(lines))
print("Rendered RESULTS_RU.md from the complete saved summary")
