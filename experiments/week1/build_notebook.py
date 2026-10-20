"""Fill the experiment notebook scaffold with a short, offline research walkthrough."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip().splitlines(keepends=True)}


cells = [
md("""
# H1-H3: первый воспроизводимый эксперимент

**Задача:** научиться проверять ограничения между двумя контрактами и не путать
правильный отказ с ошибкой. Это development diagnostic, а не доказательство H1-H3.

Notebook работает offline с уже сохранёнными ответами модели. Он ничего не
отправляет на площадки и не запускает LLM. Для нового inference есть отдельная
команда в README. Выполняйте ячейки сверху вниз.

H1: помогает ли контекст найти трудные пары? H2: помогает ли структурированный
разбор при том же тексте и модели? H3: что добавляет проверка сверх повторного вызова?
"""),
code("""
from pathlib import Path
import hashlib
import json
import sys
from collections import Counter

HERE = next(p / 'experiments/week1' for p in [Path.cwd(), *Path.cwd().parents]
            if (p / 'experiments/week1/data/manifest.json').exists())
sys.path.insert(0, str(HERE))
from logic import extract_contract, possible_states
from evaluate import summarize

manifest = json.loads((HERE / 'data/manifest.json').read_text())
for name, expected in {**manifest['inputs_sha256'], **manifest['prompt_sha256']}.items():
    assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, name
packets = json.loads((HERE / 'data/packets.json').read_text())
refs = {r['case_id']: r for r in json.loads((HERE / 'data/reference.json').read_text())}
print('Hashes verified. Cases:', dict(Counter(r['kind'] for r in refs.values())))
"""),
md("""
## 1. Сначала математика одного контракта

В состоянии `10` контракт A платит 1, а B платит 0. Если `10` невозможно,
то A влечёт B. Рассмотрим A: `x > 1`, B: `x >= 1`. На границе `x=1`
получается `01`. Поэтому A влечёт B, но эквивалентности нет.

В этих искусственных примерах один контекст обозначает одно свободное
вещественное число. Для реальных рынков совпадение величины, источника и срока
ещё нужно доказать по правилам.
"""),
code("""
case = next(p for p in packets if refs[p['case_id']]['pattern'] == 'strict_boundary')
for side in ('A', 'B'):
    print(side, case['packet'][side]['text'], sep='\\n')
a, b = (extract_contract(case['packet'][side]['text']) for side in ('A', 'B'))
worlds = possible_states(a, b)
for state in ('00', '01', '10', '11'):
    print(state, worlds.get(state, 'FORBIDDEN in the stipulated scalar world'))
assert '01' in worlds and '10' not in worlds
"""),
md("""
## 2. Пересчитать результаты, сохранив все знаменатели

Модель уже вызвана 96 раз: 24 пары × 4 LLM-ветки. direct и structured получают
один пакет. repeat и critic начинают с одного сохранённого structured output.
Числовой checker не читает эталон и не вызывает LLM.

Таблица accuracy относится только к **16 искусственным парам**, восьми
логическим шаблонам в двух доменах. Четыре scope guards и четыре реальные пары
учитываются отдельно. Во время разработки был исправлен интерфейс свидетелей;
первый неполный запуск сохранён как format calibration, а не скрыт.
"""),
code("""
result = summarize(HERE / 'results/observed', HERE.parents[1] / 'tmp/week1-notebook-rescore')
print(f"{'method':24} {'exact':>8} {'coverage':>10} {'false F':>9} {'F recall':>10}")
for name, row in result['methods'].items():
    m = row['controlled']
    exact = f"{m['exact_pairs']}/{m['pairs']}"
    false = f"{m['false_forbidden']}/{m['predicted_forbidden']}"
    print(f"{name:24} {exact:>8} {m['state_coverage']:10.1%} {false:>9} {m['forbidden_recall']:10.1%}")
"""),
md("""
**Как оценивать:** меньше false forbidden полезно только вместе с coverage и
recall запретов. Всегда возвращать unknown или «нет запретов» недостаточно.
Отказ не считается точно решённой парой. При нуле предсказанных запретов
precision не определена, а не равна 100%.
"""),
code("""
for method in ('direct', 'structured', 'repeat', 'critic'):
    row = result['methods'][method]
    print(method, 'format errors:', row['format_errors_all_24'],
          'valid scope abstentions:', row['scope_guards']['valid_all_unknown'], '/ 4',
          'real pairs:', row['real_unlabeled'])
