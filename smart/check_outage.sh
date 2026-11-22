#!/usr/bin/env bash
# Заняття 2, кроки 5–6: розгортання edge–cloud, шаблон «публікація — підписка»
# та експеримент із розривом зв'язку на 60 с (буферизація на периферії).
# Запуск з кореня репозиторію: bash smart/check_outage.sh   (≈ 4–5 хв)
set -e
cd "$(dirname "$0")/.."
export COMPOSE_FILE=smart/docker-compose.yml
mkdir -p data results
rm -f results/outage_* results/step5_* results/pubsub_*

docker compose down -v
docker compose up -d --build
echo "Чекаю 25 с, поки система запуститься й збере перші показники…"
sleep 25

echo "----- Крок 5: перевірка розгортання -----"
docker compose ps --format '{{.Service}}: {{.Status}}' | tee results/step5_ps.txt
docker compose logs --tail 1 gateway | tee results/step5_gateway.txt
docker compose exec -T collector python stats.py | tee results/step5_stats.txt

echo "----- Крок 6: публікація — підписка -----"
docker compose exec -T cloud-broker mosquitto_sub -t 'p1/+/+/tele' -v -C 3 2>&1 | tee results/pubsub_cloud.txt
docker compose exec -T edge-broker mosquitto_sub -t 'p1/+/+/state' -v -W 2 2>&1 | tee results/pubsub_edge.txt || true

echo "----- Крок 6: розрив зв'язку на 60 с при λ = 300 повідомлень/с -----"
HZ=100 docker compose up -d sensors
sleep 15
echo "disconnect=$(date -u +%Y-%m-%dT%H:%M:%S)" > results/outage_marks.txt
docker network disconnect mmss_cloud mmss-gateway-1
sleep 60
echo "reconnect=$(date -u +%Y-%m-%dT%H:%M:%S)" >> results/outage_marks.txt
docker network connect mmss_cloud mmss-gateway-1
echo "Зв'язок відновлено, чекаю вивантаження буфера (до 3 хв)…"
for i in $(seq 1 90); do
  sleep 2
  if docker compose logs --tail 1 gateway | grep -qE "буфер=[0-9]{1,2} "; then break; fi
done
sleep 6
docker compose logs -t --since 6m gateway > results/outage_gateway.txt
docker compose stop sensors
sleep 3
docker compose exec -T collector python stats.py | tee results/outage_stats.txt
docker compose exec -T collector python stats.py --csv > results/outage_stats.csv
echo "Готово: results/outage_*"
