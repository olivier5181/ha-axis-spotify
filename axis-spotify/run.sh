#!/bin/bash
set -euo pipefail

OPTS=/data/options.json
opt() { python3 -c "import json,sys; print(json.load(open('$OPTS'))[sys.argv[1]])" "$1"; }

NAME="$(opt name)"
SPOTIFY_BITRATE="$(opt spotify_bitrate)"
MP3_BITRATE="$(opt mp3_bitrate)"
INITIAL_VOLUME="$(opt initial_volume)"
PORT="$(opt port)"
ZEROCONF_PORT="$(opt zeroconf_port)"
EXTRA_ARGS=()
if [ "$(opt debug)" = "True" ]; then EXTRA_ARGS+=(--verbose); fi

FIFO=/tmp/spotify.pcm
rm -f "$FIFO"
mkfifo "$FIFO"
mkdir -p /data/cache

echo "[axis-spotify] Stream URL: http://<home-assistant-ip>:${PORT}/spotify.mp3"

python3 /streamer.py --fifo "$FIFO" --port "$PORT" --bitrate "$MP3_BITRATE" &

librespot \
    --name "$NAME" \
    --device-type speaker \
    --backend pipe \
    --device "$FIFO" \
    --format S16 \
    --bitrate "$SPOTIFY_BITRATE" \
    --initial-volume "$INITIAL_VOLUME" \
    --cache /data/cache \
    --zeroconf-port "$ZEROCONF_PORT" \
    --disable-audio-cache \
    "${EXTRA_ARGS[@]}" &

# If either process dies, exit so the add-on stops and the failure is visible
wait -n
echo "[axis-spotify] A process exited, stopping"
exit 1