print('Transitions (states, not pairs):')
for contrast, counts in result['transitions'].items():
    print(contrast, counts)
"""),
md("""
## 3. Проверить один ответ, а не только итоговую таблицу

Следующая ячейка выбирает первый по ID структурированный ответ, который не
совпал с известными состояниями. Это иллюстративный разбор после запуска,
не отдельная подтверждающая выборка. Наличие числового свидетеля в JSON ещё
не доказывает, что он действительно даёт заявленные выплаты.
"""),
code("""
rows = json.loads((HERE.parents[1] / 'tmp/week1-notebook-rescore/evaluated.json').read_text())
bad = sorted([r for r in rows if r['method'] == 'structured'
              and r['kind'] == 'controlled_decidable' and r['states'] != r['reference']],
             key=lambda r: r['case_id'])
if bad:
    item = bad[0]
    raw = [json.loads(line) for line in (HERE / 'results/observed/predictions.jsonl').read_text().splitlines()]
    response = next(r for r in raw if r['case_id'] == item['case_id'] and r['branch'] == 'structured')
    packet = next(p for p in packets if p['case_id'] == item['case_id'])
    print(json.dumps(packet['packet'], ensure_ascii=False, indent=2))
    print('Reference:', item['reference'], 'Prediction:', item['states'])
    print('Raw response:', response['raw_output'])
else:
    print('No structured errors on these controlled cases. This does not establish real-market accuracy.')
"""),
md("""
## 4. Risk-coverage и стоимость

Уменьшение риска после отказа от трудных примеров не равно исправлению этих
примеров. Пороговые кривые ниже включают все равные confidence одной группой.
Confidence не калибрована. На этой маленькой искусственной выборке не выбираем
порог для финального исследования и не считаем статистическую значимость.
"""),
code("""
for method in ('direct', 'structured', 'structured_checked', 'repeat', 'critic', 'critic_checked'):
    row = result['methods'][method]
    points = [(p['confidence_threshold'], round(p['state_coverage'], 3),
               p['selective_state_error']) for p in row['risk_coverage']]
    print(method, 'threshold / coverage / assessed-state error:', points)
    cost = row['cost']
    print('  calls:', cost['llm_calls'], 'input tokens:', cost['input_tokens'],
          'output tokens:', cost['output_tokens'])
"""),
md("""
## 5. Начало H1: подготовленная очередь

Для H1 здесь есть 323 Kalshi-контракта, TF-IDF и MiniLM в двух представлениях,
и 40 пар для слепой разметки. Это single-venue подготовка данных. Большее число
кандидатов или изменение ранга не означает лучшего качества поиска.

Следующий содержательный шаг: собрать полные межплощадочные пакеты, независимо
просмотреть небольшие блоки, включая пары вне top-k, и только затем считать
Recall@20 на фиксированном корпусе противоположной площадки.
"""),
code("""
h1 = json.loads((HERE / 'h1_queue/summary.json').read_text())
print({k: h1[k] for k in ('records', 'events', 'union_pairs', 'queue_pairs')})
queue = [json.loads(line) for line in (HERE / 'h1_queue/blind_queue.jsonl').read_text().splitlines()]
print('Blind annotation queue:', len(queue), 'pairs; labels are not supplied.')
"""),
md("""
## После notebook

1. Вручную разобрать 2-3 пары из слепой очереди, сохранив источники и unknown.
2. Согласовать два независимых разбора 8-12 калибровочных пар с полными правилами.
3. Разделить dev/test по семействам событий и шаблонам до построения пар.
4. Согласовать одну основную модель, контрасты при одинаковом coverage и бюджет.

Рабочий план: `WEEK1_PLAN_RU.md`. Точный протокол и ограничения: `PROTOCOL_RU.md`.
Результаты E01 не подтверждают H1-H3 на реальных рынках и не устанавливают
арбитраж или price discovery.
""")]

path = HERE / "week1_experiment.ipynb"
for index, cell in enumerate(cells):
    cell["id"] = hashlib.sha256((str(index) + "".join(cell["source"])).encode()).hexdigest()[:12]
notebook = json.loads(path.read_text())
notebook["cells"] = cells
notebook["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n")
print("Prepared notebook with", len(cells), "cells")
