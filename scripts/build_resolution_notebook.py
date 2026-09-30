#!/usr/bin/env python3
"""Execute a compact research overview from saved JSON; no inference/downloads.

Only notebooks/resolution_diagnostics.ipynb is written. Optional typed-pair data
may be absent or unfinished; its status is then shown explicitly.
"""
from pathlib import Path
import textwrap
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'notebooks/resolution_diagnostics.ipynb'
def md(s):
    return nbformat.v4.new_markdown_cell(textwrap.dedent(s).strip())
def code(s):
    return nbformat.v4.new_code_cell(textwrap.dedent(s).strip())

cells = [
md('''
# Диагностика отношений по правилам resolution

**Вопрос:** что требуется, чтобы перейти от похожего текста к обоснованному
отношению выплат? Здесь собраны три разных вида результата: условная проверка
логической согласованности NLI, аудит договорных исключений и аналитическая
проверка метрики относительно нулевой модели. В конце — предварительные
типизированные пары со статусами доказательности.

Notebook читает готовые JSON, не запускает модели и не скачивает данные.
**Независимого human gold здесь нет.** Проверенное арифметическое противоречие
в заданной модели, текстовое наблюдение и предварительная гипотеза связи имеют
разный статус; их нельзя объединять в общую accuracy.
'''),
code(r'''
from pathlib import Path
from collections import Counter
from decimal import Decimal
from fractions import Fraction
import hashlib, json
import pandas as pd
from IPython.display import display, Markdown

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents]
            if (p / 'research/verified_findings.json').exists())
def read(rel):
    return json.loads((ROOT / rel).read_text(encoding='utf-8'))
findings = read('research/verified_findings.json')
null = read('research/metric_null_results.json')
assert findings['all_assertions_passed'] is True
assert null['checks']['exact_mixture_identity'] is True
assert null['checks']['rounding_counts_unique'] is True
sources = ['research/verified_findings.json', 'research/metric_null_results.json']
display(pd.DataFrame([{'Источник': rel,
    'SHA-256 текущего файла': hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()}
    for rel in sources]).set_index('Источник'))
print('Читаются сохранённые результаты. Нового inference и загрузки источников нет.')
'''),
code(r'''
display(Markdown('## 1. Числовой свидетель против кандидата взаимоисключения'))
d = findings['deberta']
assert d['conditional_pairs'] == d['both_yes_witnesses_checked']
ratio = d['exclusion_conflicts'] / d['conditional_pairs']
display(pd.DataFrame([{'NLI-пар всего': d['pairs'],
    'Пороговых пар в общем scope': d['conditional_pairs'],
    'Групп шаблонов': d['template_groups'],
    'Кандидатов exclusion с both-YES свидетелем': d['exclusion_conflicts'],
    'Доля в условном поднаборе': f'{ratio:.2%}'}]))
examples = []
for e in d['examples'][:3]:
    x, a, b = Decimal(e['x_both_yes']), Decimal(e['threshold_a']), Decimal(e['threshold_b'])
    yes_a = x > a if e['operator_a'] == '>' else x >= a
    yes_b = x > b if e['operator_b'] == '>' else x >= b
    assert yes_a and yes_b
    examples.append({'A': e['a'], 'B': e['b'],
        'Условие A': f"x {e['operator_a']} {a}",
        'Условие B': f"x {e['operator_b']} {b}", 'Свидетель x': str(x),
        'Оба YES': yes_a and yes_b,
        'Средний contradiction score': round(e['mean_contradiction_score'], 4)})
display(pd.DataFrame(examples))
display(Markdown('**325/839 = 38,74% — условная несогласованность выбранной эвристики, '
    'не market error rate.** Исходная эвристика превращает два NLI contradiction '
    'score в кандидата взаимоисключения. Но при общем неограниченном скаляре и '
    'бинарной выплате по одинаковому шаблону оба нижних порога выполняются при '
    '`x = max(t_A, t_B) + 1`. Отдельный verifier заново разобрал условия и '
    'проверил все 839 свидетелей; здесь показаны три и повторно проверена их арифметика. '
    '19 групп не означают 839 независимых механизмов. NLI между предложениями '
    'правил и следование событий выплат — разные задачи. Полные фактические '
    'выплаты этим тестом не сертифицированы. '
    '[Метод и ограничения](../research/validated_findings.md).'))
'''),
code(r'''
display(Markdown('## 2. Что добавляют источники и исключения'))
s = findings['source_clauses']
rows = [
    {'Наблюдение': 'Октябрьский CPI: время закрытия 08:25 в API / 08:29 в terms',
     'Проверка сохранённого текста': s['cpi_api_0825_vs_template_0829'],
     'Вывод': 'Нужно установить версию и применимый приоритет; арифметика при одном x сохраняется.'},
    {'Наблюдение': 'Декабрьский YoY >5% / любой месяц года ≥5%',
     'Проверка сохранённого текста': s['yoy_strict_above_vs_annual_at_least_api'],
     'Вывод': 'Импликация условна: нужны общие данные и согласованная процедура.'},
    {'Наблюдение': 'KXTRUMPOUT27: уход вследствие смерти запускает особый расчёт',
     'Проверка сохранённого текста': s['kalshi_departure_nonbinary_branch_in_saved_text'],
     'Вывод': 'Последняя цена / решение комитета не гарантируют универсальную модель выплат 0/1.'},
]
display(pd.DataFrame(rows))
term_checks = s.get('terms_text_checks', {})
if term_checks:
    display(pd.DataFrame([{'Источник': name, 'Статус': value['status']}
                         for name, value in term_checks.items()]))
display(Markdown('Сохранённый YOYCPI PDF содержит fallback со степенью **13/12** '
    'и предел ожидания в три месяца; LCPIYOY содержит иную процедуру окончания, '
    'включая 14 дней и исключение для shutdown. Текущий документ по прежнему URL '
    'не доказывает историческую применимость. **Различие текстов само по себе '
    'не доказывает совместно реализуемый контрпример к полным выплатам.** '
    'Небинарная ветвь не означает, что каждая фактическая выплата будет дробной. '
    '[Подробный аудит CPI](../extension/terms/AUDIT_RU.md), '
    '[карточка исключения](../redesign/cards/politics_crossvenue_departure.json).'))
'''),
code(r'''
display(Markdown('## 3. Метрика статьи: observed, постоянный плюс и случайная перестановка'))
display(Markdown('**AAI и NLI ниже — обозначения методов референсной статьи**, '
    'не новые запуски этого notebook и не DeBERTa-пилот предыдущего раздела. '
    'Это арифметическая реконструкция опубликованных агрегатов v2 '
    '[arXiv:2512.02436](https://arxiv.org/html/2512.02436v2), а не воспроизведение '
    'исходного pair-level эксперимента.'))
rows = []
for name, m in null['methods'].items():
    observed = float(Fraction(m['compatible_edges'], m['resolved_edges']))
    assert abs(observed - m['observed_score']['value']) < 1e-12
    q = m['positive_share']['value']
    r = m['constant_positive_score_on_own_selected_edges']['value']
    expected = q * r + (1 - q) * (1 - r)
    assert abs(expected - m['uniform_fixed_count_sign_shuffle_mean']['value']) < 1e-12
    rows.append({'Метод статьи': name, 'Его resolved рёбра': m['resolved_edges'],
        'Доля знаков +': f'{q:.2%}',
        'Observed compatibility': f'{observed:.2%}',
        'Постоянный знак +': f'{r:.2%}',
        'Среднее sign-shuffle': f'{expected:.2%}',
        'Observed − shuffle, п.п.': f"{m['observed_minus_shuffle_mean_pp']['value']:.3f}"})
display(pd.DataFrame(rows).set_index('Метод статьи'))
display(Markdown('Каждая строка использует **собственный выбранный набор рёбер метода**. '
    'Постоянный `+` получает балл за одинаковые бинарные исходы. Для равномерной '
    'перестановки знаков с сохранением числа плюсов математическое ожидание равно '
    '`q·r + (1−q)·(1−r)`, где q — доля плюсов, r — доля одинаковых исходов. '
    'Перестановка здесь аналитическая: новые случайные эксперименты не запускались. '
    'Часть числителей восстановлена из округлённых опубликованных процентов при '
    'указанных в JSON предпосылках. Знаковый состав и состав выбранных рёбер '
    'влияют на метрику; таблица не устанавливает преимущество по семантической '
    'точности. Глобальная exchangeability — условие нулевой модели, не доказанный '
    'факт о графе. Нет причинного объяснения, graph-aware интервала или p-value. '
    '[Аналитический разбор](../research/metric_null.md).'))
'''),
code(r'''
display(Markdown('## 4. Типизированные пары: количество отдельно от доказательности'))
typed_path = ROOT / 'relations/typed_pairs.json'
typed = None
if not typed_path.exists():
    display(Markdown('**Файл типизированных пар пока не готов.** Остальные результаты доступны.'))
else:
    try:
        typed = json.loads(typed_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        display(Markdown('**Файл типизированных пар ещё записывается или требует проверки JSON.**'))
    if typed is not None:
        assert isinstance(typed, list), 'Ожидается список карточек'
        assert len({r['pair_id'] for r in typed}) == len(typed), 'Повтор pair_id'
        relation_counts = Counter(r['relation_candidate'] for r in typed)
        status_counts = Counter(r['candidate_status'] for r in typed)
        display(pd.DataFrame(sorted(relation_counts.items()),
                             columns=['relation_candidate (enum)', 'Пар']).set_index('relation_candidate (enum)'))
        display(pd.DataFrame(sorted(status_counts.items()),
                             columns=['candidate_status (enum)', 'Пар']).set_index('candidate_status (enum)'))
        print('Всего карточек:', len(typed))
        print('С human_gold=true:', sum(r.get('human_gold') is True for r in typed))
        print('С установленными полными contract-forbidden-states:',
              sum(r.get('established_contract_forbidden_states') is not None for r in typed))
        print('SHA-256 typed_pairs.json:', hashlib.sha256(typed_path.read_bytes()).hexdigest())
display(Markdown('`conditional_analyst_proposal` — предварительное отношение при '
    'перечисленных предпосылках; `insufficient_rule_evidence` — не хватает правил; '
    '`binary_payoff_model_inadequate` — бинарная модель не покрывает договор. '
    'Даже `EQUIVALENT`, `DISJOINT` или `NO_HARD_RELATION` в поле **candidate** '
    'не являются независимыми gold-метками. Unknown не означает, что состояние '
    'допустимо; отсутствие доказанного следования не доказывает независимость. '
    'Гипотезы статистической корреляции требуют отдельных эмпирических данных. '
    '[Типизированные карточки](../relations/typed_pairs.json).'))
'''),
md('''
## Обновление и воспроизводимость

Из корня проекта:

```bash
python3 scripts/build_resolution_notebook.py
```

Нужны `nbformat`, `nbclient`, `ipykernel` и `pandas`; kernel `python3` должен
видеть эти библиотеки. Команда обновляет только этот notebook. Она не запускает
inference, не скачивает архивы и не перезаписывает исходные результаты.
Если типизированные пары обновились, повторный запуск покажет новый snapshot.

Полную независимую проверку NLI-свидетелей выполняет
`python3 research/verify_findings.py`. Здесь читается её сохранённый результат
и повторяется арифметика нескольких примеров. Отдельно
`python3 research/metric_null.py` пересчитывает математическую реконструкцию
опубликованных агрегатов. Ни одна из этих проверок не создаёт human gold.
'''),
]
nb = nbformat.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python'},
})
NotebookClient(nb, timeout=120, kernel_name='python3',
               resources={'metadata': {'path': str(ROOT)}}).execute()
errors = [o for c in nb.cells for o in c.get('outputs', []) if o.get('output_type') == 'error']
assert not errors, errors
assert 4 <= sum(c.cell_type == 'code' for c in nb.cells) <= 6
nbformat.validate(nb)
DEST.parent.mkdir(parents=True, exist_ok=True)
nbformat.write(nb, DEST)
print(f'Executed {sum(c.cell_type == "code" for c in nb.cells)} code cells without errors: {DEST.relative_to(ROOT)}')
