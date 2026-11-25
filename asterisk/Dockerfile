# Asterisk built from source, for chan_websocket (the media WebSocket channel driver, Asterisk
# 22.6+) on a pinned version. Distribution packages are older than that.
FROM debian:12-slim AS build

ARG ASTERISK_VERSION=22.12.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl wget bzip2 patch pkg-config \
        libedit-dev uuid-dev libjansson-dev libxml2-dev libsqlite3-dev libssl-dev \
        libcurl4-openssl-dev libsrtp2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN curl -fsSL "https://downloads.asterisk.org/pub/telephony/asterisk/releases/asterisk-${ASTERISK_VERSION}.tar.gz" \
    | tar xz --strip-components=1

# BUILD_NATIVE off: the image must run on other CPUs than the one that built it.
# No sound packages: the dialplan plays none.
RUN ./configure --with-pjproject-bundled --with-jansson \
    && make menuselect.makeopts \
    && menuselect/menuselect \
        --disable BUILD_NATIVE \
        --disable-category MENUSELECT_CORE_SOUNDS \
        --disable-category MENUSELECT_EXTRA_SOUNDS \
        --disable-category MENUSELECT_MOH \
        --enable chan_websocket \
        menuselect.makeopts \
    && make -j"$(nproc)" \
    && test -f channels/chan_websocket.so \
    && make install DESTDIR=/out \
    # /var/run is a symlink in the runtime image; the directory is recreated there.
    && rm -rf /out/var/run

FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates gettext-base libedit2 libuuid1 libjansson4 libxml2 libsqlite3-0 libssl3 \
        libcurl4 libsrtp2-1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --home-dir /var/lib/asterisk --shell /usr/sbin/nologin asterisk

COPY --from=build /out/ /
RUN ldconfig \
    && mkdir -p /etc/asterisk /var/run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/asterisk \
    && chown -R asterisk:asterisk /etc/asterisk /var/run/asterisk /var/log/asterisk \
        /var/spool/asterisk /var/lib/asterisk

COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

USER asterisk
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["asterisk", "-f"]
