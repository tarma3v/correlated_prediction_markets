# Предварительная типизация 32 внешних пар

Разобраны **все 27 `different` и 5 `unsure`** из внешнего авторского аудита. Метка `different` означает, что автор счёл рынки различными; `unsure` означает, что автор не установил решение. Ни одна из них сама по себе не доказывает отсутствие иной связи. Новая разметка — исследовательские предложения с условиями, **не human gold** и не основание для оценки accuracy модели или арбитражной стратегии.

Получены свежие HTTP200 ответы официального Kalshi API для всех 32 точных тикеров: просмотрены primary/secondary rules, заголовки и даты. У Polymarket ограниченные попытки Gamma, CLOB и прямого HTML завершились сбросом соединения. Для отдельных событий прочитаны индексированные официальные правила; точное сопоставление внешнего ID с их актуальной версией через API не подтверждено. Поэтому **безусловных ограничений на реальные выплаты не сертифицировано**: у всех карточек `established_contract_forbidden_states=null`.

Итог: **7 условных кандидатов с логическим ограничением** — 2 A⇒B, 3 DISJOINT, 2 EQUIVALENT для обычного заседания; 20 NO_HARD_RELATION при указанном понимании событий; 4 ABSTAIN из-за недостающих правил; 1 OUT_OF_BINARY_SCOPE. Число ограничений не задавалось заранее. Пять NHL-карточек представляют одну смысловую семью и не являются пятью независимыми подтверждениями гипотезы.

## Как читать состояния

**A всегда Polymarket, B всегда Kalshi.** `10` означает A=YES, B=NO.

| Тип | Запрещённые состояния при выполнении предпосылок |
|---|---|
| A_IMPLIES_B | 10 |
| B_IMPLIES_A | 01 |
| EQUIVALENT | 01,10 |
| DISJOINT | 11 |
| COMPLEMENT | 00,11 |
| NO_HARD_RELATION | ∅: все четыре состояния не исключены принятой семантикой |
| ABSTAIN / OUT_OF_BINARY_SCOPE | null: таблица не установлена либо не описывает полное пространство выплат |

**`null` не равно `[]`.** Неизвестное состояние не помечено допустимым. Для NO_HARD_RELATION приведены иллюстративные сценарии всех четырёх состояний. Это не утверждение статистической независимости, нулевой корреляции или отсутствия общего фактора риска. Положительная корреляция NHL/наград записана только отдельной гипотезой механизма: цены, временные ряды и статистическая значимость здесь не анализировались.

## Что проверка изменила

