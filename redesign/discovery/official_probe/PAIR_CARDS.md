# Шесть разнообразных кандидатов для нового исследования

**Статус: discovery, без gold-разметки и без запуска моделей.** Два примера из macro, два из gaming, два из sports. Они дополняют политические карточки отдельно. Старый пилот не изменён.

Каждая карточка ссылается на `candidate_pairs.json` и записи в `source_records.json`. Там сохранены полные полученные primary/secondary, evidence для YES-пропозиции, URL, источник и ограничения. Для Polymarket это официальный сайт через поисковый индекс/текстовый render, **не Gamma API**; crawl обычно около двух недель назад. Актуальные полные условия и numeric market/condition ID не подтверждены. Kalshi — прямой официальный current/historical API; это все полученные API-поля правил, но не аудит общего rulebook/contract terms.

## 1. Recession: GDP-критерий против решения NBER

**A:** [KXRECSSNBER-26](https://external-api.kalshi.com/trade-api/v2/markets/KXRECSSNBER-26) — YES при двух последовательных кварталах отрицательного GDP в 2025 или 2026 по BEA.

**B:** [KXNBERRECESSQ-Q1-2026](https://external-api.kalshi.com/trade-api/v2/markets/KXNBERRECESSQ-Q1-2026) — YES, если NBER отнесёт предшествующий рецессии пик деловой активности к Q1 2026. Secondary уточняет выбор **квартала NBER**, независимо от указанного месяца.

**Почему интересно:** тема и слово recession совпадают, операционные определения различаются. Сам ticker A содержит NBER, хотя primary использует GDP. Направленную связь нельзя выводить из имени/тикера. Кандидат на отсутствие доказанной детерминированной связи; это не утверждение статистической независимости.

**Evidence:** два current API ответа. `case_id: macro_recession_definition`.

## 2. Fed hike: факт повышения против единиц размера повышения

**A:** [KXFEDHIKE-2-26DEC31](https://external-api.kalshi.com/trade-api/v2/markets/KXFEDHIKE-2-26DEC31) — YES при объявленном повышении target range/level после issuance и до 31 декабря 2026 включительно.

**B:** [KXRATEHIKE-2026-1](https://external-api.kalshi.com/trade-api/v2/markets/KXRATEHIKE-2026-1) — YES при ровно одной единице hike за календарный 2026 год. По secondary, 1–25 bp считаются одной, 26–50 bp — двумя, 51–75 bp — тремя.

**Почему интересно:** «одно повышение» не равно «одно заседание». Различаются также начало окна и квантор. Модель должна прочитать secondary и дату issuance; общей темы недостаточно.

**Evidence:** два current API ответа, даты issuance сохранены отдельно. `case_id: macro_hike_unit_and_window`.

## 3. GTA VI: release и postponement не обязательно дополнения

**A:** [KXGTA6ONTIME-26MAY26](https://external-api.kalshi.com/trade-api/v2/historical/markets?tickers=KXGTA6ONTIME-26MAY26&limit=1) — YES при выпуске GTA 6 на major platform (PS5, Xbox Series X/S, Windows) до 27 мая 2026.

**B:** [GTA 6 launch postponed?](https://polymarket.com/event/gta-6-launch-postponed) — YES при официальном объявлении до конца 26 мая о невыпуске к этой дате **или** при фактическом невыпуске в US к концу этого дня. Указаны purchase/download, исключены early access, beta и leaks.

**Почему интересно:** B содержит дизъюнкцию announcement OR realization. Объявление переноса с последующим своевременным релизом — гипотетический сценарий, из-за которого нельзя автоматически пометить A и B как complements. Дополнительно надо согласовать платформу и временные границы.

**Evidence:** точный исторический API A найден после 404 current endpoint; B — полный полученный фрагмент официальных indexed rules. Исторические результат и статус хранятся только в raw, исключены из `pairs_blind.jsonl`.

`case_id: gaming_release_vs_postponement`.

## 4. GTA VI: базовая игра и отдельно распространяемый online-сервис

**A:** [GTA VI released by October 31](https://polymarket.com/event/gta-vi-released-before-november-2026?outcomeIndex=0) — YES при официальной доступности игры для purchase/download в US к 31 октября 2026, 23:59 ET; pre-release формы исключены.

**B:** [KXGTAONLINE-GTA6ONLINE-27](https://external-api.kalshi.com/trade-api/v2/markets/KXGTAONLINE-GTA6ONLINE-27) — YES при доступности GTA VI Online для широкой публики до 1 января 2027. Secondary допускает multiplayer mode/service как в комплекте, так и отдельно, независимо от названия.

**Почему интересно:** название GTA VI и release маскирует различие продуктов и сроков. Из доступных формулировок не следует, что отдельный онлайн-сервис гарантирует указанный выпуск базовой игры. Кандидат на тематически близкую пару без установленной логической связи.

**Evidence:** A — event/outcome и indexed official rules, точный numeric contract ID отсутствует; B — current API.

`case_id: gaming_base_game_vs_online`.

## 5. Dodgers: World Series и National League

**A:** [Dodgers win World Series 2026](https://polymarket.com/event/mlb-world-series-champion-2026/will-the-los-angeles-dodgers-win-the-2026-world-series) — YES по исходу World Series для Dodgers.

**B:** [National League champion 2026, Dodgers](https://polymarket.com/event/mlb-2026-national-league-champion) — YES по исходу NLCS для Dodgers; команда явно присутствует в списке.

**Почему интересно:** кандидат на A⇒B при стандартной структуре турнира. Но нужны проверка этой внешней структуры и согласование payout exceptions. В полученном тексте NLCS стоит **November 31, 2026** — несуществующая дата; у World Series крайний срок иной. Ошибка сохранена, не исправлена догадкой.

**Evidence:** две официальные indexed страницы; B идентифицирован как event+outcome, numeric contract ID отсутствует. До уточнения даты и правил — **abstain**, не gold implication.

`case_id: sports_world_to_league`.

## 6. Dodgers World Series и Atlanta NLCS

**A:** тот же [Dodgers World Series](https://polymarket.com/event/mlb-world-series-champion-2026/will-the-los-angeles-dodgers-win-the-2026-world-series).

**B:** [Atlanta Braves win NLCS 2026](https://polymarket.com/event/mlb-2026-national-league-champion?marketSlug=will-atlanta-braves-win-the-2026-national-league-championship-series&outcomeIndex=1).

**Почему интересно:** кандидат на несовместимость YES-исходов при стандартной структуре MLB, а не просто отрицательная корреляция. Требуются те же проверки структуры, отмены/переноса и ошибочной даты. Это не complement: при победах других команд оба могут быть No.

**Evidence:** официальные indexed rules и точный публичный URL Braves. До проверки — provisional/abstain.

`case_id: sports_world_vs_other_league_winner`.

## Получение и ограничения

Проверка выполнена 29 сентября 2026 около 22:37–22:41 UTC. Gamma и прямой HTTP к официальному сайту вновь reset; повторного обхода блокировки не было. Другой работающий путь — публичный web search/render официальных страниц. Ни AI-generated Market Context, ни price/result, ни редакторские оценки агрегатора не использовались как условия.

Основные файлы:

- `candidate_pairs.json`: шесть карточек, hypotheses отдельно, `adjudicated_label=null`.
- `source_records.json`: 11 исходных записей с буквальными полученными правилами и provenance.
- `pairs_blind.jsonl`: только title/primary/secondary/outcome-label; без цен, статусов и результата.
- `packet_manifest.json` и отдельные request manifests: SHA-256, точные запросы и UTC-время.
- `web_domains_search.txt`, `web_sports_search.txt`: сохранённые tool render/index snapshots, включая контекст, который не поступает в model input.
- `build_candidates.py`: офлайн повторная сборка.

Резерв: monthly unemployment versus annual maximum, Poly versus Kalshi recession definitions, Fed windows. Они не включены в шесть карточек, чтобы снова не свести пилот к макроэкономическим порогам. Политические карточки формируются отдельно.

Ни одна карточка ещё не является независимым gold. Не рассчитывать по ним accuracy/recall и не превращать hypothesis в target label без разметки.
