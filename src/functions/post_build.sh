#!/bin/bash

# Post-build script for Azure Functions deployment
# Installs Playwright Chromium browser after pip packages are installed

echo "=== Starting post-build script ==="
echo "Installing Playwright Chromium browser..."

# Set PLAYWRIGHT_BROWSERS_PATH to a writable directory within the deployment
export PLAYWRIGHT_BROWSERS_PATH=/tmp/build/expressbuild/.playwright

# Create the playwright directory
mkdir -p $PLAYWRIGHT_BROWSERS_PATH

# Find the playwright driver in the installed packages
SITE_PACKAGES="/tmp/build/expressbuild/.python_packages/lib/site-packages"
DRIVER_PATH="$SITE_PACKAGES/playwright/driver/node"

echo "PLAYWRIGHT_BROWSERS_PATH: $PLAYWRIGHT_BROWSERS_PATH"
echo "SITE_PACKAGES: $SITE_PACKAGES"
echo "Looking for driver..."

# List the playwright directory structure
ls -la $SITE_PACKAGES/playwright/ || echo "No playwright directory"
ls -la $SITE_PACKAGES/playwright/driver/ || echo "No driver directory"

# Find the playwright CLI executable
PLAYWRIGHT_CLI=$(find $SITE_PACKAGES/playwright -name "playwright.sh" -o -name "playwright" -type f 2>/dev/null | head -1)
echo "Found playwright CLI: $PLAYWRIGHT_CLI"

if [ -n "$PLAYWRIGHT_CLI" ]; then
    chmod +x "$PLAYWRIGHT_CLI"
    PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_PATH "$PLAYWRIGHT_CLI" install chromium
else
    echo "Playwright CLI not found, trying node driver..."
    NODE_DRIVER=$(find $SITE_PACKAGES/playwright -name "node" -type f 2>/dev/null | head -1)
    PACKAGE_JSON=$(find $SITE_PACKAGES/playwright -name "package" -type d 2>/dev/null | head -1)
    if [ -n "$NODE_DRIVER" ] && [ -n "$PACKAGE_JSON" ]; then
        chmod +x "$NODE_DRIVER"
        PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_PATH "$NODE_DRIVER" "$PACKAGE_JSON/../cli.js" install chromium
    fi
fi

echo "Listing installed browsers:"
ls -la $PLAYWRIGHT_BROWSERS_PATH/ || echo "No browsers found"

echo "=== Post-build script completed ==="

