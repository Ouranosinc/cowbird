FROM python:3.7-alpine
LABEL Description="Runs Cowbird middleware to manage interactions between various birds of the bird-house stack."
LABEL Maintainer="Ouranos, CRIM"
LABEL Vendor="Ouranos inc."
LABEL Version="0.1.0"

ENV COWBIRD_DIR=/opt/local/src/cowbird
ENV COWBIRD_CONFIG_DIR=${COWBIRD_DIR}/config
WORKDIR ${COWBIRD_DIR}

# install dependencies
COPY cowbird/__init__.py cowbird/__meta__.py ${COWBIRD_DIR}/cowbird/
COPY requirements* setup.py README.rst CHANGES.rst ${COWBIRD_DIR}/
RUN apk update \
    && apk add \
    bash \
    libxslt-dev \
    && apk add --virtual .build-deps \
    gcc \
    libffi-dev \
    musl-dev \
    && pip install --no-cache-dir --upgrade -r requirements-sys.txt \
    && pip install --no-cache-dir -e ${COWBIRD_DIR} \
    && apk --purge del .build-deps

# install app package source, avoid copying the rest
COPY ./config/cowbird.example.ini ${COWBIRD_CONFIG_DIR}/cowbird.ini
COPY ./cowbird ${COWBIRD_DIR}/cowbird/
# equivalent of `make install` without conda env and pre-installed packages
RUN pip install --no-dependencies -e ${COWBIRD_DIR}

CMD gunicorn --paste ${COWBIRD_CONFIG_DIR}/cowbird.ini --preload
