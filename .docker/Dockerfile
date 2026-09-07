ARG QGIS_VERSION=stable
FROM --platform=linux/amd64 qgis/qgis:${QGIS_VERSION}
LABEL maintainer="Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>"
LABEL description="container to test qgispluginsupport"
SHELL ["/bin/bash", "-c"]

RUN apt update && apt install -y \
    python3-flake8 \
    python3-pytest-xdist \
    python3-pytest-cov \
    python3-pyqtgraph \
    python3-scipy \
    python3-matplotlib \
    python3-defusedxml \
    python3-colorama \
    pyqt6-dev-tools \
    qt6-base-dev \
    qt6-base-dev-tools \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

COPY ./.docker/qgis_setup.sh /tmp/
COPY . /usr/src/

ENV PYTHONPATH=\
/usr/share/qgis/python/:\
/usr/share/qgis/python/plugins:\
/usr/lib/python3/dist-packages/qgis:\
$PYTHONPATH

ENV PATH=/usr/lib/qt6/bin:/usr/lib/qt6/libexec:$PATH

RUN pip install --break-system-packages --no-cache-dir \
    flake8-qgis \
    bandit \
    coverage-badge \
    pystac

RUN bash /tmp/qgis_setup.sh
RUN cd /usr/src
RUN ls -l /usr/src
RUN ls -la /usr/lib/qt6/bin

WORKDIR /