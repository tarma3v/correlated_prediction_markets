/* Rebuild with Node.js and pptxgenjs 4. Run from any directory. */
const fs = require('node:fs')
const path = require('node:path')
const { createHash } = require('node:crypto')
const PptxGenJS = require('pptxgenjs')
const repo = path.resolve(__dirname, '../../..')
const output = process.argv[2] ? path.resolve(process.argv[2]) : __dirname
const expr = 'experiments/'
const sources = {}
function read(relative) {
  const bytes = fs.readFileSync(path.join(repo, relative))
  sources[relative] = createHash('sha256').update(bytes).digest('hex')
  return bytes.toString('utf8')
}
function json(relative) { return JSON.parse(read(expr + relative)) }
const confidence = json('confidence_audit/results.json').thresholds
const sem = json('semantic_audit/results.json')
const market = json('market_audit/summary.json')
const kota = json('oracle_audit/results/kota.json')
const cpi = json('oracle_audit/results/cpi.json')
const ev = json('oracle_audit/results/evidence.json')
const jev = json('oracle_audit/results/jev.json')
const textBaseline = json('oracle_audit/results/text_baseline.json')
const llm = sem.llm.metrics
const mu = sem.text_mutations.transfer
const e5 = sem.author_retrieval.e5_small_v2.known_same
const rankings = sem.cpi.retrieval
const graph = sem.graph
const sr = market.settlements
const norm = market.cross_venue.ordinary_release
const nested = market.nesting.sep_economics
const [header, ...entries] = read(expr + 'lead_lag/results/forecast_metrics.csv').trim().split(/\r?\n/)
const columns = header.split(',')
const lead = entries.map(line => Object.fromEntries(line.split(',').map((value, i) =>
  [columns[i], i < 3 ? value : Number(value)]))).filter(row => row.sample === 'all')
const ids = ['KXLCPIMAXYOY-27-P5.5', 'KXLCPIMAXYOY-27-P4.5']
const cards = JSON.parse(read('pilot/markets.json'))
const decisions = read(expr + 'confidence_audit/decisions.csv')
if (!ids.every(id => cards.some(c=>c.id===id))) throw Error('Missing source market')
if (!decisions.split('\n').some(line => ids.every(id => line.includes(id)) && line.startsWith('0.99,') && line.includes('exclusion_candidate'))) throw Error('The ≥ threshold witness no longer matches decisions.csv')
const pct = (v, n=1) => (v * 100).toFixed(n).replace('.', ',') + '%'
const num = (v, n=2) => Number(v).toFixed(n).replace('.', ',').replace('-', '−')
const pp = (v, n=1) => num(100 * v, n)
const frac = (a,b) => a + '/' + b

