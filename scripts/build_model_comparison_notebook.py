#!/usr/bin/env python3
"""Create/refresh a small executed notebook from saved model results only.

Missing or unfinished LLM outputs are displayed as pending, never as zero scores.
This script writes only notebooks/model_comparison.ipynb; it runs no inference.
"""
from pathlib import Path
import textwrap
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'notebooks/model_comparison.ipynb'
md = lambda text: nbformat.v4.new_markdown_cell(textwrap.dedent(text).strip())
code = lambda text: nbformat.v4.new_code_cell(textwrap.dedent(text).strip())
cells = [
md('''
# Сравнение retrieval и LLM: разные задачи, разные метрики

Этот notebook читает **сохранённые** результаты; модели не загружает и inference
не повторяет. Первая задача — восстановить известный counterpart среди кандидатов.
Вторая — сравнить решение LLM с авторской меткой по заголовкам. Третья — разобрать
доступные правила девяти пар без независимой эталонной разметки.

Эти результаты нельзя объединять в общую accuracy. Retrieval использует 461
известную положительную связь в пуле 493 × 493. LLM получают 64 выбранные пары:
32 same, 27 different и 5 unsure; agreement оценивается на **59** определённых
авторских метках, а пять unsure разбираются отдельно. Поля меток и прошлые решения
моделям не передаются. Набор уже отобран автором внешнего matcher.

**Статус ниже вычисляется из файлов.** Отсутствие LLM summary или незавершённый
manifest означает отсутствие итоговой метрики, а не нулевое качество. Авторские
labels и автоматический review не являются независимым human gold.
'''),
code(r'''
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib
import pandas as pd
from IPython.display import display, Markdown

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents]
            if (p / 'comparison/plan.json').exists())
def read(rel):
    return json.loads((ROOT / rel).read_text(encoding='utf-8'))
def sha(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
old = read('redesign/retrieval/summary.json')
new = read('comparison/retrieval/summary.json')
plan = read('comparison/plan.json')
retrieval_manifest = read('comparison/retrieval/run_manifest.json')
for rel, expected in retrieval_manifest['inputs_sha256'].items():
    if rel.endswith('.json') and (ROOT / rel).exists():
        assert sha(rel) == expected, 'Изменён frozen input: ' + rel
external_pairs = plan['external_llm']['selected_pairs']
assert len(external_pairs) == 64
assert len(plan['core_rules_llm']['cases']) == 9
print('Просмотр сохранённых файлов, UTC:', datetime.now(timezone.utc).isoformat())
print('SHA-256 доступных retrieval inputs совпали; внешние входы восстанавливает scripts/fetch_reference_inputs.py. Модели не запускались.')
print('LLM-план: 64 metadata-пары + 9 rule-кейсов.')
'''),
code(r'''
display(Markdown('## 1. Retrieval: один вход и одинаковый пул кандидатов'))
models = {'lexical': 'TF-IDF', 'dense': 'MiniLM-L6-v2',
          'e5_small_v2': 'E5-small-v2', 'bge_small_en_v1_5': 'BGE-small-en-v1.5'}
rows = []
for key, label in models.items():
    for venue, direction in [('poly', 'Polymarket → Kalshi'), ('kalshi', 'Kalshi → Polymarket')]:
        result = next(s for s in old + new
                      if s['method'] == key and s['view'] == 'event_title'
                      and s['source_venue'] == venue)
        assert result['candidate_count_per_query'] == 493 and result['query_count'] == 461
        k1, k5 = result['at_k']['1'], result['at_k']['5']
        rows.append({'Метод': label, 'Направление': direction,
            'Top-1': f"{round(k1['query_hit_rate'] * 461)}/461 ({k1['query_hit_rate']:.1%})",
            'Top-5': f"{round(k5['query_hit_rate'] * 461)}/461 ({k5['query_hit_rate']:.1%})",
            'Top-1, среднее по событиям': f"{k1['event_macro_query_hit_rate']:.1%}"})
display(pd.DataFrame(rows).set_index(['Метод', 'Направление']))
display(Markdown('Вход: **название события + заголовок**. Top-k — восстановление '
    'известных авторских links, не доказательство эквивалентности выплат. '
    'Среднее по событиям использует точную строку event title: 254 группы '
    'Polymarket и 252 Kalshi; это не независимая тестовая выборка по семействам. '
    'Устойчивого преимущества E5/BGE над обоими baseline по двум направлениям нет. '
    'Разница в несколько пар не устанавливает статистическую значимость.'))
'''),
code(r'''
display(Markdown('## 2. LLM: только завершённые запуски и явные знаменатели'))
llm_names = {'qwen3_4b': 'Qwen3-4B-Instruct-2507', 'llama32_3b': 'Llama-3.2-3B-Instruct'}
completed, manifests, statuses = {}, {}, []
for key, label in llm_names.items():
    prefix = 'comparison/llm/' + key + '/'
    summary_file, manifest_file = ROOT / (prefix + 'summary.json'), ROOT / (prefix + 'run_manifest.json')
    if not summary_file.exists():
        state = 'Итогового summary пока нет'
        if (ROOT / (prefix + 'startup_failure.json')).exists():
            state += '; сохранена запись ошибки запуска'
        statuses.append({'Модель': label, 'Статус': state})
        continue
    if not manifest_file.exists():
        statuses.append({'Модель': label, 'Статус': 'Есть summary, нет итогового manifest'})
        continue
    try:
        result, manifest = read(prefix + 'summary.json'), read(prefix + 'run_manifest.json')
    except json.JSONDecodeError:
        statuses.append({'Модель': label, 'Статус': 'Файл ещё записывается или повреждён'})
        continue
    if not manifest.get('completed_at_utc'):
        statuses.append({'Модель': label, 'Статус': 'Запуск ещё не отмечен завершённым'})
        continue
    assert result['external_n'] == 64 and result['definite_author_labels'] == 59
    assert result['total_n'] == 73 and len(result['core_decisions']) == 9
    assert manifest['plan_sha256'] == sha('comparison/plan.json')
    assert manifest['inputs_sha256'] == sha('comparison/llm/inputs.json')
    assert manifest['predictions_sha256'] == sha(prefix + 'predictions.jsonl')
    completed[key], manifests[key] = result, manifest
    statuses.append({'Модель': label, 'Статус': 'Завершён; plan/inputs/predictions hashes совпали'})
display(pd.DataFrame(statuses).set_index('Модель'))
llm_rows = []
for key, result in completed.items():
    a, c, selective = result['reference_label_agreement'], result['coverage'], result['selective_agreement']
    first_pass = result.get('valid_first_pass_json')
    llm_rows.append({'Модель': llm_names[key],
        'Agreement с автором': f"{a['agree']}/{a['n']} ({a['fraction']:.1%})",
        'Coverage': f"{c['covered']}/{c['n']} ({c['fraction']:.1%})",
        'Agreement среди ответов': f"{selective['agree']}/{selective['n']}" if selective['n'] else 'нет ответов',
        'Balanced agreement': f"{result['balanced_agreement']:.1%}",
        'Корректный первый JSON': f"{first_pass}/{result['total_n']}" if first_pass is not None else 'не записан',
        'Ошибки': sum(result['error_counts'].values())})
if llm_rows:
    display(pd.DataFrame(llm_rows).set_index('Модель'))
else:
    display(Markdown('**Итоговых LLM-метрик ещё нет.** Таблица заполнится после завершения запусков.'))
display(Markdown('Agreement — согласие с авторской same/different меткой, **не human-gold accuracy**. '
    'Coverage — доля 59 определённых пар, где модель дала exact_match/not_exact_match. '
    'Unknown и ошибки не засчитываются как совпадение. Balanced agreement усредняет '
    'доли совпадения отдельно для 32 same и 27 different. Валидность JSON показана '
    'на всех 73 заданиях и не означает смысловую правильность. MLX 4 bit — отдельная '
    'конфигурация от исходных полноточных моделей.'))
'''),
code(r'''
display(Markdown('## 3. Что скрывается за числом: классы, отказы и правила'))
for key, result in completed.items():
    display(Markdown('### ' + llm_names[key]))
    display(pd.DataFrame(result['confusion']).rename(columns={
        'author_label': 'Авторская метка', 'prediction': 'Ответ', 'n': 'Число'}))
    print('Пять авторских unsure:', result['author_unsure_prediction_counts'])
    print('Ошибки/нарушения формата:', result['error_counts'])
    quotes = result['quote_exact_substrings']
    print('Цитаты найдены дословно в указанных полях:', quotes['valid'], '/', quotes['n'])
    display(pd.DataFrame(result['core_decisions']).rename(columns={
        'id': 'Rule-кейс', 'decision': 'Решение', 'relation': 'Отношение'}))
if not completed:
    display(Markdown('Ожидаются завершённые ответы. Девять rule-кейсов пока не получают числовой оценки.'))
display(Markdown('Девять кейсов используют **все доступные поля правил**, что не гарантирует '
    'полноту применимого договора. Для них нет независимого gold: таблица показывает '
    'решения и расхождения, а не рейтинг качества. Наличие дословной цитаты проверяет '
    'атрибуцию; достаточность цитаты для логического вывода требует отдельного разбора. '
    'Agreement двух моделей тоже не создаёт gold.'))
'''),
md('''
## Как обновить notebook и что известно о Linux

После завершения LLM-запусков из корня репозитория:

```bash
python3 scripts/build_model_comparison_notebook.py
```

Скрипт заново читает JSON и исполняет только этот notebook. Он не перезаписывает
исходные данные, планы, model outputs или run scripts. Для него нужны `nbformat`,
`nbclient`, `ipykernel` и `pandas` в окружении с kernel `python3`; MLX, PyTorch и
веса моделей для просмотра не требуются. При несовпадении hashes ячейка прекращает
работу, а не рисует метрики из изменённых данных.

**Linux: статическая проверка, запуска на Linux не было.** E5/BGE runner использует
PyTorch CPU float32, safetensors и пути относительно репозитория; обязательных
macOS/Metal-зависимостей у этого пути нет. Нужен Python 3.11 и отдельное окружение
из `comparison/retrieval/requirements.txt`. Повторное получение моделей требует
доступа к Hugging Face; `--offline` годится только с заранее наполненным cache.
Проверка сохранённых матриц `comparison/retrieval/verify_outputs.py` обходится
без моделей. Шрифты macOS нужны только отдельному PDF-генератору, не retrieval.

Текущий LLM-runner — **MLX/Metal на Apple Silicon**, Linux-воспроизведение для него
не подготовлено. Эти окружения нельзя объединять: retrieval фиксирует
Transformers 4.44.2 / NumPy 1.25.1, MLX-окружение использует другие версии.
Повторный inference проводить в отдельной копии рабочей папки: текущий E5/BGE
runner пишет в `comparison/retrieval/`, а LLM-runner запрещает перезапись существующих
predictions. Сохранённые результаты остаются исходной точкой сравнения.
'''),
]
nb = nbformat.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python'},
})
NotebookClient(nb, timeout=120, kernel_name='python3',
               resources={'metadata': {'path': str(ROOT)}}).execute()
assert not [o for c in nb.cells for o in c.get('outputs', []) if o.get('output_type') == 'error']
nbformat.validate(nb)
DEST.parent.mkdir(parents=True, exist_ok=True)
nbformat.write(nb, DEST)
print(f'Executed {len(nb.cells)} cells without errors: {DEST.relative_to(ROOT)}')
