#
# livecd.py
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

# System imports
import os
import statvfs
import subprocess
import commands
import stat
import time
import shutil

import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)

# Anaconda imports
import storage
import flags
from constants import productPath as PRODUCT_PATH, DISPATCH_BACK
import backend
import isys
import iutil
import logging
import sabayon.utils
from sabayon import Entropy

# Entropy imports
from entropy.const import etpConst, const_kill_threads
from entropy.misc import TimeScheduled, ParallelTask
from entropy.cache import EntropyCacher
import entropy.tools

log = logging.getLogger("anaconda")

class LiveCDCopyBackend(backend.AnacondaBackend):

    def __init__(self, anaconda):
        backend.AnacondaBackend.__init__(self, anaconda)
        flags.livecdInstall = True
        self.supportsUpgrades = False
        self.supportsPackageSelection = False

        self.osimg = anaconda.methodstr[8:]
        if not os.path.ismount(self.osimg):
            anaconda.intf.messageWindow(_("Unable to find image"),
               _("The given location [%s] isn't a valid %s "
                 "live CD to use as an installation source.")
               %(self.osimg, productName), type = "custom",
               custom_icon="error",
               custom_buttons=[_("Exit installer")])
            raise SystemExit(1)

    def _getLiveSize(self):
        st = os.statvfs(PRODUCT_PATH)
        compressed_byte_size = st.f_blocks * st.f_bsize
        return compressed_byte_size * 3 # 3 times is enough

    def _getLiveSizeMB(self):
        return self._getLiveSize() / 1048576

    def postAction(self, anaconda):
        try:
            anaconda.storage.umountFilesystems(swapoff = False)
            os.rmdir(anaconda.rootPath)
        except Exception, e:
            log.error("Unable to unmount filesystems: %s" % e) 

    def doPreInstall(self, anaconda):
        self._progress = sabayon.utils.SabayonProgress(anaconda)
        self._progress.start()
        self._entropy = Entropy()
        self._entropy.connect_progress(self._progress)

    def doInstall(self, anaconda):
        log.info("Preparing to install Sabayon")

        self._progress.set_label(_("Copying live image to hard drive."))
        self._progress.set_fraction(0.0)

        shot_adbox = TimeScheduled(60, self._progress.spawn_adimage)
        shot_adbox.start()

        #slTools = sabayon.utils.Tools(id, intf, instPath, progressTools)

        time.sleep(120)

        shot_adbox.kill()
        shot_adbox.join()
        const_kill_threads()
        anaconda.intf.setInstallProgressClass(None)

    def doPostInstall(self, anaconda):

        storage.writeEscrowPackets(anaconda)

        # now write out the "real" fstab and mtab
        anaconda.storage.write(anaconda.rootPath)
        f = open(anaconda.rootPath + "/etc/mtab", "w+")
        f.write(anaconda.storage.mtab)
        f.flush()
        f.close()

        if hasattr(self._entropy, "shutdown"):
            self._entropy.shutdown()
        else:
            self._entropy.destroy()
            EntropyCacher().stop()

    def writeConfiguration(self):
        pass

    def kernelVersionList(self, rootPath = "/"):
        # FIXME: implement
        return [("name", "arch", "tag")]

    def doBackendSetup(self, anaconda):

        ossize = self._getLiveSizeMB()
        slash = anaconda.storage.rootDevice
        if slash.size < ossize:
            rc = anaconda.intf.messageWindow(_("Error"),
                _("The root filesystem you created is "
                  "not large enough for this live "
                  "image (%.2f MB required).") % ossize,
                type = "custom",
                custom_icon = "error",
                custom_buttons=[_("_Back"),
                                _("_Exit installer")])
            if rc == 0:
                return DISPATCH_BACK
            else:
                raise SystemExit(1)

    # package/group selection doesn't apply for this backend
    def groupExists(self, group):
        pass

    def selectGroup(self, group, *args):
        pass

    def deselectGroup(self, group, *args):
        pass

    def selectPackage(self, pkg, *args):
        pass

    def deselectPackage(self, pkg, *args):
        pass

    def packageExists(self, pkg):
        return True

    def getDefaultGroups(self, anaconda):
        return []

    def writePackagesKS(self, f, anaconda):
        pass
