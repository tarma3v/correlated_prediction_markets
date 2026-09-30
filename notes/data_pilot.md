# Результат агента: реальный воспроизводимый пилот

Готов в `pilot/`. Дата получения — 2026-09-28 около 21:01 UTC.

**Фактические числа:** 286 Kalshi markets, 19 event; 40 755 всех пар; 1 188 кандидатов в union top-5 трёх lexical TF-IDF вариантов (title / rules / title+rules). 0 пустых primary, 46 пустых secondary. Нет gold-разметки и измерений precision/recall, прибыльности или межплощадочного matching. Матрица pairwise dense, вычисление O(n²); 2,915% — лишь доля downstream candidate pairs.

**Сильные иллюстрации:**

- Одинаковый title `Inflation surge in 2026?` у шести порогов 4.5/5/5.5/6/6.5/7%. ≥7 ⇒ ≥6.5, не equivalence. Это внутри известного event, т.е. positive control.
- Core CPI YoY >2.6% декабрь против ноября: rules similarity 0.973437, взаимный top1; разные периоды, импликация из текстов не следует.
- Октябрьский CPI >0.9 ⇒ >0.8: отсутствует в top5 всех вариантов, rules ranks 7/8. Пропуск даже простой threshold implication.
- CPI и core CPI >0.2% ноябрь: title similarity .860176 против rules .544710; разные underlyings.
- Декабрьский CPI YoY >5 ⇒ любой месяц года CPI YoY ≥5 — только условная гипотеза при совпадении source/revision semantics. В metadata обоих series BLS, полные PDF terms не прочитаны. Retrieval rules ranks 283/59, ни один вариант top5 не извлёк.

Все пары и их полные evidence packets: `pilot/results/review_cases.json`. Интерпретации AI-assisted exploratory, без второго аннотатора; нельзя называть gold или рассчитывать на них обобщаемые метрики.

**Доступ:** Kalshi official external-api работает, 8 market requests + 2 series metadata. Gamma local resets (и пробные alternate gamma-cache/events также reset); единственная попытка основного коллектора с exact URL, временем и ошибкой в manifest/raw. Нет полученных Polymarket contracts. Коллектор для Gamma реализован, но ветка на реальных данных не проверена.

**Запуск:** `python3 pilot/pilot.py analyze --top-k 5`, затем `python3 pilot/review_cases.py`. Интерпретатор `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3`, sklearn1.3/numpy1.25.1, nbformat5.9.2. pinned requirements. Hash-checks исходных raw, markets.json и normalized model-input fields выполняются при analyze.

**Точность формулировок:** не называйте экономически связанные показатели независимыми при отсутствии логической связи; empirical correlation не измерялась. Не выдавайте API rules snapshot за все юридические условия. Не называйте сохранившиеся event threshold связи неизвестными discoveries. Более низкая cross-event доля при rules-retrieval не означает лучшее качество: требуется gold.
