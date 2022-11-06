#!/bin/bash
LINE="***********************************************"
PORT="7070"
#WORK_DIR="/mnt/WD/Users/Work/python/ff_dev_plugins/anime_downloader/yommi_api"
WORK_DIR="/Volumes/WD/Users/Work/python/ff_dev_plugins/anime_downloader/yommi_api"

echo "$LINE"
echo "* fast api running..."
echo "$LINE"
pip install fastapi uvicorn[standard] playwright
# shellcheck disable=SC2164
cd "$WORK_DIR"
uvicorn main:app --reload --port=$PORT
#echo "* listening $PORT..."
#echo "$LINE"

