#!/usr/bin/env bash
# Драбина якостей і сегменти для адаптивного потокового передавання.
# Запуск з кореня репозиторію: bash stream/package.sh hls (або dash)
set -e
FORMAT=${1:-hls}
SRC=data/source.mp4
SEG=2                 # тривалість сегмента, с
FPS=15                # частота кадрів потоку (як у конвеєрі заняття 1)
GOP=$((SEG * FPS))    # ключовий кадр на початку кожного сегмента

# Три рівні якості (кбіт/с) за результатами заняття 1: верхній рівень -
# h264_400k (SSIM 0,9941 >= 0,99); нижчі зберігають 0,0289 біт/піксель:
#   960x540@15  -> 225 кбіт/с,  640x360@15 -> 100 кбіт/с
# Усі три розміри мають точне відношення 16:9 (це потрібно для DASH).
LADDER=(
  -map "[v1]" -b:v:0 400k -maxrate:v:0 440k -bufsize:v:0 800k
  -map "[v2]" -b:v:1 225k -maxrate:v:1 248k -bufsize:v:1 450k
  -map "[v3]" -b:v:2 100k -maxrate:v:2 110k -bufsize:v:2 200k
)
SCALE="[0:v]fps=$FPS,split=3[a][b][c];[a]scale=1280:720[v1];"
SCALE+="[b]scale=960:540[v2];[c]scale=640:360[v3]"
CODEC=(-c:v libx264 -preset veryfast -pix_fmt yuv420p
       -g $GOP -keyint_min $GOP -sc_threshold 0 -an)

cd "$(dirname "$0")/.."
rm -rf "stream/$FORMAT" && mkdir -p "stream/$FORMAT"

if [ "$FORMAT" = hls ]; then
  ffmpeg -y -hide_banner -loglevel error -i $SRC -filter_complex "$SCALE" \
    "${LADDER[@]}" "${CODEC[@]}" \
    -f hls -hls_time $SEG -hls_playlist_type vod \
    -hls_segment_filename "stream/hls/v%v/seg_%03d.ts" \
    -master_pl_name master.m3u8 -var_stream_map "v:0 v:1 v:2" \
    "stream/hls/v%v/index.m3u8"
else
  ffmpeg -y -hide_banner -loglevel error -i $SRC -filter_complex "$SCALE" \
    "${LADDER[@]}" "${CODEC[@]}" \
    -f dash -seg_duration $SEG -use_template 1 -use_timeline 0 \
    -adaptation_sets "id=0,streams=v" "stream/dash/manifest.mpd"
fi
echo "Готово: stream/$FORMAT"
