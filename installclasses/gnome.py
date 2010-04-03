#
# gnome.py
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

    # name has underscore used for mnemonics, strip if you dont need it
    id = "sabayon_gnome"
    name = N_("Sabayon _GNOME Desktop")
    _description = N_("Select this installation type for a default installation "
                     "with the GNOME desktop environment. "
                     "After this installation process you will "
                     "be able to install additional packages.")
    _descriptionFields = (productName,)
    sortPriority = 10000

    # check if GNOME is available on the system
    if not Entropy().is_installed("gnome-base/gnome-session"):
        hidden = 1

    tasks = [(N_("Graphical Desktop"),
              ["admin-tools", "base", "base-x", "core", "editors", "fonts",
               "games", "gnome-desktop", "graphical-internet", "graphics",
               "hardware-support", "input-methods", "java", "office",
               "printing", "sound-and-video", "text-internet"]),
             (N_("Software Development"),
              ["base", "base-x", "core", "development-libs",
               "development-tools", "editors", "fonts", "gnome-desktop",
               "gnome-software-development", "graphical-internet", "graphics",
               "hardware-support", "input-methods", "java", "text-internet",
               "x-software-development"]),
             (N_("Web Server"),
              ["admin-tools", "base", "base-x", "core", "editors",
               "gnome-desktop", "graphical-internet", "hardware-support",
               "java", "text-internet", "web-server"]),
             (N_("Minimal"), ["core"])]

    def configure(self, anaconda):
        BaseInstallClass.configure(self, anaconda)
        BaseInstallClass.setDefaultPartitioning(self,
            anaconda.storage, anaconda.platform)

    def setSteps(self, anaconda):
        BaseInstallClass.setSteps(self, anaconda)

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

        # This line means we do not support upgrading from anything older
        # than two versions ago!
        return newVer > oldVer and newVer - oldVer <= 2

    def __init__(self):
        BaseInstallClass.__init__(self)
