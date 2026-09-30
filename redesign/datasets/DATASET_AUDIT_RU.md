# Открытые данные для нового пилота: проверка доступности

Проверено 30 сентября 2026. Модели в этой проверке не запускались. Полный открытый peer-reviewed benchmark с текстами правил обеих площадок и независимо проверенными типами отношений не найден. Найден пригодный внешний **author audit для оценки retrieval**, с существенными ограничениями. Доступность файла не означает наличие разрешительной лицензии.

## 1. Рекомендуемый ограниченный внешний тест: nl2992/prediction-pipeline

[Репозиторий](https://github.com/nl2992/prediction-pipeline); [точный snapshot](https://github.com/nl2992/prediction-pipeline/blob/f7f652b7ea7c2285fca7c2aa7c02785b11ba9e84/tests/fixtures/endorsed_audit_2026-09-14.json). Это инженерный публичный репозиторий; статус научного benchmark ему не приписывается.

Файл реально скачан, HTTP 200, 307100 байт. Commit `f7f652b7ea7c2285fca7c2aa7c02785b11ba9e84`, SHA256 файла `c61e60b667ea59d14b9f247c3ba268249dfb38682389ecf56fb306d688840141`.

Источник датирует выборку 14.09.2026: 343 пары из сигналов работающего pipeline и 150 дополнительных пар из стратифицированной по категориям выборки кандидатов, одобренных авторским matcher v2. Это **выборка после фильтра matcher**, а не случайная выборка всех возможных пар.

Независимый локальный аудит файла:

| Свойство | Результат |
|---|---:|
| Строки / уникальные пары ID | 493 / 493 |
| Уникальные контракты Polymarket / Kalshi | 493 / 493 |
| Метки автора same / different / unsure | 461 / 27 / 5 |
| Повторы ID-пар / конфликты меток и metadata | 0 / 0 |
| Категории | pop 303; election 111; sports 43; political 25; economic 11 |
| Группы положительных пар по двум event titles | 254 |
| Самые крупные группы | Republican nominee 2028: 19; Democratic nominee 2028: 16 |

Поля: обе стороны имеют title, event_title, close date и ID (`poly_id` — condition hash; `kalshi_ticker` — ticker). Имеются `label`, `reason_class`, сведения о решении авторского matcher. **Полных resolution rules нет.** Авторский смысл same — идентичный исход с учетом субъекта, стороны, порога, места и горизонта. Это заявленный критерий разметки, не независимо доказанная эквивалентность выплат.

Provenance: [загрузчик fixtures](https://github.com/nl2992/prediction-pipeline/blob/f7f652b7ea7c2285fca7c2aa7c02785b11ba9e84/audit_fixture.py) называет fixtures human-labelled. [Коммит добавления этих наборов](https://github.com/nl2992/prediction-pipeline/commit/4dd2c07a27554c7bda1277f006a48fbde14f92c1) содержит AI co-author. Протокол, имена/число независимых аннотаторов и межэкспертное согласие не найдены. Поэтому корректное обозначение — **author-audit labels**, не human gold и не автоматически LLM labels. Упоминание 50 hand-labelled пар в другом validation log относится к отдельному curated fixture и не подтверждает качество этих 493.

Причины 27 different: scope mismatch 8, different subject 6, threshold mismatch 4, moneyline/spread 2, horizon mismatch 2, и по одному: award category vs annual release, different award category, different location, inverted outcome, different measurement window. Среди пяти unsure: три scope и два threshold mismatch. Сохранены все отрицательные пары для дальнейшего чтения.

**Что измерять:** искать известный counterpart для каждой из 461 positive query среди 493 контрактов другой площадки, в обе стороны; Recall@1/5/10 и MRR относительно авторских positives. Публиковать также среднее по группам event titles и категориям, отдельно результаты на двух source subsets. Группа event titles — воспроизводимый приближенный идентификатор семейства, не экспертно размеченное семейство. Неразмеченные cross-pairs нельзя объявлять отрицательными; такая оценка не дает глобальный recall по всем рынкам, precision классификации или доказанную resolution equivalence. Поля с метками/author matcher не включать во вход retrieval.

**Лицензия:** GitHub metadata сообщает `license: null`, LICENSE в recursive tree не найден. Не называть корпус CC-BY/MIT; сохранять источник и pin. Полный upstream fixture и его точные реконструкции исключены из Git; сохранены ссылка, commit, SHA-256 и скрипт загрузки. Точечные исследовательские разборы и агрегаты не объявляются перелицензированным upstream-корпусом.

Готовые локальные файлы:

- [source.json](source.json) — URL, commit и SHA-256 исходного snapshot. Полная копия не распространяется; `python3 scripts/fetch_reference_inputs.py` восстанавливает локальные ignored inputs.
- `author_audit_pairs_unique.json` — 493 пары, добавлены только source_subset и source_row.
- `polymarket_author_audit_markets.json`, `kalshi_author_audit_markets.json` — корпуса по 493 рынка.
- `author_audit_negative_pairs.json`, `author_audit_summary.json` — отрицательные примеры и аудит.
- `scripts/audit_author_pairs.py` — воспроизводит аудит офлайн.
- `pinned_access.json` — URL, HTTP status, размеры и SHA256 загрузок.

## 2. KalshiBench-v2: настоящие описания, без pair labels

[Dataset card](https://huggingface.co/datasets/2084Collective/kalshibench-v2), revision `e70c1077093e12ca604429d7f7dc7562127e81f2`. [Parquet](https://huggingface.co/datasets/2084Collective/kalshibench-v2/resolve/e70c1077093e12ca604429d7f7dc7562127e81f2/data/train-00000-of-00001.parquet) реально скачан, HTTP 200, 202676 байт, 1531 строк по metadata. Поля: id, question, description, category, close_time, ground_truth, market_probability, series_ticker, source.

Три строки были получены через официальный HF rows API; изучен sample parquet. Копии rows/parquet не распространяются. В sample есть короткие критерии IPO и развернутое правило ухода лидера с особым исходом при смерти. **ground_truth — реализовавшийся исход отдельного рынка, не тип отношения.** В первых двух строках один id обозначает разные стороны IPO-события: нельзя считать id уникальным market ID. Полноту/актуальность правил относительно официальных terms не проверяли. Лицензия в card metadata не указана. Это возможный дополнительный корпус текстов, а не замена labeled relation benchmark.

## 3. Pytheum: обещанные артефакты сейчас недоступны

[Repo](https://github.com/pytheum/pytheum), [datasets manifest](https://github.com/pytheum/pytheum/blob/main/datasets/MANIFEST.json). В README заявлены settlement-verified cross-platform pairs, код MIT, данные CC-BY 4.0. Однако в tree имеются только README/MANIFEST: сами exports не committed, ссылок скачивания manifest не содержит. Файл equivalence-export.jsonl.gz заявлен размером 12.8 MB и 142179 парами; **этот корпус не получен, числа не верифицированы**.

GitHub releases endpoint вернул `[]`; документированные api.pytheum.com/v1/markets/matched?limit=5, /v1/status и /healthz вернули HTTP 404 / DEPLOYMENT_NOT_FOUND. Ответы сохранены. Поэтому нельзя строить текущий пилот на заявленных 142 тысячах пар или выдавать их за доступный проверенный dataset.

## 4. Отрицательные результаты поиска

Для [Semantic Non-Fungibility, arXiv:2601.01706](https://arxiv.org/abs/2601.01706) публичный скачиваемый корпус в ограниченном поиске по primary sources не найден; формулировка доступности upon publication не является URL данных. У Jon-Becker/prediction-market-analysis большой trade snapshot, но проверенная схема market metadata не содержит resolution descriptions или pair labels. ImpliedData public sample исключает cross-venue links; данные с title-only не решают эту задачу. ForesightFlow resolution typology — метки механизма resolution, а не отношений между контрактами. ClearMarket проверяется параллельно другим участником и здесь не оценен.

**Практическое решение:** внешний retrieval-тест на 493 author-audit парах плюс отдельные проверенные кейсы full rules. Эти две части дают разные виды свидетельств и не должны объединяться в вымышленную единую метрику market-quality accuracy.
