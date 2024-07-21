ARG QGIS_TEST_VERSION=latest
FROM  qgis/qgis:${QGIS_TEST_VERSION}
MAINTAINER Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>
RUN apt install -y python3-flake8 python3-pytest-xdist python3-pytest-cov python3-venv pyqt5-dev-tools

COPY ./requirements.txt /tmp/
COPY ./.docker/qgis_setup.sh /tmp/

RUN mkdir -p venv/qps
RUN python3 -m venv --system-site-packages venv/qps
RUN . venv/qps/bin/activate
RUN pip install flake8-qgis coverage-badge

RUN sh /tmp/qgis_setup.sh


# ENV LANG=C.UTF-8

WORKDIR /