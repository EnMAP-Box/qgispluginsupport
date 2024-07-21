ARG QGIS_TEST_VERSION=latest
FROM  qgis/qgis:${QGIS_TEST_VERSION}
LABEL maintainer="Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>"
LABEL description="container to test qgispluginsupport"
SHELL ["/bin/bash", "-c"]
RUN apt install -y python3-flake8 python3-pytest-xdist python3-pytest-cov python3-venv pyqt5-dev-tools

COPY ./requirements.txt /tmp/
COPY ./.docker/qgis_setup.sh /tmp/


RUN mkdir -p venv/qps
RUN python3 -m venv --system-site-packages venv/qps
ENV PATH=/venv/qps/bin:$PATH
RUN pip install flake8-qgis coverage-badge

RUN ls -lisa /tmp
RUN cat /tmp/qgis_setup.sh
RUN sh /tmp/qgis_setup.sh

# ENV LANG=C.UTF-8

WORKDIR /