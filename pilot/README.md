# Воспроизводимый пилот: тексты резолюшена и лексический retrieval

Это **выполненный инженерный пилот на реальных публичных данных**, подготовленный 29 сентября 2026 по времени Дубая (UTC: 28 сентября, около 21:01). Это не готовый benchmark и не оценка качества NLP-модели.

## Что выполнено

- Сохранены 286 уникальных контрактов Kalshi из 19 событий. У всех есть `rules_primary`; у 46 пуст `rules_secondary`.
- Выборка намеренно небольшая и нерепрезентативная: первые 80 открытых non-MVE контрактов API плюс до 40 открытых контрактов из каждой из семи выбранных экономических серий. В текущем снимке первые 80 оказались platinum/palladium; шесть серий дали ещё 206 контрактов; `KXFEDRATEMIN` вернула пустой список.
- Сохранены сырые JSON-ответы, полные URL запросов, UTC-время, SHA-256 файлов и нормализованных входов. Два дополнительных снимка series metadata содержат ссылки на полные contract terms и источник CPI — BLS.
- Запущены три варианта TF-IDF: только title, только primary+secondary rules, title+rules. Каждый score — среднее cosine для word 1–2 grams и character-within-word 3–5 grams; `sublinear_tf=True`, sklearn IDF defaults. Цифры сохраняются; character features сохраняют десятичный контекст. Это лексический baseline, **не semantic embeddings/NLI/LLM**.
- Для каждого контракта берётся top-5; ненаправленные пары объединяются между вариантами. Из 40 755 возможных пар получено 1 188 кандидатов (2,915%). Это доля кандидатов, **не recall и не accuracy**.

| Представление | Пар в top-5 union внутри варианта | Из разных event |
|---|---:|---:|
| title | 888 | 346 |
| rules | 943 | 147 |
| title + rules | 953 | 186 |

Матрицы сходства вычисляются полностью: память и pair-scoring квадратичны по числу контрактов. Уменьшение количества downstream-кандидатов не означает ускорение построения этой матрицы. Для большого корпуса понадобятся blocking и inverted index/ANN; этот код проверяет экспериментальный путь на малой выборке.

## Что удалось увидеть

1. **Одинаковый title не задаёт одинаковый контракт.** Шесть контрактов имеют title `Inflation surge in 2026?`, но primary rules задают пороги ≥4.5%, ≥5%, ≥5.5%, ≥6%, ≥6.5%, ≥7%. Для ≥7% и ≥6.5% title score = 1.0; это вложенность, а не эквивалентность.
2. **Добавить весь rules text недостаточно.** `KXCPICOREYOY-26DEC-T2.6` и `KXCPICOREYOY-26NOV-T2.6` получают rules score 0.973437 и взаимный rank 1, хотя относятся к разным двенадцатимесячным периодам. Из текста не следует импликация. Статистическая зависимость здесь не измерялась.
3. **Даже простой positive control может выпасть из top-k.** Октябрьский CPI >0.9% логически влечёт CPI >0.8% при одинаковых остальных условиях. Пара `KXCPI-26OCT-T0.9` / `KXCPI-26OCT-T0.8` не попала в top-5 ни одного варианта: ranks rules = 7 и 8. Это конкретный пример пропуска, а не оценка общей полноты.
4. **Core и headline CPI — разные показатели.** Для ноябрьского порога >0.2% title score = 0.860176, rules score = 0.544710. Пара извлекается title-вариантом; детерминированная связь из этих текстов не установлена.
5. **Связи между горизонтом и его частью требуют другого retrieval.** Декабрьский YoY CPI >5% и любой месяц 2026 с YoY CPI ≥5% — условный кандидат на импликацию. Оба series metadata называют BLS, но полные PDFs условий ещё не сверены. Пара отсутствует в top-5 всех вариантов; rules ranks = 283 и 59. Присваивать ей статус подтверждённой контрактной гарантии пока нельзя.

Все шесть разобранных пар, полные тексты, URL, предварительная интерпретация, similarities и ranks сохранены в `results/review_cases.json`. Кейсы отобраны после просмотра результатов и интерпретированы с помощью AI; независимой разметки нет. Они **не gold test set**. Positive controls внутри уже известных event показывают необходимость правильно различать тип связи, но не доказывают способность обнаруживать неизвестные межсобытийные связи.

