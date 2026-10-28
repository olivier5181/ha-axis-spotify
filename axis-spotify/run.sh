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
AIRPLAY="$(opt airplay)"
EXTRA_ARGS=()
if [ "$(opt debug)" = "True" ]; then EXTRA_ARGS+=(--verbose); fi

FIFO=/tmp/spotify.pcm
AIRPLAY_FIFO=/tmp/airplay.pcm
rm -f "$FIFO" "$AIRPLAY_FIFO"
mkfifo "$FIFO" "$AIRPLAY_FIFO"
mkdir -p /data/cache

echo "[axis-spotify] Stream URL: http://<home-assistant-ip>:${PORT}/spotify.mp3"

# Work around Spotify access points the local network blocks
python3 /ap_check.py

# AirPlay first: it wins when both sources play at once
python3 /streamer.py --fifo "$AIRPLAY_FIFO" --fifo "$FIFO" --port "$PORT" --bitrate "$MP3_BITRATE" &

if [ "$AIRPLAY" = "True" ]; then
    # Avahi announces the AirPlay receiver; keep it on the LAN interface only
    IFACE="$(ip route show default | awk '{print $5; exit}')"
    sed -e "s/@IFACE@/${IFACE}/" /etc/avahi/avahi-daemon.conf.template > /etc/avahi/avahi-daemon.conf
    mkdir -p /run/dbus /run/avahi-daemon
    rm -f /run/dbus/dbus.pid /run/dbus/pid /run/avahi-daemon/pid
    dbus-uuidgen --ensure
    dbus-daemon --system --fork
    avahi-daemon --daemonize --no-chroot
    echo "[axis-spotify] AirPlay receiver '${NAME}' announced on ${IFACE}"

    cat > /etc/shairport-sync.conf <<EOF
general = {
    name = "${NAME}";
    output_backend = "pipe";
    mdns_backend = "avahi";
};
pipe = {
    name = "${AIRPLAY_FIFO}";
};
EOF

    (
        while true; do
            shairport-sync -c /etc/shairport-sync.conf || true
            echo "[axis-spotify] shairport-sync exited, restarting in 5 seconds"
            sleep 5
        done
    ) &
fi

# Restart librespot after failures (e.g. temporary internet outages)
(
    while true; do
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
            "${EXTRA_ARGS[@]}" || true
        echo "[axis-spotify] librespot exited, restarting in 5 seconds"
        sleep 5
    done
) &

# If the streamer dies, exit so the add-on stops and the failure is visible
wait -n
echo "[axis-spotify] A process exited, stopping"
exit 1
