ARG QGIS_TEST_VERSION=latest
FROM  qgis/qgis:${QGIS_TEST_VERSION}
MAINTAINER Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>

RUN apt-get update && \
    apt-get -y install python3-pip wget unzip \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update
COPY ./requirements.txt /tmp/
RUN ./.docker/qgis_setup.sh /tmp/
RUN pip3 install -r /tmp/requirements.txt
RUN pip3 install coverage-badge
ENV PATH="/usr/local/bin:${PATH}"
RUN sh /tmp/qgis_setup.sh
# Avoid sqlcmd termination due to locale -- see https://github.com/Microsoft/mssql-docker/issues/163
# RUN echo "nb_NO.UTF-8 UTF-8" > /etc/locale.gen
# RUN echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
# RUN locale-gen


# ENV LANG=C.UTF-8

WORKDIR /