FROM python:3.8-alpine

ARG HTTP_PROXY=${HTTP_PROXY}
ARG HTTPS_PROXY=${HTTPS_PROXY}
ARG PKG_VERSION
ENV http_proxy $HTTP_PROXY
ENV https_proxy $HTTPS_PROXY
ENV pkg_version=${PKG_VERSION}
ADD . /service
WORKDIR /service

RUN sh /service/docker-env-conf.sh

EXPOSE 8806
USER onap
WORKDIR /service

ENTRYPOINT modeling/etsicatalog/docker/docker-entrypoint.sh
