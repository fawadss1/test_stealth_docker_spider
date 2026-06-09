FROM python:3.11-slim

#============================================
# System deps + Xvfb
#============================================
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unzip \
    zip \
    xvfb \
    file \
    ca-certificates \
&& rm -rf /var/lib/apt/lists/*

#--------------------------------------------
# Install Brave from a vendored .deb (no network to brave.com needed)
# brave-browser depends on `brave-keyring`, which only exists in Brave's
# (blocked) apt repo and just enables auto-updates. We satisfy that one
# dependency with a dummy package so apt can install Brave + all its real
# libraries from Debian's repos.
#--------------------------------------------

COPY ./vendor/brave-browser_1.91.168_amd64.deb /tmp/brave.deb

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends equivs; \
    printf 'Package: brave-keyring\nVersion: 1.0\nArchitecture: all\nDescription: dummy to satisfy brave-browser dependency (auto-update unused in container)\n' \
> /tmp/brave-keyring.ctl; \
    cd /tmp && equivs-build brave-keyring.ctl; \
    apt-get install -y /tmp/brave-keyring_1.0_all.deb; \
    apt-get install -y /tmp/brave.deb; \
    apt-get purge -y --auto-remove equivs; \
    rm -f /tmp/brave.deb /tmp/brave-keyring*; \
    rm -rf /var/lib/apt/lists/*
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


ENV TERM=xterm
ENV SCRAPY_SETTINGS_MODULE=cVehicles.settings
ENV CHROME_BIN=/usr/bin/brave-browser
ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome

RUN mkdir -p /app
WORKDIR /app
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
RUN python setup.py install