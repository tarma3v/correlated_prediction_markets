"""Execute a compact review notebook against actual frozen experiment outputs."""
import json
import os
from pathlib import Path
import sys
import nbformat as nbf
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[1]
kernel=ROOT/'tmp/jupyter/kernels/research-local'
kernel.mkdir(parents=True,exist_ok=True)
(kernel/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],
                                            'display_name':'Research local','language':'python'}))
os.environ['JUPYTER_PATH']=str(ROOT/'tmp/jupyter')
md,code=nbf.v4.new_markdown_cell,nbf.v4.new_code_cell
nb=nbf.v4.new_notebook(cells=[
md('''# Выполненное автономное продолжение

286 контрактов → lexical/dense поиск → двунаправленный NLI → условная
проверка числовых отношений. Отдельно: чтение полных terms и межплощадочный кейс.

Этот notebook **читает и проверяет сохранённые результаты фактических запусков**.
Он не повторяет inference. Код запуска моделей находится в `extension/nlp/`.
Независимой человеческой разметки нет; никакие scores не являются market accuracy.
'''),
code('''from pathlib import Path
import json, hashlib
from collections import Counter
root=Path.cwd()
if root.name=='notebooks': root=root.parent
nlp=root/'extension/nlp'
def read(path): return json.loads((root/path).read_text())
manifest=json.loads((nlp/'artifact_manifest.json').read_text())
for f in manifest['files']:
    p=nlp/f['path']
    assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'], str(p)
print('Проверено файлов:',len(manifest['files']))
corpus=read('extension/nlp/corpus_run_manifest.json')
assert 'completed_at_utc' in corpus
assert hashlib.sha256((root/'pilot/markets.json').read_bytes()).hexdigest()==corpus['input_hash']
print('NLI завершена:',corpus['completed_at_utc'])
print('Пар / направленных входов:',corpus['n_pairs'],corpus['directional_inferences'])
'''),
md('''## 1. Что дал NLI по всему candidate pool

Каждая метка ниже — **предложение модели, verified=false**.
Не читать число exclusion как число правильно обнаруженных взаимоисключений.
'''),
code('''for label,n in sorted(corpus['output_counts'].items()):
    print(f'{label:28s} {n:4d}')
assert sum(corpus['output_counts'].values())==1188
print('Усечённых входов:',corpus['truncated_inputs'])
'''),
md('''## 2. Проверяемый числовой свидетель

Среди 839 пар одинаковых пороговых event-шаблонов есть 325 NLI-exclusion
кандидатов. Но в заданной общей неограниченной скалярной модели выбор значения
выше обоих порогов делает обе пропозиции истинными. Сравнение имеет силу внутри
этой модели; полные договорные выплаты оно не сертифицирует.
'''),
code('''consistency=read('extension/nlp/conditional_consistency.json')
print('Совпало шаблонных пар:',consistency['matched_pairs'])
print('Групп:',consistency['event_template_groups'])
print('Конфликтов exclusion:',consistency['exclusion_conflicts'])
example=next(r for r in consistency['records'] if r['conflict_in_scalar_scope'])
print(json.dumps(example,ensure_ascii=False,indent=2))
'''),
md('''## 3. Негативный результат улучшения retrieval

На двух post-hoc пороговых контролях k=10 lexical находит оба с 2012 парами.
k=5 + шаблоны тоже находит оба, но требует 3187 пар. Поэтому улучшение
шаблонного генератора при одинаковом бюджете **не установлено**.
Это не recall на неизвестных связях. [Полный протокол](../extension/retrieval/README.md).

## 4. Порядок eligibility-фильтра меняет бюджет
'''),
code('''eligibility=read('extension/nlp/eligible_retrieval.json')
for kind in ['lexical','dense']:
    print(kind,eligibility['methods'][kind]['union']['5'])
print('Больше кандидатов не означает более высокую точность при равных затратах.')
'''),
md('''## 5. Диагностика реальных пар

Выбранные заранее в первом пилоте примеры, три views. Ниже только title_rules
для двух кейсов; остальные результаты сохранены, а не скрыты.
'''),
code('''pred=read('extension/nlp/nli_predictions.json')
for r in pred:
    if r['kind']=='real_exploratory' and r['view']=='title_rules' and r['id'] in ['different_periods','strict_thresholds']:
        print(r['id'],r['direction'],r['prediction'],
              {k:round(v,3) for k,v in r['probabilities'].items()})
'''),
md('''## 6. Аудит собственной синтетической проверки

В v1 были дубли и неоднозначность real CPI / continuous toy domain. V2 сохраняет
историю, вводит вымышленные непрерывные показатели и дедуплицирует входы до
нового inference. Это поправка после анализа, не новый закрытый тест.
'''),
code('''v2=read('extension/nlp/synthetic_v2_manifest.json')
print('Правильных / уникальных входов:',v2['correct'],v2['n_unique_ordered_text_pairs'])
print('Always-neutral на этом составе:',v2['gold_counts']['neutral'])
print('Матрица ошибок:')
for r in v2['confusion']:
    print(r['gold'],'->',r['prediction'],':',r['n'])
print('Шаблоны зависимы; это не точность на реальных рынках.')
'''),
md('''## 7. Что изменилось после чтения документов

Полные Kalshi terms содержат разные fallback/expiry для месячного YoY и
любого месяца года. Поэтому обычное числовое следование требует scope.
Одна межплощадочная пара также найдена, но Polymarket rules взяты из поискового
индекса с непроверенной актуальностью; безусловный вывод отклонён.

- [Аудит полных условий](../extension/terms/AUDIT_RU.md)
- [Межплощадочный пример и качество источников](../extension/cross_platform/README.md)
- [Обновлённый исследовательский вывод](../EXPERIMENT_UPDATE_RU.md)

Главная гипотеза следующего этапа: отдельно измерить эффект полных документов,
структурирования и контрпримеров при равном бюджете и независимом human gold.
'''),
])
NotebookClient(nb,timeout=60,kernel_name='research-local',resources={'metadata':{'path':str(ROOT)}}).execute()
nb.metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
             'language_info':{'name':'python','version':'3.11'}}
nbf.validate(nb)
path=ROOT/'notebooks/autonomous_results.ipynb'; nbf.write(nb,path)
print(path)
print('Executed code cells:',sum(c.cell_type=='code' for c in nb.cells))
