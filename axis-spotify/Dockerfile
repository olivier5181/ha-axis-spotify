ARG BUILD_FROM
FROM ${BUILD_FROM}

# Drop the parent image's PulseAudio librespot service; run.sh starts our own
RUN rm -rf /etc/services.d/librespot \
    && apk add --no-cache ffmpeg python3 shairport-sync avahi dbus \
    && rm -f /etc/avahi/services/*.service \
    && librespot --version \
    && shairport-sync -V | grep -q pipe

COPY run.sh streamer.py ap_check.py /
COPY avahi-daemon.conf /etc/avahi/avahi-daemon.conf.template
RUN chmod +x /run.sh

CMD ["/run.sh"]
