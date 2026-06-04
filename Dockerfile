FROM python:3.11-slim

#============================================
# System deps + Google Chrome + Xvfb
#============================================
ARG CHROME_VERSION="google-chrome-stable"
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unzip \
    zip \
    xvfb \
    && curl -sSL https://dl.google.com/linux/linux_signing_key.pub \
       | gpg --dearmor > /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
       http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update -qqy \
    && apt-get -qqy install ${CHROME_VERSION:-google-chrome-stable} \
    && rm /etc/apt/sources.list.d/google-chrome.list \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

ENV TERM xterm
ENV SCRAPY_SETTINGS_MODULE cVehicles.settings
RUN mkdir -p /app
WORKDIR /app
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
RUN python setup.py install
