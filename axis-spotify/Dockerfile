ARG BUILD_FROM
FROM ${BUILD_FROM}

# Drop the parent image's PulseAudio librespot service; run.sh starts our own
RUN rm -rf /etc/services.d/librespot \
    && apk add --no-cache ffmpeg python3 \
    && librespot --version

COPY run.sh streamer.py ap_check.py /
RUN chmod +x /run.sh

CMD ["/run.sh"]
