#!/usr/bin/env bash
# Заняття 1, крок 3: перевірка каналу внесеними збоями.
# Брокер — у Docker, підписник і емулятор — на хості (у середовищі .venv).
# Запуск з кореня репозиторію: bash smart/check_channel.sh
set -e
cd "$(dirname "$0")/.."
export COMPOSE_FILE=smart/docker-compose.yml
mkdir -p data results

docker compose up -d cloud-broker
echo "Чекаю, поки брокер почне відповідати…"
until docker compose exec -T cloud-broker mosquitto_sub -t '$SYS/broker/version' -C 1 -W 3 >/dev/null 2>&1; do
  sleep 1
done
docker compose exec -T cloud-broker mosquitto_sub -t '$SYS/broker/version' -C 1 | tee results/broker_version.txt

# чистий стан: boot = 1
rm -f data/telemetry.db data/telemetry.db-wal data/telemetry.db-shm data/boot.txt
export BROKER=localhost

# підписник працює 40 с самостійно й завершується; перші покази QoS 0 не мають губитися,
# тому спершу підписник, а через 3 с — емулятор
RUN_SECONDS=40 python smart/collector.py > results/channel_collector.txt 2>&1 &
sleep 3
DROP=0.03 DUP=0.02 LATE=0.03 BAD=0.02 HZ=20 DURATION=30 python smart/sensors.py | tee results/channel_sensors.txt
wait

echo "----- Підсумок каналу -----"
python smart/stats.py | tee results/channel_stats.txt
python smart/stats.py --csv > results/channel_stats.csv
echo "Готово: results/channel_sensors.txt, channel_stats.txt, channel_stats.csv"