const pptx = new PptxGenJS()
pptx.layout = 'LAYOUT_WIDE'
pptx.author = 'Исследовательский проект ИТМО'
pptx.title = 'Проверяемые связи выплат на рынках предсказаний'
pptx.subject = 'Материалы к обсуждению ВКР, 17 ноября 2026 года'
pptx.lang = 'ru-RU'
pptx.theme = {headFontFace:'Arial', bodyFontFace:'Arial', lang:'ru-RU'}
const W=13.33333, H=7.5, L=.64, R=12.69, A=R-L
const BG='F7F6F1', INK='152C36', TEAL='006B65', MUTE='455B60', LINE='BFCBC5'
const LIGHT='D9E9E3', RED='9C3826', BLUSH='F3E3D9', WHITE='FFFFFF', PALE='C1E2D7'
let sl, number=0
function text(x,y,w,h,value,size,options={}) {
  sl.addText(String(value), {x,y,w,h,fontFace:'Arial',fontSize:size,bold:false,color:INK,margin:0,
    breakLine:false,valign:'mid',align:'left',paraSpaceAfter:0,paraSpaceBefore:0,
    ...options})
}
function box(x,y,w,h,fill) {
  sl.addShape(pptx.ShapeType.rect,{x,y,w,h,line:{color:fill,transparency:100},fill:{color:fill},radius:0})
}
function line(x,y,w,color=LINE) {
  sl.addShape(pptx.ShapeType.line,{x,y,w,h:0,line:{color,width:0.9},beginArrowType:undefined})
}
function begin(tag,title,sub) {
  sl=pptx.addSlide();number++;sl.background={color:BG}
  text(L,.31,10.75,.28,tag.toUpperCase(),13,{color:TEAL,bold:true})
  text(11.49,.31,1.2,.28,'ИТМО   /   '+String(number).padStart(2,'0'),12,{align:'right',color:MUTE})
  text(L,.89,A,.61,title,31,{bold:true})
  if(sub) text(L,1.65,A,.50,sub,17,{color:MUTE})
}
function finish(footer,notes,url) {
  line(L,6.85,A)
  text(L,6.95,A,.30,footer,11.1,{color:MUTE,...(url?{hyperlink:{url}}:{})})
  sl.addNotes(notes)
}
function table(x,y,widths,headers,rows,opts={}) {
  const headerH=opts.headerH||.50, rowH=opts.rowH||.62
  const ranges=[0]
  for(const w of widths) ranges.push(ranges[ranges.length-1]+w)
  const tw=ranges[ranges.length-1]
  const rowObjects = [headers,...rows].map((cells,i)=>cells.map((value,j)=>({
    text:String(value),options:{
      color:i===0?WHITE:(j===0?INK:(opts.numericColor||TEAL)),
      bold:(i===0||j>0),align:j===0?'left':'center',valign:'middle',
      fill:{color:i===0?INK:(i%2===0?'E8EEEA':BG)},
      fontSize:i===0?(opts.headSize||15):(opts.size||18),
      margin:[0.045,0.12,0.045,0.12],
      border:{type:'solid',pt:.4,color:i===0?INK:LINE}
    }
  })))
  sl.addTable(rowObjects,{x,y,w:tw,h:headerH+rowH*rows.length,colW:widths,
    rowH:[headerH,...rows.map(()=>rowH)],autoPage:false,fontFace:'Arial',margin:0,
    lineSpacingMultiple:1})
}
function statement(y,value,size=18,color=TEAL) {
  box(L,y,.065,.52,color);text(L+.20,y-.03,A-.20,.59,value,size,{bold:true,color})
}
function addBars({x,y,w,h,labels,values,max=100,step=25,colors=[TEAL],format='0',axisTitle}) {
  sl.addChart(pptx.ChartType.bar,[{name:axisTitle,labels,values}],{
    x,y,w,h,barDir:'bar',barGrouping:'clustered',catAxisLabelFontFace:'Arial',
    catAxisLabelFontSize:16,catAxisLabelColor:INK,catAxisLabelPos:'low',catAxisOrientation:'maxMin',
    valAxisMinVal:0,valAxisMaxVal:max,valAxisMajorUnit:step,valAxisLabelFontSize:13,valAxisLabelColor:MUTE,
    valAxisLineShow:false,catAxisLineShow:false,showLegend:false,showTitle:false,showValue:true,
    dataLabelPosition:'inEnd',dataLabelFormatCode:format,dataLabelColor:WHITE,dataLabelFormat:'number',
    dataLabelFormatSymbol:'',dataLabelFontFace:'Arial',dataLabelFontSize:17,
    gapSizePct:70,catAxisMajorTickMark:'none',valAxisMajorTickMark:'none',
    valGridLine:{color:LINE,size:.6},catAxisLineColor:LINE,chartColors:colors,
    chartArea:{fill:{color:BG},border:{color:BG,width:0}},
    plotArea:{fill:{color:BG},border:{color:BG,width:0}},showCatName:false,
    showBorder:false
  })
}

// The four payout states are also the running example for the meeting.
sl=pptx.addSlide();number++;sl.background={color:INK}
text(L,.38,11,.30,'ИТМО   /   МАТЕРИАЛЫ К ОБСУЖДЕНИЮ ВКР',14,{color:PALE,bold:true})
text(L,1.25,A,1.66,'Проверяемые связи выплат\nна рынках предсказаний',42,{bold:true,color:WHITE})
text(L,3.20,A,.70,'Какие совместные исходы допускают правила двух контрактов?',23,{color:WHITE})
line(L,4.50,A,'618078')
text(L,4.73,A,.36,'Совместные выплаты A и B при бинарном расчёте',16,{color:PALE})
for(const [i,state] of ['нет / нет','нет / да','да / нет','да / да'].entries())
  text(L+i*3.02,5.35,2.85,.59,state,26,{color:WHITE,bold:true})
