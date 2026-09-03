ARG QGIS_TEST_VERSION=latest
FROM  qgis/qgis:${QGIS_TEST_VERSION}
LABEL maintainer="Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>"
LABEL description="container to test qgispluginsupport"
SHELL ["/bin/bash", "-c"]

RUN apt update && apt install -y \
    python3-flake8 \
    python3-pytest-xdist \
    python3-pytest-cov \
    python3-venv \
    pyqt6-dev-tools \
    qt6-base-dev \
    qt6-base-dev-tools \
    libxcb-cursor0 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /tmp/
COPY ./.docker/qgis_setup.sh /tmp/
COPY ./runfirst.py /tmp/
COPY ./scripts/ /tmp/scripts/

RUN python3 -m venv --system-site-packages /venv/qps
ENV PATH=/venv/qps/bin:$PATH
ENV PYTHONPATH=/usr/share/qgis/python/:/usr/share/qgis/python/plugins:/usr/lib/python3/dist-packages/qgis:/usr/share/qgis/python/qgis

RUN /venv/qps/bin/pip install --upgrade pip && \
    /venv/qps/bin/pip install --no-cache-dir -r /tmp/requirements.txt

RUN bash /tmp/qgis_setup.sh

RUN /venv/qps/bin/python /tmp/runfirst.py

RUN ls -l /usr/src
RUN ls -la /usr/lib/qt6/bin

WORKDIR /