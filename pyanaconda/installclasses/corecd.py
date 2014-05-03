#
# corecd.py
#
# Copyright (C) 2014 Fabio Erculiani
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

from pyanaconda.installclass import BaseInstallClass
from pyanaconda.i18n import N_

from sabayon import Entropy

class InstallClass(BaseInstallClass):

    id = "sabayon_corecd"
    name = N_("Sabayon Core")
    sortPriority = 9998

    _l10n_domain = "anaconda"

    efi_dir = "sabayon"

    dmrc = None

    def configure(self, anaconda):
        BaseInstallClass.configure(self, anaconda)
        BaseInstallClass.setDefaultPartitioning(self, anaconda.storage)

    def getBackend(self):
        from sabayon.livecd import LiveCDCopyBackend
        return LiveCDCopyBackend

    def __init__(self):
        BaseInstallClass.__init__(self)