text(L,6.92,A,.30,'Kalshi и Polymarket, 17 ноября 2026 года',13,{color:PALE})
sl.addNotes('00:00–00:25. Наша единица анализа: версии правил двух контрактов и выбранная ветвь расчёта. Мы пытаемся обосновать запрет и найти контрпример к каждому выводу модели. Если договор допускает небинарную выплату, эту ветвь нужно анализировать отдельно.')

begin('Ближайшая работа','Логические связи в работе Shi и Zhai',
  'Shi и Zhai (2026) восстанавливают логические связи и ищут арбитраж на Polymarket.')
text(L,2.44,5.55,.45,'102 288 из 239 653',28,{bold:true,color:TEAL})
text(L,3.01,5.68,1.38,'Столько парных предложений подтвердили обе модели-аудиторы. Это измеряет согласие проверяющих.',19)
line(6.55,2.37,5.9)
text(6.55,2.59,5.85,.50,'Вопрос ВКР',24,{bold:true})
text(6.55,3.28,5.91,1.72,'Как часто модель запрещает возможную выплату? Как меняется ответ, если площадки используют разные выпуски показателя?',19)
statement(5.61,'Единица проверки: конкретная пара версий правил и предпосылки расчёта.',18)
finish('Shi и Zhai, Combinatorial Arbitrage in Prediction Markets, версия 4, § 4.2, таблица 3.',
'00:25–00:55. Работа уже включает поиск числовых зависимостей, проверку направления и контрпримеров. Доля двух согласных аудиторов 42,7%. Для оценки внешней валидности ВКР нужны независимые решения по допустимости совместных выплат и изучение отказов. https://arxiv.org/html/2610.23517v4','https://arxiv.org/html/2610.23517v4')

begin('Проверяемый пример / Kalshi','При инфляции 6,5% оба контракта платят «да»',
  'x обозначает наибольшую годовую инфляцию по индексу потребительских цен (CPI) среди месяцев 2026 года.')
const x0=4.55, step=1.23
for(const [i,[label,threshold]] of [['A: x ≥ 5,5%',5.5],['B: x ≥ 4,5%',4.5]].entries()){
  const y=3.23+i*.82
  text(L,y-.24,3.5,.52,label,24,{bold:true})
  box(x0,y,5*step,.043,LINE);box(x0+(threshold-3)*step,y-.045,(8-threshold)*step,.135,TEAL)
}
const px=x0+(6.5-3)*step;box(px,2.89,.035,1.47,RED)
text(px-.72,2.35,1.44,.4,'x = 6,5%',18,{color:RED,bold:true,align:'center'})
for(let val=3;val<=8;val++) text(x0+(val-3)*step-.28,4.57,.56,.35,val+'%',14,{align:'center',color:MUTE})
statement(5.50,'При пороге уверенности 0,99 модель запретила совместное «да». Значение 6,5% даёт контрпример.',17,RED)
finish('Архив Kalshi: KXLCPIMAXYOY-27-P5.5 и KXLCPIMAXYOY-27-P4.5. Условный пример при бинарном расчёте.',
'00:55–01:25. На этих двух рынках достаточно превышения порога хотя бы в одном месяце. Интервалы простираются вправо за пределы графика. При одинаковой версии показателя и равных прочих условиях x=6,5% удовлетворяет обоим порогам. Это возможное значение, фактический CPI для опровержения запрета не требуется. Исходные условия: pilot/markets.json. Прогноз: experiments/confidence_audit/decisions.csv.')

const c80=confidence.find(r=>r.cutoff===.8)
begin('Архив правил / условная числовая проверка','У 500 из 555 ответов есть числовой контрпример',
  '839 пар Kalshi, 19 групп пороговых шаблонов, 8 серий. Для каждой пары принят общий числовой показатель.')
