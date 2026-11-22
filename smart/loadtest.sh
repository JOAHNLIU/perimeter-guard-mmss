#!/usr/bin/env bash
# Навантажувальне випробування: частота сенсорів зростає ступенями.
# Запуск з кореня репозиторію: bash smart/loadtest.sh   (≈ 6–8 хв)
set -e
cd "$(dirname "$0")/.."
export COMPOSE_FILE=smart/docker-compose.yml
STEP=30                       # тривалість ступеня, с
export MAX_ROWS=10000         # менший буфер: переповниться за ступінь
mkdir -p data results
rm -f results/docker_stats.txt results/load_gateway_last.txt

docker compose down -v        # почати з чистого стану
docker compose build
docker compose up -d edge-broker gateway cloud-broker collector
sleep 5
for HZ in 10 100 200 250 300 350 400 450 500; do
  echo "$(date +%T) HZ=$HZ: λ = $((3 * HZ)) повідомлень/с"      # 3 сенсори
  HZ=$HZ DURATION=$STEP docker compose up -d sensors
  sleep 15                    # середина ступеня: знімок завантаження контейнерів
  { echo "## HZ=$HZ"; docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}'; } >> results/docker_stats.txt
  sleep $((STEP + 5 - 15))
  until docker compose logs --tail 1 gateway | grep -q "буфер=0 "; do
    sleep 2                   # дочекатися, поки буфер спорожніє
  done
done
docker compose logs --tail 1 gateway > results/load_gateway_last.txt
docker compose exec -T collector python stats.py --csv > results/load.csv
cat results/load.csv
echo "Готово: results/load.csv, results/docker_stats.txt. Далі: python smart/plot.py"
