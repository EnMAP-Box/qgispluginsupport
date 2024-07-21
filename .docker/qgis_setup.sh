#!/bin/bash
# Setup QGIS for the automated tests. Modified from
# https://github.com/qgis/QGIS/blob/master/.docker/qgis_resources/test_runner/qgis_setup.sh
#
# Note: on QGIS3 assumes the default profile for root user
#
# - create the folders
# - install startup.py monkey patches
# - disable tips
# - enable the plugin (optionally)

CONF_MASTER_FOLDER="/root/.local/share/QGIS/QGIS3/profiles/default/QGIS/"
CONF_MASTER_FILE="${CONF_MASTER_FOLDER}/QGIS3.ini"

QGIS_MASTER_FOLDER="/root/.local/share/QGIS/QGIS3/profiles/default"
PLUGIN_MASTER_FOLDER="${QGIS_MASTER_FOLDER}/python/plugins"

STARTUP_MASTER_FOLDER="/root/.local/share/QGIS/QGIS3/"

# Creates the config file
mkdir -p $CONF_MASTER_FOLDER
if [ -e "$CONF_MASTER_FILE" ]; then
    rm -f $CONF_MASTER_FILE
fi
touch $CONF_MASTER_FILE

# Creates plugin folder
mkdir -p $PLUGIN_MASTER_FOLDER
mkdir -p $STARTUP_MASTER_FOLDER

# Install the monkey patches to prevent modal stacktrace on python errors
# cp /usr/bin/qgis_startup.py ${STARTUP_MASTER_FOLDER}/startup.py

# Disable tips
printf "[qgis]\n" >> $CONF_MASTER_FILE
SHOW_TIPS=$(qgis --help 2>&1 | head -2 | grep 'QGIS - ' | perl -npe 'chomp; s/QGIS - (\d+)\.(\d+).*/showTips\1\2=false/')
printf "%s\n\n" "$SHOW_TIPS" >> $CONF_MASTER_FILE

# Disable firstRunVersionFlag for master
echo "
[migration]
fileVersion=2
firstRunVersionFlag=30500
settings=true
" >> $CONF_MASTER_FILE