table(L,2.33,[2.29,3.05,3.12,3.59],['Порог NLI','Ответов из 839','Ответов с\nконтрпримером','Риск среди ответов'],
confidence.filter(r=>[.50,.80,.90,.99].includes(r.cutoff)).map(r=>[num(r.cutoff),String(r.calls),String(r.errors),pct(r.risk)]),{headSize:15,rowH:.52,headerH:.68,size:18})
statement(5.52,'При пороге 0,80 охват составил '+pct(c80.coverage)+'. При пороге 0,99 остались 17 ответов, у всех есть контрпример.',17)
finish('DeBERTa-v3-base, оценки текстового следования (NLI). Расчёт по experiments/confidence_audit/results.json.',
'01:25–01:55. Один ошибочный ответ запрещает хотя бы одно достижимое состояние. При пороге 0,8 получены 325 ложных взаимоисключений, 148 ложных эквивалентностей и 27 импликаций неверного направления. Остальные 349 из 1188 исходных пар не вошли в условно проверяемую подгруппу. Эти доли описывают выбранные шаблоны, полные договоры площадок могут содержать исключения.')

begin('H1 / поиск межплощадочных связей','С контекстом известная пара чаще стоит первой',
  'E5-small-v2, 461 известное совпадение и 252 группы контрактов. Каждая группа имеет одинаковый вес.')
const k1=e5.k['1'], k20=e5.k['20']
addBars({x:L,y:2.17,w:9.05,h:2.08,labels:['Заголовок','Событие и заголовок'],
  values:[Number(pp(k1.title_macro).replace(',','.')),Number(pp(k1.event_macro).replace(',','.'))],max:100,step:25,
  format:'[$-0419]0.0"%"',axisTitle:'Известная пара на первом месте, %'})
text(10.05,2.40,2.58,.68,pct(k20.title_macro,0),30,{bold:true,color:TEAL})
text(10.05,3.10,2.62,.85,'Оба варианта находят пару в первых 20',16.2,{color:MUTE})
text(L,4.59,A,.52,'Прирост для первого места '+pp(k1.delta)+' п.п. (95%-й ДИ от '+pp(k1.ci95_family[0])+' до '+pp(k1.ci95_family[1])+' п.п.).',20,{bold:true,color:TEAL})
text(L,5.37,A,.75,'В одном блоке Core CPI при бюджете 5 кандидатов заголовок находит '+frac(rankings.title['5'].hits,sem.cpi.shared_pairs)+' связей, ключ показателя и месяца находит '+frac(rankings.structured['5'].hits,sem.cpi.shared_pairs)+'. При бюджете 20 оба находят все 77.',16.7)
finish('Два корпуса с разными эталонами. Интервал для известных совпадений получен бутстрэпом по группам.',
'01:55–02:35. В авторском корпусе с каждой стороны было по 493 кандидата. При основном заранее заданном бюджете 20 достигнут потолок. На отдельном блоке из 7 запросов и 55 кандидатных контрактов эталон рассчитан для общей публикации. В этом контрасте совместно изменялись представление и вес ключа. Полнота на новых тематических семействах остаётся неизвестной. Расчёт: experiments/semantic_audit/results.json.')

begin('H2 и H3 / контролируемые изменения','Формат ответа и проверка условий',
  'Контроли с заранее известными ответами позволяют отдельно измерить ошибки модели и проверяющего правила.')
text(L,2.30,5.75,.4,'H2. Формат ответа Qwen3-4B',19,{bold:true})
text(6.76,2.30,5.94,.40,'H3. Повреждённые условия',19,{bold:true})
line(L,2.93,5.60);line(6.76,2.93,5.93)
text(L,3.09,5.60,.62,'16 искусственных пар, 8 шаблонов.\nОхват размеченных состояний 75%.',16.4,{color:MUTE})
text(6.76,3.09,5.91,.62,'112 повреждений в 6 отложенных сериях.\nЧисло ошибочных допусков:',16.4,{color:MUTE})
for(const [i,[label,key]] of [['Прямой ответ','direct'],['Структурированный ответ','structured']].entries()){
  text(L,4.02+i*.55,4.23,.43,label,17)
  text(4.82,4.02+i*.55,1.45,.43,pct(llm[key]['0.75'].false_forbidden_risk),19,{bold:true,color:RED,align:'right'})
}
for(const [i,[label,key]] of [['Дословная цитата','literal'],['Предикат и выплата','predicate_and_payout'],['С учётом исключений','with_scope_guards']].entries()){
  text(6.76,4.02+i*.43,4.70,.38,label,16.8)
  text(11.45,4.02+i*.43,1.24,.38,frac(mu.methods[key].accepted_invalid,mu.methods[key].invalid),17.5,{bold:true,color:key==='with_scope_guards'?TEAL:RED,align:'right'})
}
text(L,5.26,5.49,.63,'Доля ложных запретов среди допустимых состояний, для которых дан ответ.',14.5,{color:MUTE})
text(6.76,5.58,5.90,.62,'Новую оговорку о выплате 0,5 словарная проверка пропустила.',15.7,{color:RED,bold:true})
finish('Контроли построены на разных задачах. Все три правила H3 приняли 28 из 28 действительных предъявлений.',
'02:35–03:15. При равном ожидаемом охвате состояний структурированный формат не уменьшил риск в этой выборке. Доли основаны на ожидаемых числах при равных рангах. H3 показывает эффект для предусмотренных видов порчи. За пределами списка новая оговорка о частичной выплате прошла проверку, хотя меняла исход. Эти результаты не заменяют теста на независимо размеченных полных правилах. Данные: experiments/semantic_audit/results.json, контрпример: experiments/semantic_audit/test_audit.py.')

