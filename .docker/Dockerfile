ARG QGIS_TEST_VERSION=latest
FROM  qgis/qgis:${QGIS_TEST_VERSION}
MAINTAINER Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>
RUN apt install -y python3-flake8

RUN sh /tmp/qgis_setup.sh


# ENV LANG=C.UTF-8

WORKDIR /