"""Build and execute the introductory notebook in the current Python environment."""
import json
import os
from pathlib import Path
import sys

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
kernel_dir = ROOT / "tmp" / "jupyter" / "kernels" / "research-local"
kernel_dir.mkdir(parents=True, exist_ok=True)
(kernel_dir / "kernel.json").write_text(json.dumps({
    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
    "display_name": "Research local Python", "language": "python",
}))
os.environ["JUPYTER_PATH"] = str(ROOT / "tmp" / "jupyter")
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
nb = nbf.v4.new_notebook(cells=[
md("""# Первый эксперимент: смысл контракта и поиск похожих пар

29 сентября 2026. **Выполненный учебный notebook, не benchmark качества NLP.**
Данные: сохранённые публичные тексты Kalshi. Интернет, аккаунт и LLM API не нужны.
Необходимы библиотеки из `pilot/requirements.txt`. Для нового запуска выберите Python 3.11.

Цель: увидеть, почему сходство текста не равно логической связи, и научиться
различать эмпирический пилот и синтетическую проверку метрики.
"""),
code("""from pathlib import Path
import json, subprocess, sys
root = Path.cwd()
if root.name == 'notebooks':
    root = root.parent
assert (root / 'pilot/markets.json').exists(), 'Откройте notebook из корня проекта или notebooks/'
markets = json.loads((root / 'pilot/markets.json').read_text())
print('Сохранённых контрактов:', len(markets))
print('Площадки:', sorted({m['venue'] for m in markets}))
"""),
md("""## 1. Пересчитать retrieval и проверить целостность данных

Скрипт сверяет SHA256 исходных JSON, нормализованного снимка и входов.
Затем считает три TF-IDF представления. Он использует квадратичную матрицу;
это небольшая демонстрация, не реализация масштабного ANN-поиска.
Вывод ниже получен исполнением кода, не заполнен вручную.
"""),
code("""proc = subprocess.run([sys.executable, str(root/'pilot/pilot.py'), 'analyze', '--top-k', '5'],
                      check=True, capture_output=True, text=True, cwd=root)
print(proc.stdout)
"""),
md("""**Как читать результат:** 1 188 — число отобранных пар. 2,915% — доля от 40 755
возможных пар. У нас ещё нет gold-разметки, поэтому recall/precision неизвестны.
Выборка нерепрезентативна; Polymarket не был доступен при сборе.
"""),
code("""proc = subprocess.run([sys.executable, str(root/'pilot/review_cases.py')],
                      check=True, capture_output=True, text=True, cwd=root)
cases = json.loads((root/'pilot/results/review_cases.json').read_text())
print('Подготовленных разборов:', len(cases))
by_case = {c['case_id']: c for c in cases}
case = by_case['same_title_thresholds']
for side in ['a','b']:
    m = case[side]
    print(side.upper(), m['id'], '\\nЗаголовок:', m['title'], '\\nПравило:', m['primary'], '\\n')
print('Сходство заголовков:', case['retrieval']['title']['similarity'])
"""),
md("""## 2. Ваше рассуждение

Одинаковые заголовки скрывают пороги ≥7% и ≥6,5%. При одинаковых остальных
условиях первый влечёт второй, но не наоборот. Попробуйте придумать число,
при котором второй Yes, а первый No. Затем проверьте полные условия серии:
API primary rules ещё не гарантируют полноту спецификации.
Интерпретации кейсов сделаны с помощью AI; это не независимый человеческий gold.
"""),
code("""case = by_case['different_periods']
print(case['a']['primary'])
print(case['b']['primary'])
print('Показатели поиска:', case['retrieval']['rules'])
print('Предварительный разбор:', case['note_ru'])
"""),
md("""Почти одинаковый текст и rank=1 не доказывают следование: месяцы различаются.
И наоборот, полезная пороговая пара может оказаться за пределами top-5.
"""),
code("""case = by_case['strict_thresholds']
print('A:', case['a']['title'])
print('B:', case['b']['title'])
for view, score in case['retrieval'].items():
    print(view, score)
assert all(not v['in_top5_union'] for v in case['retrieval'].values())
"""),
md("""## 3. Проверить метрики без LLM

Следующие числа получены на **искусственно заданных мирах**, а не по рыночной
выборке. Они проверяют корректность определения метрики.
"""),
code("""sys.path.insert(0, str(root/'logic'))
from metric_demo import run
demo = run()
print(json.dumps(demo, ensure_ascii=False, indent=2))
"""),
md("""Треугольник из трёх взаимоисключающих победителей логически корректен,
но его signed frustration равна 1/3. Два независимых события с P(Yes)=0,1
совпадают в среднем в 82% случаев. Поэтому нужны метрики конкретных
ограничений выплат и независимая разметка.

## 4. Первый самостоятельный шаг

Выберите ещё одну пару в `pilot/results/candidates.json`. Найдите её контракты
в `markets.json`. Выпишите объект измерения, период, источник, порог, исключения.
Для каждого состояния 00/01/10/11 укажите: запрещено с основанием,
возможно с конкретным сценарием, или неизвестно. Не смешивайте unknown
с доказанным отсутствием логической связи.

Дальше сравнивать NLI/LLM можно только после согласования инструкции
`protocol/annotation_guide.md` и получения gold. Этот notebook не запускает
NLI/LLM, не совершает сделок и не воспроизводит численные результаты статьи.
"""),
])
nb.metadata = {"kernelspec":{"display_name":"Python 3", "language":"python", "name":"python3"},
               "language_info":{"name":"python", "version":"3.11"}}
NotebookClient(nb, timeout=120, kernel_name="research-local", resources={"metadata":{"path":str(ROOT)}}).execute()
nb.metadata["kernelspec"] = {"display_name":"Python 3", "language":"python", "name":"python3"}
nbf.validate(nb)
target = ROOT/'notebooks'/'first_steps.ipynb'
nbf.write(nb, target)
print(target)
print('Executed code cells:', sum(c.cell_type == 'code' for c in nb.cells))
