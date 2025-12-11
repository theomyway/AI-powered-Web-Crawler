#!/bin/bash

# Azure Functions startup script to install Playwright browsers
echo "Starting Playwright browser installation..."

# Install system dependencies for Playwright
apt-get update
apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcursor1 \
    libxi6 \
    fonts-liberation \
    xdg-utils \
    wget

# Install Playwright browsers (chromium only to save space/time)
echo "Installing Playwright Chromium browser..."
python -m playwright install chromium --with-deps

echo "Playwright browser installation complete!"

