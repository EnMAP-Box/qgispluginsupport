#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True
rm -Rf test-outputs
pytest