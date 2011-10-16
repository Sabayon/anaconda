#
# xfce.py
#
# Copyright (C) 2010 Fabio Erculiani
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from installclass import BaseInstallClass
from constants import *
from product import *
from flags import flags
import os, types
import iutil

import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)

import installmethod

from sabayon import Entropy
from sabayon.livecd import LiveCDCopyBackend

class InstallClass(BaseInstallClass):

    id = "sabayon_corecd"
    name = N_("Sabayon Core")

    _pixmap_dirs = os.getenv("PIXMAPPATH", "/usr/share/pixmaps").split(":")
    for _pix_dir in _pixmap_dirs:
        _pix_path = os.path.join(_pix_dir, "sabayon-core.png")
        if os.path.isfile(_pix_path):
            pixmap = _pix_path

    dmrc = None
    simplenet = True
    _description = N_("Select this installation type to just install "
         "a Core System without graphical applications. "
         "This is the best choice for Server-oriented "
         "deployments.")
    _descriptionFields = (productName,)
    sortPriority = 9998

    def configure(self, anaconda):
        BaseInstallClass.configure(self, anaconda)
        BaseInstallClass.setDefaultPartitioning(self,
            anaconda.storage, anaconda.platform)

    def setSteps(self, anaconda):
        BaseInstallClass.setSteps(self, anaconda)
        anaconda.dispatch.skipStep("welcome", skip = 1)
        #anaconda.dispatch.skipStep("network", skip = 1)

    def getBackend(self):
        return LiveCDCopyBackend

    def productMatches(self, oldprod):
        if oldprod is None:
            return False

        if oldprod.startswith(productName):
            return True

        return False

    def versionMatches(self, oldver):
        try:
            oldVer = float(oldver)
            newVer = float(productVersion)
        except ValueError:
            return True

        return newVer >= oldVer

    def __init__(self):
        BaseInstallClass.__init__(self)
