#!/usr/bin/env bash
# Exit on any failure
set -o errexit

echo "Installing Python Dependencies..."
pip install -r requirements.txt

echo "Diverting Playwright Installation Path to strictly persist on Render..."
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/src/browsers

echo "Downloading Chromium Engine..."
playwright install chromium
playwright install-deps chromium

echo "Build Pipeline Successfully Finished!"
