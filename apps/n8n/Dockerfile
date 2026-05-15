FROM docker.n8n.io/n8nio/n8n

USER root

RUN mkdir /workflows
# COPY workflows /workflows

RUN chown -R node:node /workflows

USER node

ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh" ]