## Как воспроизвести офлайн

Рекомендуемый Python 3.11. Команды для Linux/macOS, из каталога `pilot`:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python pilot.py analyze --top-k 5
python review_cases.py
```

Скрипт `analyze` сверяет hashes raw-файлов, `markets.json` и нормализованных входов. Стабильный tie-break — порядок записей в снимке. Timestamp результата обновится; числа кандидатов и similarities должны совпасть при указанных зависимостях. В текущей среде использован Python 3.11.4, requests 2.31.0, numpy 1.25.1, scipy 1.11.1, scikit-learn 1.3.0. Это версии фактического запуска, а не рекомендация для производственного окружения.

## Как получить новый снимок

```bash
python pilot.py --root snapshot_new collect
python pilot.py --root snapshot_new analyze --top-k 5
```

Новый снимок будет содержать текущие контракты и даст другие результаты. Скрипт намеренно не перезаписывает существующий manifest без `--overwrite`. Всего не более 11 публичных GET-запросов, без полного обхода страниц; market cap 460 до удаления дубликатов, включая до 100 Polymarket. Никакие ордера, сделки или аутентифицированные запросы не выполняются. Для `review_cases.py` используется сохранённый исходный снимок рядом со скриптом: зафиксированные кейсы нельзя автоматически переносить на новую выборку.

## Доступность Polymarket и полнота условий

В этой среде запрос `https://gamma-api.polymarket.com/markets` завершился `ConnectionResetError(54, 'Connection reset by peer')`. Ошибка, параметры и UTC-время сохранены в `raw/polymarket_open.json` и `manifest.json`. Это локальный результат доступа, не утверждение, что Polymarket API недоступен вообще. В пилоте **нет полученных контрактов Polymarket, межплощадочного сравнения или измерения его качества**. Коллектор содержит ветку нормализации Gamma для последующего запуска при доступности API.

Первичные API-поля — не гарантия, что собраны все юридически и технически значимые условия. Для Kalshi нужно дополнительно включить series contract_terms, rulebook, settlement_sources, версии и исключения; для Polymarket — изменения/уточнения и применимые oracle/ancillary data. В этом пилоте PDFs условий по ссылкам из series metadata не разобраны. API `close_time` и `expected_expiration_time` не заменяют целевой период из текста.

## Структура

- `pilot.py` — CLI коллектора и retrieval; `requirements.txt` — версии запуска.
- `manifest.json` — запросы, ошибки, hashes; `raw/` — исходные ответы.
- `markets.json` — нормализованные контрактные тексты и идентификаторы.
- `results/summary.json` — выполненные числовые результаты, input hash, версии.
- `results/candidates.json` — 1 188 candidate pairs и три score.
- `review_cases.py`, `results/review_cases.json` — воспроизводимые evidence packets для выбранных кейсов.
- `raw/discovery_series_economics.json` — вспомогательный исходный discovery-запрос, использованный для выбора семи series; не часть анализируемых 286 контрактов.

## Официальные источники полей

- [Kalshi Get Markets](https://docs.kalshi.com/api-reference/market/get-markets): `rules_primary`, `rules_secondary`, фильтры `series_ticker`, `mve_filter=exclude`; публичный endpoint.
- [Polymarket Discover Markets](https://docs.polymarket.com/market-data/discover-markets): публичное получение markets/events без аутентификации.
- [Gamma OpenAPI](https://gamma-api.polymarket.com/docs): схема market metadata и description.
- [Kalshi series CPI YoY](https://external-api.kalshi.com/trade-api/v2/series/KXCPIYOY) и [Inflation surge](https://external-api.kalshi.com/trade-api/v2/series/KXLCPIMAXYOY): источник и ссылки на полные условия.

Первые исследовательские выводы: извлекать `underlying / time window / aggregation / comparator / threshold / source / revision policy`; генерировать threshold- и time-window-кандидатов наряду с текстовыми; отдельно оценивать внутри event, между event и между площадками; размечать независимый gold до сравнений качества моделей.
