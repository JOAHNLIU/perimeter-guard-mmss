#!/usr/bin/env bash
# Завантажує бібліотеки плеєрів hls.js 1.7.3 і dash.js 5.2.1 у stream/vendor.
# Запуск з кореня репозиторію: bash stream/get_vendor.sh
set -e
cd "$(dirname "$0")"
mkdir -p vendor && cd vendor
CDN=https://cdn.jsdelivr.net/npm
curl -L -o hls.min.js $CDN/hls.js@1.7.3/dist/hls.min.js
curl -L -o dash.all.min.js $CDN/dashjs@5.2.1/dist/modern/umd/dash.all.min.js
ls -l
