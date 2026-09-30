#!/usr/bin/env python3
"""Build and execute a short Russian notebook from saved pilot-v2 results only."""
from pathlib import Path
import textwrap
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'notebooks' / 'pilot_v2.ipynb'

def code(text):
    return nbformat.v4.new_code_cell(textwrap.dedent(text).strip())

def md(text):
    return nbformat.v4.new_markdown_cell(textwrap.dedent(text).strip())

cells = [
md('''
# Пилот v2: найти похожий контракт ≠ подтвердить связь выплат

**30 сентября 2026 · самостоятельный просмотр результатов за 5–10 минут.**
Первый пилот на однотипных инфляционных порогах заменён внешним тестом поиска
и отдельными карточками реальных правил. Этот notebook **не запускает модели**,
не обращается к API и не обучает классификатор: он читает сохранённые JSON,
проверяет исходный файл и строит один график.

**Как читать результат.** Retrieval — поиск кандидатов. Top-1 показывает, как часто
известный авторский counterpart оказался первым среди 493 рынков другой площадки.
Это ещё не доказательство эквивалентности. TF-IDF сравнивает слова и фрагменты слов;
MiniLM кодирует текст числовым вектором. «Контекст» означает название события
плюс заголовок/вариант контракта. Сравниваются четыре комбинации метода и входа.

Внешняя разметка — **author audit**, не независимый human gold. Материалы и код
имеют предварительный статус; приведённые карточки требуют экспертной проверки.
Запускайте ячейки сверху вниз; весь запуск использует только локальные результаты.
'''),
code(r'''
from pathlib import Path
from collections import Counter
import hashlib, json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display, Markdown

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents]
            if (p / 'redesign/retrieval/summary.json').exists())
load = lambda rel: json.loads((ROOT / rel).read_text(encoding='utf-8'))
manifest = load('redesign/retrieval/run_manifest.json')
source = ROOT / 'redesign/datasets/rawsamples/nl2992_pinned_audit.json'
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
assert source_hash == manifest['source_sha256'], 'Исходный файл изменился'
fixture = json.loads(source.read_text())
pairs = fixture['signal_subset'] + fixture['stratified_subset']
counts = Counter(p['label'] for p in pairs)
assert len(pairs) == 493 and counts == {'same': 461, 'different': 27, 'unsure': 5}
assert len({(p['poly_id'], p['kalshi_ticker']) for p in pairs}) == 493
summary = load('redesign/retrieval/summary.json')
assert all(s['candidate_count_per_query'] == 493 and s['query_count'] == 461
           for s in summary)
display(Markdown('### 1. Данные и контроль целостности'))
display(pd.DataFrame([{'Всего пар': len(pairs), 'same': counts['same'],
    'different': counts['different'], 'unsure': counts['unsure'],
    'Рынков Polymarket': len({p['poly_id'] for p in pairs}),
    'Рынков Kalshi': len({p['kalshi_ticker'] for p in pairs})}]))
print('SHA-256 совпал с manifest:', source_hash)
display(Markdown('Источник заранее отобран чужим matcher: 343 production-пары '
    'и 150 дополнительных. Вход поиска не содержит reference labels, reasons, '
    'цен или исходов. Неразмеченные перекрёстные пары не считаются отрицательными. '
    'Модель сохранённого запуска: `' + manifest['model']['repo'] + '`; обучения не было.'))
'''),
code(r'''
display(Markdown('### 2. Первый результат поиска: оба направления'))
lookup = {(s['method'], s['view'], s['source_venue']): s for s in summary}
configurations = [('lexical', 'title', 'TF-IDF · заголовок'),
                  ('dense', 'title', 'MiniLM · заголовок'),
                  ('lexical', 'event_title', 'TF-IDF · контекст'),
                  ('dense', 'event_title', 'MiniLM · контекст')]
rows = []
for method, view, label in configurations:
    row = {'Метод и вход': label}
    for source_venue, direction in [('kalshi', 'Kalshi → Polymarket'),
                                    ('poly', 'Polymarket → Kalshi')]:
        score = lookup[method, view, source_venue]['at_k']['1']['query_hit_rate']
        row[direction] = f'{round(score * 461)}/461 ({score:.1%})'
    rows.append(row)
display(pd.DataFrame(rows).set_index('Метод и вход'))
display(Markdown('Добавление контекста у MiniLM для Kalshi → Polymarket: '
    '**277 → 454** известных связей на первом месте. Но TF-IDF с контекстом '
    'находит **455**, поэтому превосходство dense-поиска здесь не установлено. '
    'Это проверка 461 известной связи в малом фиксированном пуле, не общей '
    'полноты поиска по площадкам. Среднее сначала по названиям событий, затем '
    'между ними для MiniLM в этом направлении: **54,9% → 98,3%** (252 группы); '
    'название события — приближённая группировка, не независимый тест семейств.'))
'''),
code(r'''
# Статический исследовательский график: сохранённые доли, без нового inference.
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                     'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.4), sharey=True)
x = np.arange(2)
for ax, venue, title in zip(axes, ['kalshi', 'poly'],
                          ['Kalshi → Polymarket', 'Polymarket → Kalshi']):
    for offset, view, label, color in [(-0.18, 'title', 'Только заголовок', '#a9b8c8'),
                                     (0.18, 'event_title', 'С контекстом события', '#2563a6')]:
        values = [100 * lookup[m, view, venue]['at_k']['1']['query_hit_rate']
                  for m in ['lexical', 'dense']]
        bars = ax.bar(x + offset, values, width=0.34, color=color, label=label)
        ax.bar_label(bars, labels=[f'{v:.1f}%' for v in values], padding=4, fontsize=10)
    ax.set(title=title, xticks=x, xticklabels=['TF-IDF', 'MiniLM'], ylim=(0, 112))
    ax.set_yticks(np.arange(0, 101, 20))
    ax.grid(axis='y', alpha=0.18)
    ax.set_axisbelow(True)
axes[0].set_ylabel('Известный counterpart на первом месте, %')
fig.suptitle('Контекст события улучшает поиск известных соответствий',
             fontsize=16, fontweight='bold', y=0.98)
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(0.5, 0.085),
           ncol=2, frameon=False)
fig.text(0.5, 0.028, '461 запрос · 493 кандидата другой площадки · author-audit labels\n'
         'Ранжирование кандидатов; эквивалентность выплат не проверена.',
         ha='center', fontsize=10, color='#475569')
fig.subplots_adjust(top=0.85, bottom=0.25, left=0.08, right=0.98, wspace=0.15)
chart_path = ROOT / 'output/pilot_v2_retrieval.png'
chart_path.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(chart_path, dpi=180, facecolor='white')
plt.show()
plt.close(fig)
print('График сохранён:', chart_path.relative_to(ROOT))
'''),
code(r'''
display(Markdown('### 3. Один понятный пример: Good Afternoon, ранг 21 → 1'))
ticker = 'KXFEDMENTION-26SEP-GOOD'
example = next(p for p in pairs if p['kalshi_ticker'] == ticker)
dense_title = load('redesign/retrieval/dense_title_pair_ranks.json')
dense_context = load('redesign/retrieval/dense_event_title_pair_ranks.json')
rank_before = next(p for p in dense_title if p['kalshi_ticker'] == ticker)['poly_rank_for_kalshi']
rank_after = next(p for p in dense_context if p['kalshi_ticker'] == ticker)['poly_rank_for_kalshi']
assert (rank_before, rank_after) == (21, 1)
display(pd.DataFrame([
    {'Поле': 'Запрос Kalshi', 'Текст': example['kalshi_title']},
    {'Поле': 'Короткая строка Polymarket', 'Текст': example['poly_title']},
    {'Поле': 'Название события Polymarket', 'Текст': example['poly_event_title']},
]).set_index('Поле'))
print(f'Ранг известной авторской пары: {rank_before} → {rank_after}')
display(Markdown('«Good Afternoon» — короткий вариант ответа, который теряет смысл '
    'без события пресс-конференции. Это особенность полей данного snapshot; '
    'её нельзя автоматически переносить на canonical question всех рынков. '
    'Пример выбран после запуска для объяснения результата, а не как отдельный тест. '
    'Авторская метка same не заменяет чтение полных правил.'))
'''),
code(r'''
display(Markdown('### 4. Почему найденная пара ещё не подтверждена'))
negatives = [p for p in dense_context if p['reference_label'] == 'different']
assert len(negatives) == 27
negative_rows = []
for field, direction in [('poly_rank_for_kalshi', 'Kalshi → Polymarket'),
                         ('kalshi_rank_for_poly', 'Polymarket → Kalshi')]:
    negative_rows.append({'Направление': direction,
        'Авторский different в top-1': sum(p[field] <= 1 for p in negatives),
        'В top-5': sum(p[field] <= 5 for p in negatives), 'Всего': len(negatives)})
assert negative_rows[0]['Авторский different в top-1'] == 24
assert negative_rows[0]['В top-5'] == 27
display(pd.DataFrame(negative_rows).set_index('Направление'))
display(Markdown('У MiniLM с контекстом **24 из 27** авторских different-пар '
    'стоят первыми в направлении Kalshi → Polymarket, все **27** попадают в top-5. '
    'Они семантически близки и могут быть полезными кандидатами второй стадии. '
    '**Это не false-positive rate классификации:** reject-правило или '
    'классификатор отношений здесь не применялись. Ошибкой было бы автоматически '
    'объявить ближайший контракт эквивалентным.'))
'''),
code(r'''
display(Markdown('### 5. Три предварительные политические карточки'))
card_names = ['politics_resignation_departure', 'politics_impeachment_departure',
              'politics_crossvenue_departure']
explanations = {
    'politics_resignation_departure': 'При общих предпосылках объявление отставки '
        'влечёт квалифицирующий уход; обратное не обязательно.',
    'politics_impeachment_departure': 'Импичмент и уход не влекут друг друга; '
        'в заявленной области рассмотрены все четыре бинарных сочетания.',
    'politics_crossvenue_departure': 'У Kalshi есть расчёт по последней цене или '
        'справедливому распределению при уходе вследствие смерти: общая модель '
        'только Да/Нет неполна.'}
for name in card_names:
    card = load('redesign/cards/' + name + '.json')
    display(Markdown('**' + name + '** — ' + explanations[name] + '\n\n'
        '*Сохранённый вывод:* ' + card['conclusion'] + '\n\n'
        'Статус: `' + card['review']['status'] + '`. Покрытие источников: `'
        + card['scope']['source_coverage'] + '`.'))
display(Markdown('Это разборы текста с явными предпосылками, не независимый gold '
    'и не результат классификатора. Политические правила Polymarket сохранены '
    'через стороннюю копию; правила Kalshi — через официальный API. Небинарная '
    'ветвь делает общую таблицу неполной, но сама по себе не запрещает изучать '
    'обычные бинарные сценарии. Статистическая корреляция цен здесь не измерялась.'))
'''),
code(r'''
display(Markdown('### 6. Ещё шесть кандидатов: snapshot без утверждённых меток'))
candidates = load('redesign/discovery/official_probe/candidate_pairs.json')
records = {r['id']: r for r in load('redesign/discovery/official_probe/source_records.json')}
assert len(candidates) == 6
assert all(p['adjudicated_label'] is None and p['do_not_use_as_gold'] for p in candidates)
for p in candidates:
    source_kinds = sorted({records[p[side]]['source_kind'] for side in ['a', 'b']})
    display(Markdown('**' + p['case_id'] + '** (' + p['domain'] + ') — '
        + p['question_ru'] + '\n\n' + p['research_note_ru'] + '\n\n'
        'Источники: `' + '`, `'.join(source_kinds) + '`. Метка: **не установлена**.'))
display(Markdown('**Что можно защищать сейчас:** контекст восстановил известные '
    'связи в фиксированном наборе; простой поиск оказался конкурентоспособным; '
    'близость текста не подтверждает отношение выплат. Следующий эксперимент '
    'проверяет правила и контрсценарии на новом наборе с независимой разметкой. '
    'Шесть кандидатов выше — материал для такой проверки, не шесть доказанных связей.'))
print('Готово: локальные результаты прочитаны, исходный SHA-256 проверен; модели не запускались.')
'''),
]
nb = nbformat.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3'},
})
DEST.parent.mkdir(parents=True, exist_ok=True)
NotebookClient(nb, timeout=120, kernel_name='python3',
               resources={'metadata': {'path': str(ROOT)}}).execute()
errors = [out for cell in nb.cells for out in cell.get('outputs', [])
          if out.get('output_type') == 'error']
assert not errors, errors
assert len(nb.cells) == 8
nbformat.validate(nb)
nbformat.write(nb, DEST)
print(f'Created and executed: {DEST}; {len(nb.cells)} cells, no errors.')
