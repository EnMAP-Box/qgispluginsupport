# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    asd.py
    Reading Spectral Profiles from ASD data
    ---------------------
    Date                 : Aug 2019
    Copyright            : (C) 2019 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
"""

import os, sys, re, pathlib, json
import csv as pycsv
from .spectrallibraries import *

class ASDBinaryFile(object):


    def __init__(self, path):
        super(ASDBinaryFile, self).__init__()





class ASDSpectralLibraryIO(AbstractSpectralLibraryIO):


    @staticmethod
    def addImportActions(spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        sub = menu.addMenu('ASD')
        a = sub.addAction('ASD Binary')

        a = sub.addAction('ASD CSV')