begin('Полевые наблюдения / выплаты и котировки','Учёт правил устранил 12 расхождений в выплатах',
  'Core CPI, август, сентябрь и октябрь 2026 года. Семь категорий Polymarket для каждого выпуска.')
table(L,2.36,[8.19,3.86],['Как сопоставили Polymarket с Kalshi','Разные выплаты'],
[['По числу из названия категории',frac(sr.same_number_mismatch,sr.n)],['По условиям выплаты и набору порогов Kalshi',frac(sr.mapped_mismatch,sr.n)]],
{size:19,headSize:17,headerH:.52,rowH:.67})
text(L,4.47,A,.43,'Котировки ноябрьского Core CPI на 14 ноября',20,{bold:true})
text(L,5.04,A,1.02,'После сопоставления по правилам валовое расхождение положительно для '+frac(norm.quote_positive,norm.quote_eligible)+' доступных категорий. После расчётных комиссий осталось '+frac(norm.unrounded_net_cents.n_positive,norm.unrounded_net_cents.n)+'. Снимки площадок разновременные, глубина Polymarket неизвестна.',17.6)
finish('Два разных среза: исходы трёх выпусков и котировки одного открытого рынка. Источник: experiments/market_audit/.',
'03:15–03:50. На десятичной сетке категория «ровно 0,3%» соответствует разности индикаторов «выше 0,2%» и «выше 0,3%». Совпадение 21 выплаты относится к трём обычным публикациям. У ноябрьских контрактов сравнение использует котируемые стороны и модель комиссий без поордерного округления. На сентябрьском снимке Kalshi среди вложенных порогов 41/1027 инверсий середин котировок и 0/1030 положительных разностей bid высокого порога минус ask низкого. Исполнимость потребует синхронных стаканов и глубины обеих площадок.')

begin('Полевые наблюдения / дневные цены','Последняя цена дала меньшую ошибку прогноза',
  'Средняя абсолютная ошибка (MAE) дневной цены в процентных пунктах. Меньше означает точнее.')
table(L,2.30,[3.86,1.79,2.81,3.59],['Рынок и площадка','Строк','Последняя цена','Модель с ценой\nвторой площадки'],
lead.map(r=>[(r.cohort==='fomc'?'Ставка ФРС':'Выборы в Сенат')+', '+(r.target==='kalshi'?'Kalshi':'Polymarket'),r.rows,num(r.mae_persist,3),num(r.mae_cross_full,3)]),
{size:17.8,headSize:15.9,headerH:.70,rowH:.51})
text(L,5.65,A,.77,'Сравнение охватывает 3 исхода заседания ФРС и 4 гонки в Сенат США. Дневные данные позволяют проверить перенос прогноза между площадками. Для внутридневного опережения нужны временные метки сделок.',16.4)
finish('Каждый прогноз использует доступное к дате прошлое. Данные и интервалы: experiments/lead_lag/results/forecast_metrics.csv.',
'03:50–04:30. Оценка относится к следующим календарным суткам; пропуски не заполнялись. Среди четырёх основных комбинаций полный межплощадочный прогноз проиграл повтору последней цены. На рынках ФРС собственная двухфакторная модель дала больший MAE, чем полная модель, но интервалы для этой разницы включали ноль. У Сената с целью Polymarket усложнение увеличило MAE. Дни и пары зависимы. Положительный внутридневной lead-lag и торговую доходность эти четыре сравнения не устанавливают.')