- **OpenAI:** обычное завершённое IPO с большой оценкой подразумевает один из признаков подтверждения IPO, перечисленных Kalshi. Остаются проверки преемника, direct listing/SPAC и сроков. Это условное A⇒B, а не тождество контрактов. [Индексированные официальные правила Polymarket](https://polymarket.com/uk/event/openai-1t-ipo-before-2027?outcomeIndex=1), [точный Kalshi API](https://api.elections.kalshi.com/trade-api/v2/markets/KXIPO-26-OPENAI).
- **BoE25 против >25:** DISJOINT нельзя выводить до проверки округления. Официальный одноимённый контракт [Polymarket US](https://polymarket.us/event/boe-2026-11-05) содержит округление, но это другой контракт. Значение 30, округлённое к 25, даёт контрпример 11 для такой интерпретации; международные правила этого ID остаются недостающими.
- **ФРС 50+ против >25:** индексированные [правила Polymarket](https://polymarket.com/event/fed-decision-in-december-20260729232808632?marketSlug=will-there-be-no-change-in-fed-interest-rates-after-the-december-2026-meeting-20260729232808635&outcomeIndex=1) округляют величину вверх до 25. В обычном сценарии корзина 50+ эквивалентна >25. Но Kalshi потерял знак сравнения в primary, а правила отмены/переноса различаются: полное равенство выплат не заявлено.
- **Texas/Atlanta и Chargers/division–seed 5:** условные DISJOINT, не complement. Для Chargers проверен официальный [NFL Record & Fact Book 2025](https://static.clubs.nfl.com/image/upload/saints/bvaqvsl0fwdhlxu6wnw2.pdf): нужна также применимость правил к 2026–27. Для обеих пар 00 возможно.
- **NHL conference/division:** вывод зависит от того, что conference означает плей-офф, а division — регулярный сезон. При этом понимании обе импликации неверны; общий фактор силы команды — лишь гипотеза корреляции. [Официальный формат NHL](https://www.nhl.com/info/standings-info/playoff-format).
- **Рецессия:** [KXRECSSNBER-27](https://api.elections.kalshi.com/trade-api/v2/markets/KXRECSSNBER-27) фактически задаёт два последовательных отрицательных Advance GDP квартала Q4 2026–Q4 2027, несмотря на NBER в тикере. A-правила на [официальной странице Polymarket](https://polymarket.com/event/us-recession-by-end-of-2027-20260807185409760) не извлечены. Поэтому B⇒A не подтверждено: важны определение и публикация Q4 2027 уже в 2028. AI-summary страницы исключён из доказательств.
- **Небинарные выплаты:** смерть Трампа допускает расчёт по рыночной цене/решению комитета; ничьи рейтинга AI и совместные спортивные награды допускают 1/N. Бинарные truth tables не описывают эти ветки.

## Все карточки

Это краткий указатель. Предпосылки, недостающие доказательства, альтернативы и контрпримеры находятся в `typed_pairs.json`; в столбце состояний приведены только **условные** ограничения.

| ID | A / B | Кандидат | Запрещены |
|---|---|---|---|
| rel_01 | OpenAI: IPO $1 трлн+ / подтверждение IPO | A ⇒ B (условно) | 10 |
| rel_02 | Трамп: уход / уход, объявление и смерть | OUT_OF_BINARY_SCOPE | не определены |
| rel_03 | Half-Life 3: Game of the Year / полный релиз США | NO_HARD_RELATION | ∅ |
| rel_04 | BoE: корзина снижения 25 / снижение>25 | ABSTAIN | не определены |
| rel_05 | NFL 2027: Texas / Atlanta | DISJOINT (условно) | 11 |
| rel_06 | Columbus: конференция / Metropolitan | NO_HARD_RELATION | ∅ |
| rel_07 | LA Kings: конференция / Pacific | NO_HARD_RELATION | ∅ |
| rel_08 | Tampa Bay: конференция / Atlantic | NO_HARD_RELATION | ∅ |
| rel_09 | Vegas: конференция / Pacific | NO_HARD_RELATION | ∅ |
| rel_10 | NY Rangers: конференция / Metropolitan | NO_HARD_RELATION | ∅ |
| rel_11 | ФРС: снижение 50+ / снижение>25 | EQUIVALENT (обычное заседание) | 01, 10 |
| rel_12 | ФРС: повышение 50+ / повышение>25 | EQUIVALENT (обычное заседание) | 01, 10 |
| rel_13 | ФРС: уровень 5% / пять изменений | NO_HARD_RELATION | ∅ |
| rel_14 | Phantom Blade Zero: Audio Design / Game of the Year | NO_HARD_RELATION | ∅ |
| rel_15 | BTC: достигнет 100k / 50k раньше 100k | NO_HARD_RELATION | ∅ |
| rel_16 | Anthony Davis: обмен / следующая команда Philadelphia | NO_HARD_RELATION | ∅ |
| rel_17 | Национализация: выборы / SpaceX | NO_HARD_RELATION | ∅ |
| rel_18 | Al-Shamal лидирует в перерыве / Al-Ittihad выигрывает≥3 | NO_HARD_RELATION | ∅ |
| rel_19 | Rocco Baldelli: следующий менеджер Phillies / Red Sox | NO_HARD_RELATION | ∅ |
| rel_20 | Taylor Swift: US#1 / Global#2 | NO_HARD_RELATION | ∅ |
| rel_21 | Image AI: конец октября /18 сентября | NO_HARD_RELATION | ∅ |
| rel_22 | Рецессия: к концу 2027 / GDP-пары 2026–27 | ABSTAIN | не определены |
| rel_23 | Нет урагана в сентябре / ураган до октября | ABSTAIN | не определены |
| rel_24 | Al-Ittihad: лидерство в перерыве / выигрыш≥2 | NO_HARD_RELATION | ∅ |
| rel_25 | Truth Social:11–18 /13–19 сентября | NO_HARD_RELATION | ∅ |
| rel_26 | Mendoza: named by Week1 / depth chartWeek1–2 | ABSTAIN | не определены |
| rel_27 | BoE: повышение 50+ / повышение 1–25 | DISJOINT (условно) | 11 |
| rel_28 | Dante Moore: Heisman / Walter Camp | NO_HARD_RELATION | ∅ |
| rel_29 | Bo Jackson: Heisman / Doak Walker | NO_HARD_RELATION | ∅ |
| rel_30 | Julian Sayin: Heisman / Walter Camp | NO_HARD_RELATION | ∅ |
| rel_31 | JUUL Fruit Medley: relaunch / public release | A ⇒ B (условно) | 10 |
| rel_32 | Chargers: AFC West champion / AFC seed #5 | DISJOINT (условно) | 11 |

## Источники и проверка

`typed_pairs.json` содержит 32 записи с внешними ID, короткими **производными описаниями**, источниками, областью действия, недостающими доказательствами и `human_gold=false`. Оригинальные полные fixture, ответы API, страницы и модельные outputs сюда не скопированы. `kalshi_provenance.json` хранит URL, время получения, SHA256 прочитанного ответа и отдельный хеш полей названия/правил без меняющихся цен и объёмов; `sources.json` отделяет официальный API, индексированную страницу, общий спортивный регламент и источник, который не удалось использовать как правила нужного контракта.

Хеш без сохранённого полного ответа не восстанавливает исторический текст. Заметки позволяют проследить происхождение вывода, но перед независимой human adjudication понадобятся официальные версии правил на согласованную дату. Свежие API-поля могут отличаться от правил на дату исходного авторского аудита; его историческая разметка не пересчитывается как «ошибочная» автоматически.

Дополнительные первичные источники объясняют спорные спортивные/игровые выводы: [TGA eligibility FAQ](https://origin-stage.thegameawards.com/faq) допускает Early Access; [архив TGA 2020](https://thegameawards.com/rewind/year-2020) показывает совместную победу в двух категориях; [Heisman/Ron Dayne](https://www.heisman.com/articles/ron-dayne-25th-anniversary-heisman-trophy-profile/) — получение нескольких футбольных наград. В 2021 победители [Walter Camp](https://waltercamp.org/michigan-state-running-back-kenneth-walker-iii-is-the-2021-walter-camp-player-of-year/) и [Heisman](https://www.heisman.com/articles/bryce-young-of-alabama-wins-2021-heisman-trophy/) различались. Это контрпримеры универсальным правилам, не статистическая оценка корреляции.

Проверка из корня проекта, обычный Python3, без зависимостей и сети:

```bash
python3 relations/verify.py
```

Verifier проверяет 32 записи, уникальность ID, исходный состав 27+5, соответствие live Kalshi provenance, кодирование типов/состояний и отсутствие gold-утверждений. Дополнительно проверены границы округления через Decimal. Если исходный fixture ещё присутствует, проверяются его SHA256 и точное множество выбранных пар; после его удаления основная проверка остаётся автономной. Verifier не доказывает корректность интерпретации внешних правил. JSON Schema сохранена в `typed_pairs.schema.json`.

