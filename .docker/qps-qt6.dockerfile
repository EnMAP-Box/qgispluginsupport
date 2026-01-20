# ARG QGIS_TEST_VERSION=latest
# FROM  qgis/qgis:${QGIS_TEST_VERSION}
FROM registry.gitlab.com/oslandia/qgis/pyqgis-4-checker/pyqgis-qt-checker:latest
LABEL maintainer="Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>"
LABEL description="container to test qgispluginsupport"
SHELL ["/bin/bash", "-c"]
USER root
# RUN dnf update

RUN dnf update -y && \
    dnf install -y  \
    python3-pip \
    python3-flake8  \
    python3-pytest-xdist  \
    python3-pytest-cov

COPY ./requirements.txt /tmp/
COPY ./.docker/qgis_setup.sh /tmp/

RUN mkdir -p venv/qps &&  \
  python3 -m venv --system-site-packages venv/qps
ENV PATH=/venv/qps/bin:$PATH
RUN python3 -m pip install -r /tmp/requirements.txt
#RUN sh /tmp/qgis_setup.sh

# ENV LANG=C.UTF-8
RUN ls -l /usr/src
# RUN python -c 'from colorama.win32 import windll'

WORKDIR /

# Default command (optional)
CMD ["/bin/bash"]