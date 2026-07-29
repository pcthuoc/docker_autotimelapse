FROM python:3.11-slim-bullseye

RUN apt-get update && \
    apt-get install -y \
        git gcc g++ make curl gettext wget \
        libxml2-dev libxslt1-dev zlib1g-dev \
        mariadb-client libmariadb-dev \
        libjpeg-dev debconf-utils pkg-config \
        ffmpeg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /
COPY repo/backend/requirements.txt .
RUN pip3 install -r requirements.txt

CMD ["python3", "manage.py", "mqtt_listen"]