begin('Решения к обсуждению','Какие данные нужны для следующей проверки',
  'Диагностика определила проверяемые ошибки. Теперь можно заранее зафиксировать критерии для нового материала.')
for(const [i,[head,body]] of [
  ['H1. Поиск кандидатов','Полностью разметить небольшие блоки из новых семейств, включая пары вне первых 20 результатов.'],
  ['H2 и H3. Проверка выплат','Два эксперта независимо размечают 30–50 пилотных пар по полным правилам. Скрыть ответы моделей, цены и итоговые выплаты.'],
  ['Экономическое расширение','Для теста исполнения собрать синхронные стаканы с глубиной. Для прогноза добавить новые события и заранее выбрать базовую модель.']
].entries()){
  let y=2.34+i*1.19;line(L,y,A);text(L,y+.16,3.62,.64,head,18.6,{bold:true,color:TEAL})
  text(4.54,y+.14,8.15,.80,body,17.0)
}
finish('На 17 ноября 2026 года независимая оценка полных договоров и фактически исполненные сделки отсутствуют.',
'04:30–05:15. Предлагаю выбрать новые семейства и двух разметчиков, согласовать обработку разногласий и зафиксировать основной показатель до просмотра теста. На следующую встречу можно принести долю разногласий и примеры новых оговорок. Для цен выбираем одно расширение по доступности данных. Методика подготовки научных слайдов: Kassis, Agarwal, He, Patel, Brueckner (2026), Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065')

begin('Приложение / зависимость от выпуска CPI','При независимых значениях снимаются 79 запретов',
  'Один блок ноябрьского Core CPI. Для 77 межплощадочных пар вычислены четыре совместные выплаты.')
const mut=sem.cpi.mutations
table(L,2.38,[8.03,4.02],['Что меняется относительно обычной модели','Пар с новым типом связи'],
[['Порог Kalshi становится нестрогим',frac(mut.inclusive.changed_pairs,sem.cpi.shared_pairs)],
 ['Непрерывная шкала вместо десятых',frac(mut.continuous.changed_pairs,sem.cpi.shared_pairs)],
 ['Площадки используют независимые значения выпусков',frac(mut.different_releases.changed_pairs,sem.cpi.shared_pairs)]],
{rowH:.61,headerH:.59,size:18,headSize:16})
text(L,5.27,A,1.03,'Правила Polymarket допускают предыдущий месяц после дедлайна. Kalshi предусматривает продление при приостановке работы федеральных органов. Независимые значения дают верхнюю границу чувствительности к выбору выпуска.',17.1)
finish('Контролируемый сценарий. Для каждого прежнего запрета сохранён условный числовой контрпример.',
'Приложение. В обычной модели десятичная шкала и единый индекс общие у площадок. Например, ≥0,7% и >0,6% совпадают на десятых, но при непрерывной шкале 0,65% их различает. Исходное число запретов 79; некоторые пары запрещают два состояния. Независимые публикации представляют допущение и не доказывают историческое нарушение. Данные: experiments/semantic_audit/cpi_pairs.jsonl и results.json.')

begin('Приложение / аудит решений оракула','Оракул дал 292 верных решения из 300 принятых',
  'Повторный анализ архива Kota. Порог выбран на 455 ранних строках, тест охватывает 668 более поздних строк.')
