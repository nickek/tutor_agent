FROM ghcr.io/open-webui/open-webui:main

USER root

RUN mkdir /functions
COPY functions /functions

# RUN mkdir /app/backend/static/assets
COPY assets /app/backend/static/assets

RUN mkdir /models
COPY Modelfile /models/

CMD ["bash", "start.sh"]