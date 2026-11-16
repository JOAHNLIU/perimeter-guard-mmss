#!/usr/bin/env bash
# Запускає локальний вебсервер для ЛР 2. Потім відкрийте http://localhost:8000/player.html
cd "$(dirname "$0")/stream" && python3 -m http.server 8000
