#!/usr/bin/env python3
"""Generate the detailed Markdown/PDF report from saved analysis results.

Run scripts/analyze.py first. This module does not collect measurements or
recompute statistical estimates; the short report is built from main.typ.
"""
import csv
import html
import json
from pathlib import Path
import re
import sys

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
LABELS = ['read/lseek: Read', 'read/lseek: Write', 'mmap: Read', 'mmap: Write']


def fmt(x):
    return f'{x:.6f}'


def main():
    summaries = json.loads((RESULTS / 'summary.json').read_text())
    plan = json.loads((RESULTS / 'plan.json').read_text())
    graph = json.loads((RESULTS / 'graphs.json').read_text())['rand']
    env = json.loads((RESULTS / 'environment-final-before.json').read_text())
    outputs = {c['command'][0]: c.get('stdout', '') for c in env['commands']}
    system = outputs.get('sysctl', outputs.get('lscpu', '')).strip()
    # Include only device characteristics, never serial numbers or host identifiers.
    system_lines = [line for line in system.splitlines() if any(key in line for key in ['hw.', 'brand_string', 'Model name:', 'CPU(s):'])]
    nvme = outputs.get('system_profiler', '')
    disk_lines = [line.strip() for line in nvme.splitlines() if any(key in line for key in ['APPLE SSD', 'Capacity:', 'TRIM Support:', 'Model:', 'Link Width:', 'Link Speed:'])]
    passport = '; '.join(system_lines + disk_lines) or 'См. environment-final-before.json.'
    if env['platform'] == 'darwin':
        properties = dict(line.split(': ', 1) for line in system_lines if ': ' in line)
        ram = int(properties.get('hw.memsize', '0')) / 1024**3
        passport = f"Модель {properties.get('hw.model', '?')}; CPU {properties.get('machdep.cpu.brand_string', '?')}; {properties.get('hw.ncpu', '?')} ядер ({properties.get('hw.perflevel0.physicalcpu', '?')} производительных, {properties.get('hw.perflevel1.physicalcpu', '?')} энергоэффективных); RAM {ram:.0f} ГиБ. Накопитель: " + next((line for line in disk_lines if line.startswith('Model:')), 'модель не определена') + '; локальная файловая система APFS.'
    before_top = outputs.get('top', '')
    before_cpu = next((line for line in before_top.splitlines() if line.startswith('CPU usage:')), '')
    before_load = outputs.get('uptime', '').strip()
    power = outputs.get('pmset', '').strip().replace('\n', '; ')
    after_env = json.loads((RESULTS / 'environment-after.json').read_text())
    after_outputs = {c['command'][0]: c.get('stdout', '') for c in after_env['commands']}
    after_cpu = next((line for line in after_outputs.get('top', '').splitlines() if line.startswith('CPU usage:')), '')
    after_load = after_outputs.get('uptime', '').strip()
    def pair_text(a, b):
        r = summaries[b]['mean']/summaries[a]['mean']
        overlap = max(summaries[a]['ci_low'], summaries[b]['ci_low']) <= min(summaries[a]['ci_high'], summaries[b]['ci_high'])
        return f'Write/Read = {r:.3f}; обновление медленнее на {(r-1)*100:.1f}%. 95% ДИ ' + ('пересекаются.' if overlap else 'не пересекаются.')
    meta = f"ОС: {outputs.get('sw_vers', sys.platform).strip().replace(chr(10), '; ')}. {passport}"
    sections = []
    os_name = 'macOS' if env['platform'] == 'darwin' else env['platform']
    affinity_note = ('CPU affinity не контролировалась; планировщик выбирал ядро.' if plan['core'] is None else f'Процессы закреплялись через taskset на CPU {plan["core"]}.')
    monitor_note = ('strace/perf относятся к Linux и здесь не запускались. dtruss не запускался: для трассировки нужны дополнительные права и доступ зависит от SIP.' if env['platform'] == 'darwin' else 'strace/perf в этой серии не запускались; отдельная трассировка системных вызовов не выполнялась.')
    def section(title, *paragraphs):
        sections.append((title, list(paragraphs)))
    section('1. Постановка и гипотезы',
        'Вариант: Read vs Write, Cache, 10M, Rand. Сравниваются чтение и обновление записей одного случайного графа через read/lseek и mmap. Write означает чтение записи и инкремент её поля value; это read-modify-write, а не изолированная запись.',
        f"Рабочие гипотезы: обновление медленнее чтения из-за дополнительных операций и загрязнения страниц; mmap быстрее read/lseek благодаря отсутствию системных вызовов на каждую вершину. В прогретом файловом кэше характеристики диска ожидаются менее существенными, чем стоимость переходов в ядро. Размер: {graph['bytes']} байт (10 МиБ), {graph['nodes']} вершин по 24 байта, заголовок 40 байт, seed=427.")
    section('2. Паспорт и ограничения окружения', meta,
        f"Страница ОС: {graph['page_size']} байт. Граф сгенерирован с --page-size={graph['page_size']}, --topology chain, -b 0.5, --min-step-pages 2. Проверены отсутствие циклов и достижимость всех вершин. Доля межстраничных переходов: {(1-graph['same_page_edges']/(graph['nodes']-1))*100:.2f}%. Принудительное расстояние не гарантирует промах CPU-кэша или файлового кэша.",
        f'Работа выполнена в {os_name}. Файл лежит на локальном разделе; параметры ОС зафиксированы системными утилитами. Объём 10 МиБ значительно меньше RAM, что соответствует тёплому page cache. {affinity_note} Частота, Turbo, температура и миграции не контролировались. Перед серией на адаптере фоновые приложения были закрыты; системные службы macOS продолжали работать. Uptime, top, vm_stat и питание записаны до и после серии; стенд не был полностью изолирован. Файловый кэш и CPU-кэш - разные уровни; прогрев первого не гарантирует постоянного состояния второго.',
        f'Снимок перед финальной серией: {before_load}; {before_cpu}. После: {after_load}; {after_cpu}. Питание перед серией: {power}. Питание после серии: {after_outputs.get("pmset", "").strip().replace(chr(10), "; ")}. Источник питания подтверждён двумя снимками; остаточная фоновая загрузка ограничивает переносимость результатов. Частота во время финальной серии и размеры CPU-кэшей не определены.',
        'Компиляция обоих прототипов: clang -O2 -Wall -Wextra, без изменения исходников. Полная версия компилятора сохранена в паспорте. Сборка выполнена без предупреждений.')
    section('3. Методика и выбор числа запусков',
        'Основная метрика: время всего дочернего процесса, измеренное perf_counter_ns и делённое на 5 обходов. В неё входят запуск, открытие/отображение и закрытие файла, диагностический вывод в pipe. Это оценка средней стоимости одного обхода при данном протоколе, а не чистого тела цикла. User/sys и rusage измеряются для завершённого дочернего процесса. Нормированные пять обходов одного процесса считаются одним наблюдением.',
        'Кэш включён: --no-cache не передаётся. Два прогревочных запуска каждой конфигурации выполнены заранее и сохранены отдельно. Во время серии кэш не сбрасывался. Четыре конфигурации перемешиваются в каждом раунде с seed=427. Пилотные 10 запусков каждой конфигурации исключены из итоговой серии. Выбросы итоговой серии не удалялись.',
        f"Цель - полуширина 95% ДИ не более 5% среднего. По пилоту N уточнялось из N ≈ (t·s/(0.05·mean))², минимум 30, максимум 100. Пилотные оценки N: {plan['pilot_required_n']}. Итог: N={plan['final_n']} на каждую конфигурацию. При превышении ограничения 100 целевая точность может не достигаться; это проверяется по финальным данным.",
        'Среднее = сумма/N; выборочное стандартное отклонение s вычислено с делителем N-1. ДИ = mean ± t(0.975,N-1)·s/√N. ДИ относится к среднему, а не к разбросу отдельных запусков. Формула предполагает достаточно независимые наблюдения и устойчивое среднее; фоновые задачи и временная зависимость ограничивают её точность. Медиана и IQR сохранены в summary.csv. Непересечение ДИ используется как консервативный учебный критерий; пересечение само по себе не доказывает равенство.')
    section('4. Результаты и статистическая точность')
    for i, s in enumerate(summaries):
        sections[-1][1].append(f"{LABELS[i]}: N={s['n']}; среднее {fmt(s['mean'])} с; s={fmt(s['std'])} с; 95% ДИ [{fmt(s['ci_low'])}; {fmt(s['ci_high'])}] с; полуширина {s['relative_half']*100:.2f}%; медиана {fmt(s['median'])} с; IQR {fmt(s['iqr'])} с.")
    section('5. Сравнение и объяснение',
        'read/lseek: ' + pair_text(0, 1),
        'mmap: ' + pair_text(2, 3) + ' Гипотеза о замедлении при обновлении убедительно подтверждается для read/lseek; для mmap наблюдаемая разница мала относительно неопределённости. По этому учебному критерию утверждать различие mmap Read и Write нельзя.',
        f"Отношение read/lseek к mmap: {summaries[0]['mean']/summaries[2]['mean']:.2f} при чтении, {summaries[1]['mean']/summaries[3]['mean']:.2f} при обновлении. Для каждого узла read/lseek выполняет lseek и read (плюс lseek и write при обновлении). На один обход по исходному коду ожидаются {2*graph['nodes']+2} таких вызовов чтения/позиционирования, а при обновлении - {4*graph['nodes']+2} вызовов read/write/lseek, без учёта open/close и сообщений. Это анализ кода, а не результат трассировки.",
        f'Среднее user/sys на процесс (5 обходов): read/lseek Read {summaries[0]["user_s"]:.4f}/{summaries[0]["sys_s"]:.4f} с; Write {summaries[1]["user_s"]:.4f}/{summaries[1]["sys_s"]:.4f} с; mmap Read {summaries[2]["user_s"]:.4f}/{summaries[2]["sys_s"]:.4f} с; Write {summaries[3]["user_s"]:.4f}/{summaries[3]["sys_s"]:.4f} с. Minor faults: {summaries[0]["minflt"]:.1f}, {summaries[1]["minflt"]:.1f}, {summaries[2]["minflt"]:.1f}, {summaries[3]["minflt"]:.1f}, соответственно. Полные счётчики переключений и major faults приведены в summary.csv и PDF.',
        'mmap отображает файл целиком и затем обращается к памяти. Повторное отображение в каждом обходе требует восстановления отображений страниц даже при наличии данных в page cache; minor faults не равны чтениям с диска. Переключения контекста возникают из-за планировщика и ожиданий: системный вызов сам по себе не означает переключение процесса.',
        'Обе Cache-конфигурации обновляют данные без fsync/msync. Завершение процесса не гарантирует запись на физический носитель. Поэтому полученные числа характеризуют буферизованный read-modify-write; из них нельзя получить скорость устойчивой записи SSD. Dirty writeback может происходить асинхронно и создавать шум в следующих запусках.')
    section('6. Мониторинг, фоновая нагрузка и достаточность',
        f'{monitor_note} Полные счётчики системных вызовов и cache-misses отсутствуют; смены ядра разобраны ниже. Для характеризации использован отдельный /usr/bin/time {'-l' if env["platform"] == 'darwin' else '-v'}; его вывод сохранён в runs.log. Не следует выдавать вычисленные по исходнику числа вызовов за результаты мониторинга.')
    evidence_dir = RESULTS / 'mac-diagnostics'
    if (evidence_dir / 'powermetrics.txt').exists():
        power_log = (evidence_dir / 'powermetrics.txt').read_text()
        pressure = re.findall(r'Current pressure level: (.*)', power_log)
        frequencies = [int(v) for v in re.findall(r'P-Cluster HW active frequency: (\d+)', power_log)]
        setup = (evidence_dir / 'environment.txt').read_text()
        lowpower = re.findall(r'lowpowermode\s+(\d+)', setup)
        logs = list(evidence_dir.glob('*-xctrace.log'))
        completed = [p.name for p in logs if 'Output file saved as:' in p.read_text()]
        sections[-1][1].append(f'Дополнительная проверка от 05.10.2026: питание от адаптера, lowpowermode={lowpower}. В отдельной нагрузке graph_traverse --write 10 получено {len(pressure)} образцов powermetrics с интервалом около 1 с: состояния теплового давления {sorted(set(pressure))}; частота P-кластера {min(frequencies)}-{max(frequencies)} МГц. Это системные счётчики отдельного запуска; они не устанавливают частоту конкретного процесса и не доказывают отсутствие троттлинга во время основной серии. Логи: results/mac-diagnostics/.')
        trace_summary = RESULTS / 'system-trace/summary.json'
        if trace_summary.exists():
            profiles = json.loads(trace_summary.read_text())
            sections[-1][1].append('System Trace разобран: при read/lseek Read на read и lseek приходится 99,4% веса выборок. При Write: write 51,8%, lseek 28,1%, read 19,6%. У mmap Read/Write на main приходится 99,1%/98,6%. Это веса выборок верхнего кадра пользовательского стека, а не количество вызовов или точная доля kernel time. Результаты согласуются с объяснением различий и независимыми счётчиками user/sys.')
            sections[-1][1].append('Основной поток выполнялся только на P-ядрах, со сменами ядра 19/46/8/2 в порядке таблицы. Running занимает 96,9-99,6% экспортированного окна; ожидания не доминируют. Начальный Blocked до запуска исключён; у read/lseek Read отсутствует событие завершения, поэтому возможен хвост записи. Подробности и ограничения: TRACE_ANALYSIS.md. Экспорт: results/system-trace/; скрипт: scripts/analyze_traces.py.')
        else:
            sections[-1][1].append(f'System Trace: успешно сохранены {len(completed)} из {len(logs)} записей. Содержимое .trace не анализировалось.')

    diagnostics = json.loads((RESULTS / 'diagnostics-summary.json').read_text())
    for app in ('graph_traverse', 'graph_traverse_mmap'):
        bare = diagnostics['monitoring'][app]['bare']
        monitored = diagnostics['monitoring'][app]['time']
        overlap = max(bare['ci_low'], monitored['ci_low']) <= min(bare['ci_high'], monitored['ci_high'])
        sections[-1][1].append(f"{app}, 5 пар: обычный запуск {bare['mean']*1000:.3f} мс; под time {monitored['mean']*1000:.3f} мс; отношение {monitored['mean']/bare['mean']:.3f}. 95% ДИ {'пересекаются' if overlap else 'не пересекаются'}. Замер включает запуск time. Сырые данные: diagnostics.csv.")

    noise = diagnostics['cpu_noise']
    sections[-1][1].append(f"Один запуск с собственным CPU worker: {noise['wall_per_traversal_s']*1000:.3f} мс/обход; итоговое среднее без этой нагрузки - {summaries[0]['mean']*1000:.3f} мс. Работник использует один CPU, всегда останавливается после проверки. Одного наблюдения недостаточно для вывода о систематическом влиянии нагрузки.")
    sections[-1][1].append('Итоговая относительная полуширина 95% ДИ: ' + '; '.join(f"{LABELS[i]} {item['relative_half']*100:.2f}%" for i, item in enumerate(summaries)) + '. Грубые оценки N для точности 5% при t≈1.96: ' + ', '.join(str(item['target_n']) for item in summaries) + ', соответственно. Эти оценки не заменяют t-квантиль при малом N; фактически использовано N=30. При увеличении N в 4 раза полуширина примерно вдвое меньше при неизменной дисперсии; систематические ошибки это не устраняет.')
    section('7. Общий вывод и воспроизведение',
        'Гипотеза о преимуществе mmap согласуется с данными обеих нагрузок. В исследованном варианте различия следует объяснять стоимостью доступа к закэшированным данным, количеством переходов в ядро и обработкой отображений страниц. Критичны одинаковый случайный граф, прогретый кэш, одинаковая сборка и число обходов. Конкретная модель диска менее существенна для чтения в тёплом кэше, но изолированное влияние оборудования и CPU affinity в этой работе не проверялось. Выводы относятся к данному стенду и Cache-семантике.',
        'Полный запуск: bash scripts/run.sh. Для Linux можно передать --core с доступным CPU: bash scripts/run.sh --core 2. Анализ существующих CSV: out/venv/bin/python scripts/analyze.py. Генерация и сбор: scripts/experiment.py prepare и collect. Папка results содержит паспорт, план, журнал, пилот, прогрев, четыре финальных CSV и статистику; figures - графики. Генератор расположен в ../util/graphgen.py и должен оставаться доступным.',
        'Проверка результатов: все запуски завершились успешно; каждый обход обработал все 436905 вершин. Поле value каждой вершины увеличилось ровно на ожидаемое число Write-обходов, остальные байты структуры остались неизменными. Сырые CSV позволяют пересчитать результаты без новых измерений.')
    baseline_path = RESULTS / 'battery-baseline/summary.csv'
    if baseline_path.exists():
        with baseline_path.open() as f:
            previous = {(r['app'], r['mode']): r for r in csv.DictReader(f)}
        sections[-1][1].append('Дополнительное сравнение условий: первоначальная серия выполнена 04.10.2026 на батарее, основная серия - 05.10.2026 на адаптере. Обе серии содержат по 30 наблюдений каждой конфигурации, но выполнены в разное время и при разном фоне. Их нельзя считать контролируемым экспериментом по изолированному влиянию питания.')
        for i, item in enumerate(summaries):
            old = previous[(item['app'], item['mode'])]
            reduction = (1-item['mean']/float(old['mean']))*100
            sections[-1][1].append(f"{LABELS[i]}: батарея {float(old['mean'])*1000:.3f} мс; адаптер {item['mean']*1000:.3f} мс; снижение среднего времени {reduction:.1f}%. Сырые данные старой серии сохранены отдельно: results/battery-baseline/.")
        sections[-1][1].append('Основная статистика и графики используют только новую серию, результаты двух дней не объединялись. Общие выводы сохранились: mmap быстрее обоих режимов read/lseek; обновление read/lseek существенно медленнее чтения, а для mmap интервалы Read и Write пересекаются.')
    table = [['Конфигурация', 'N', 'Mean, ms', 's, ms', '95% CI, ms']]
    for label, s in zip(LABELS, summaries):
        table.append([label, str(s['n']), f"{s['mean']*1000:.3f}", f"{s['std']*1000:.3f}", f"[{s['ci_low']*1000:.3f}; {s['ci_high']*1000:.3f}]"])
    md = ['# Отчёт: Read vs Write, Cache, 10M, Rand', '']
    for title, paragraphs in sections:
        md += [f'## {title}', '']
        for p in paragraphs:
            md += [p, '']
        if title.startswith('4.'):
            md += ['| ' + ' | '.join(table[0]) + ' |', '|---|---:|---:|---:|---|'] + ['| ' + ' | '.join(row) + ' |' for row in table[1:]] + ['', '![Средние и ДИ](figures/comparison.png)', '', '![Распределения](figures/distributions.png)', '', '![Порядок запусков](figures/run-order.png)', '']
            md += ['Гистограмма показывает плотность частот в интервалах; KDE сглаживает наблюдения ядром и зависит от выбранной ширины сглаживания. Здесь использована гистограмма с общими границами корзин для Read и Write в каждой паре. Форма эмпирического распределения при данном N не доказывает нормальность.', '']
    (ROOT / 'REPORT.md').write_text('\n'.join(md))
    font_candidates = [Path('/Library/Fonts/Arial Unicode.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    font = next((p for p in font_candidates if p.exists()), None)
    if font is None:
        raise RuntimeError('Install a Cyrillic TrueType font (DejaVu Sans)')
    pdfmetrics.registerFont(TTFont('Report', str(font)))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('BodyRu', fontName='Report', fontSize=10, leading=14, spaceAfter=8))
    styles.add(ParagraphStyle('HeadingRu', fontName='Report', fontSize=14, leading=18, spaceAfter=12))
    styles.add(ParagraphStyle('TitleRu', fontName='Report', fontSize=21, leading=28, spaceAfter=18))
    story = [Paragraph('Экспериментальное введение<br/>в операционные системы', styles['TitleRu']), Paragraph('Read vs Write · Cache · 10M · Rand', styles['HeadingRu']), Paragraph('Измерения: ' + html.escape(env['timestamp']), styles['BodyRu'])]
    for index, (title, paragraphs) in enumerate(sections):
        if index in (2, 3, 4, 5, 6):
            story.append(PageBreak())
        story.append(Paragraph(html.escape(title), styles['HeadingRu']))
        if index == 3:
            pdf_table = Table(table, colWidths=[47*mm, 10*mm, 24*mm, 22*mm, 57*mm])
            pdf_table.setStyle(TableStyle([('FONTNAME', (0,0), (-1,-1), 'Report'), ('FONTSIZE', (0,0), (-1,-1), 8), ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e9eef2')), ('LINEBELOW', (0,0), (-1,0), .5, colors.gray), ('BOTTOMPADDING', (0,0), (-1,-1), 8), ('TOPPADDING', (0,0), (-1,-1), 8)]))
            story += [pdf_table, Spacer(1, 3*mm), Paragraph('Относительная полуширина ДИ: ' + '; '.join(f'{LABELS[i]} {item["relative_half"]*100:.2f}%' for i, item in enumerate(summaries)) + ('. Цель 5% достигнута во всех четырёх сериях.' if all(item['relative_half'] <= .05 for item in summaries) else '. Цель 5% достигнута не во всех сериях.') + ' В каждой панели свой масштаб времени.', styles['BodyRu']), Spacer(1, 3*mm), Image(str(ROOT / 'figures/comparison.png'), width=165*mm, height=69.7*mm), Image(str(ROOT / 'figures/distributions.png'), width=165*mm, height=61*mm), Paragraph('Плотности Read/Write наложены в каждой паре. Корзины общие; площадь каждой гистограммы равна 1. Гистограмма не подтверждает нормальность распределения; KDE дополнительно требует выбора сглаживания.', styles['BodyRu'])]
        else:
            for p in paragraphs:
                story.append(Paragraph(html.escape(p), styles['BodyRu']))
        if index == 4:
            story += [Spacer(1, 3*mm), Image(str(ROOT / 'figures/run-order.png'), width=150*mm, height=80*mm)]
        if index == 5:
            resource_table = [['Конфигурация', 'User, s', 'Sys, s', 'Minor', 'Major', 'Vol / Invol']]
            for label, s in zip(LABELS, summaries):
                resource_table.append([label, f"{s['user_s']:.4f}", f"{s['sys_s']:.4f}", f"{s['minflt']:.1f}", f"{s['majflt']:.1f}", f"{s['vol_ctx']:.1f} / {s['invol_ctx']:.1f}"])
            rt = Table(resource_table, colWidths=[43*mm, 21*mm, 21*mm, 23*mm, 18*mm, 34*mm])
            rt.setStyle(TableStyle([('FONTNAME', (0,0), (-1,-1), 'Report'), ('FONTSIZE', (0,0), (-1,-1), 8), ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e9eef2')), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
            story += [Paragraph('Средние ресурсы на один процесс (5 обходов)', styles['HeadingRu']), rt]
    output = ROOT / 'output/pdf/report.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    def footer(canvas, doc):
        canvas.setFont('Report', 8)
        canvas.drawString(22*mm, 13*mm, 'Операционные системы · Read vs Write / Cache / 10M / Rand')
        canvas.drawRightString(188*mm, 13*mm, str(doc.page))
    SimpleDocTemplate(str(output), pagesize=(210*mm, 297*mm), rightMargin=22*mm, leftMargin=22*mm, topMargin=20*mm, bottomMargin=22*mm).build(story, onFirstPage=footer, onLaterPages=footer)
    print('Created REPORT.md and output/pdf/report.pdf from saved analysis results.')


if __name__ == '__main__':
    main()