const kg=kota.heldout_gate, ci=kg.series_bootstrap_percentile_95
text(L,2.42,5.75,.70,pct(kg.accuracy,2),36,{bold:true,color:TEAL})
text(L,3.19,5.60,.70,'Точность при единогласии трёх агентов и средней уверенности от '+num(kota.training_confidence_median,4)+'.',18)
text(6.69,2.42,5.90,.70,pct(kg.coverage,2),36,{bold:true,color:TEAL})
text(6.69,3.19,5.95,.70,'Охват. Из '+kg.total+' решений фильтр принял '+kg.accepted+', в том числе '+kg.errors+' ошибочных.',18)
line(L,4.22,A)
text(L,4.55,A,.63,'95%-й интервал точности от '+pct(ci[0],2)+' до '+pct(ci[1],2)+' по 379 сериям. Без отказов голосование дало '+frac(kota.heldout.paper_confidence_vote.correct,kg.total)+' верных решений.',18)
text(L,5.49,A,.64,'Все '+ev.packets+' проверенных пакетов источников собраны после дня закрытия соответствующего контракта. Это ограничивает ретроспективную интерпретацию.',16.4,{color:MUTE})
finish('Kota (2026), архив ответов. Расчёты: experiments/oracle_audit/results/kota.json и evidence.json.','Приложение. Уровень уверенности 0,9167 получен на ранней части. Отсечка по закрытию 1 октября 2025 года. Из-за неоднозначности дат или пересечения границы исключены 33 серии. Модель текста без внешнего поиска дала '+frac(textBaseline.text_only.correct,textBaseline.test)+'. Доступность источников на исторический момент отдельно проверяет тест CPI. Основная публикация: https://arxiv.org/abs/2605.30802','https://arxiv.org/abs/2605.30802')

begin('Приложение / время публикации','До выпуска CPI правило отложило все 40 решений',
  'Историческое воспроизведение, 40 контрактов Kalshi, четыре серии-месяца и две даты публикаций BLS.')
table(L,2.36,[7.49,4.56],['Момент проверки','Результат'],
[['За секунду до публикации','Отказ: '+frac(cpi.release_before_deferred,cpi.n_rows)],
 ['При появлении официального значения','Решение: '+frac(cpi.release_at_decided,cpi.n_rows)],
 ['Сверка с опубликованными исходами','Совпали: '+frac(cpi.exchange_correct,cpi.exchange_checked)]],
{rowH:.61,headerH:.57,size:19,headSize:16.5})
text(L,5.37,A,.78,'В отдельном срезе 17 ноября все три открытых ноябрьских контракта получили отказ. На эту дату выпуск ожидался 10 декабря 2026 года.',17.8)
finish('BLS и опубликованные результаты Kalshi. Сверка на 12 контрактах включает 9 строк исходного снимка котировок.',
'Приложение. Решение формирует детерминированный обработчик в новом процессе. Замена будущего значения не меняет входной пакет. Ноябрьские прогнозы нельзя оценить до выпуска. Для отдельного модельного сравнения подготовлены 60 слепых запросов Jev, ответов на контрактах пока нет. В архиве другой задачи Jev получил 384/400, применять эту точность к контрактам оснований нет. Данные: experiments/oracle_audit/results/cpi.json и jev.json.')

const manifest={
  reference:{authors:'Hongjian Shi, Daojing Zhai',version:'v4, 2026-10-25',url:'https://arxiv.org/abs/2610.23517v4',
    proposed:239653,confirmed_by_both:102288},
  method_reference:'https://doi.org/10.48550/arXiv.2609.00065',
  witness:{markets:ids,shared_scalar:6.5,possible_state:'11',cutoff:.99},
  confidence:confidence.map(({cutoff,pairs,calls,errors,coverage,risk})=>({cutoff,pairs,calls,errors,coverage,risk})),
  retrieval:{author:e5,cpi:rankings},graph:{totals:graph.totals,macro_difference:graph.macro_graph_minus_confidence},
  llm_at_75pct:Object.fromEntries(Object.entries(llm).map(([name,byCoverage])=>[name,byCoverage['0.75']])),
  mutations:mu,cpi_sensitivity:sem.cpi.mutations,market:{settlements:sr,november:norm,nesting:nested},lead_lag:lead,
  oracle:{split:kota.split,gate:kg,confidence_median:kota.training_confidence_median,retrieved_after_close_day:ev.retrieved_after_close_day,
    cpi:{rows:cpi.n_rows,events:cpi.events,releases:cpi.release_dates,before_deferred:cpi.release_before_deferred,at_decided:cpi.release_at_decided,
      exchange_checked:cpi.exchange_checked,exchange_correct:cpi.exchange_correct,overlap:cpi.exchange_overlap_with_quotes},
    jev_first_repeat:jev.first_repeat},
  slide_count:number,source_sha256:sources
}
fs.mkdirSync(output,{recursive:true})
fs.writeFileSync(path.join(output,'slides-data.json'),JSON.stringify(manifest,null,2)+'\n')
pptx.writeFile({fileName:path.join(output,'slides.pptx'),compression:true}).catch(err=>{console.error(err);process.exitCode=1})
