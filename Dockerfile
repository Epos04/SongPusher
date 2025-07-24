# Wir starten mit einem offiziellen Python-Image
FROM python:3.11-slim

# Systempakete und Google Chrome installieren
# Das ist der Teil, der den Browser in unser System holt
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    --no-install-recommends \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Die passende Version des ChromeDriver herunterladen und installieren
RUN CHROME_VERSION=$(google-chrome --version | cut -d " " -f3 | cut -d "." -f1-3) && \
    DRIVER_VERSION=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json | jq -r ".versions[] | select(.version | startswith(\"${CHROME_VERSION}\")) | .downloads.chromedriver[0].url" | tail -n 1) && \
    wget -q --continue -P /tmp/ ${DRIVER_VERSION} && \
    unzip /tmp/chromedriver-linux64.zip -d /usr/local/bin/ && \
    rm /tmp/chromedriver-linux64.zip

# Verzeichnis für unsere App erstellen
WORKDIR /app

# Python-Abhängigkeiten installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Node.js und TailwindCSS installieren für den Frontend-Build
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm install
COPY static/src/input.css .
COPY static ./static
RUN npm run build

# Den gesamten App-Code kopieren
COPY . .

# Den Port freigeben, auf dem unsere App laufen wird
EXPOSE 10000

# Der Befehl zum Starten der App
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "120"]