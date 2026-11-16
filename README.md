# PerimeterGuard

Смартсистема відеоспостереження за периметром об'єкта з автоматичною
аналітикою подій. Я виконав цю роботу як Лабораторну роботу 1 з дисципліни
«Архітектури мультимедійних та смартсистем» (КПІ ім. Ігоря Сікорського,
ФПМ, кафедра ПЗКС). Обрана предметна область — варіант №2 із методичних
вказівок («Відеоспостереження за периметром з аналітикою подій») —
залишається наскрізною для лабораторних робіт 1–4 цього семестру.

Систему детально описано в `docs/`:

- [`docs/requirements.md`](docs/requirements.md) — контекст, класифікація
  системи, зацікавлені сторони, реєстр даних, 10 функційних і 6
  нефункційних вимог, розподіл бюджету наскрізної затримки.
- [`docs/diagrams/`](docs/diagrams/) — три архітектурні подання за
  ISO/IEC/IEEE 42010:2022 (контекстне, компонентне, розгортання) у форматі
  Mermaid (`.mmd`) та SVG.
- [`docs/adr/`](docs/adr/) — три записи архітектурних рішень (ADR):
  розміщення детекції (периферія/сервер), транспортний протокол відео,
  стратегія зберігання архіву.
- [`docs/quality-scenarios.md`](docs/quality-scenarios.md) — два сценарії
  атрибутів якості (продуктивність під навантаженням, стійкість до втрати
  зв'язку) з переліком складників, що їх забезпечують.

## Як переглянути діаграми

Найпростіше — відкрити файли `docs/diagrams/*.svg` подвійним кліком: вони
відкриються в браузері й читаються без додаткових інструментів.

Щоб переглянути чи відредагувати вихідний код діаграм (`.mmd`) прямо у
VS Code з живим прев'ю, встановіть розширення `bierner.markdown-mermaid` і
відкрийте файл у режимі попереднього перегляду Markdown
(`Ctrl+Shift+V`) — для цього достатньо вставити вміст `.mmd` у блок
```` ```mermaid ```` в будь-якому `.md`-файлі.

Щоб перегенерувати SVG з початкового `.mmd` (наприклад, після редагування
діаграми), знадобиться Node.js (LTS):

```
cd docs/diagrams
npx -y @mermaid-js/mermaid-cli -i context.mmd -o context.svg
npx -y @mermaid-js/mermaid-cli -i components.mmd -o components.svg
npx -y @mermaid-js/mermaid-cli -i deployment.mmd -o deployment.svg
```

Якщо `mermaid-cli` не запускається (типово через завантаження Chromium),
альтернатива без встановлення — відкрити вміст `.mmd` на
[mermaid.live](https://mermaid.live) і зберегти результат через
`Actions → SVG`, зберігши ту саму назву файлу.

## Лабораторна робота 2: конвеєр і адаптивне потокове передавання

Репозиторій доповнено конвеєром оброблення медіаданих і адаптивним потоком HLS:

- [`pipeline/pipeline.py`](pipeline/pipeline.py) — конвеєр «декодування — перетворення — кодування» і вимірювання PSNR та SSIM;
- [`results/encoding.csv`](results/encoding.csv), [`docs/pipeline.md`](docs/pipeline.md) — вимірювання чотирьох варіантів кодування й звіт заняття 1;
- [`stream/package.sh`](stream/package.sh), [`stream/player.html`](stream/player.html), `stream/hls/` — драбина з трьох рівнів, сегменти й плеєр з вимірюванням QoE;
- [`results/qoe.csv`](results/qoe.csv), [`docs/qoe.md`](docs/qoe.md) — показники QoE для трьох профілів мережі та звіт заняття 2;
- [`docs/adr/0004-parametry-konveiera-i-dostavlyannya.md`](docs/adr/0004-parametry-konveiera-i-dostavlyannya.md) — рішення щодо параметрів.

Відтворення з кореня репозиторію (Git Bash у Windows):

```
python -m venv .venv && source .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r pipeline/requirements.txt
python tools/make_source.py          # data/source.mp4 (власне згенероване відео)
python pipeline/pipeline.py          # results/encoding.csv
bash stream/get_vendor.sh            # hls.js і dash.js у stream/vendor
bash stream/package.sh hls           # сегменти й master.m3u8
cd stream && python -m http.server 8000   # потім http://localhost:8000/player.html
```

Медіафайли (`data/`) і сегменти `.ts` у репозиторій не додаються.
