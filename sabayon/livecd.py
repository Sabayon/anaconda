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

import os
import statvfs
import subprocess
import stat

import storage
import backend
import flags
from constants import productPath as PRODUCT_PATH

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
            sys.exit(0)

    def _getLiveSize(self):
        st = os.statvfs(PRODUCT_PATH)
        compressed_byte_size = st.f_block * st.f_bsize
        return compressed_byte_size * 3 # 3 times is enough

    def _getLiveSizeMB(self):
        return self._getLiveSize() / 1048576

    def _unmountNonFstabDirs(self, anaconda):
        # unmount things that aren't listed in /etc/fstab.  *sigh*
        dirs = []
        if flags.selinux:
            dirs.append("/selinux")
        for dir in dirs:
            try:
                isys.umount("%s/%s" %(anaconda.rootPath,dir), removeDir = False)
            except Exception, e:
                log.error("unable to unmount %s: %s" %(dir, e))

    def postAction(self, anaconda):
        self._unmountNonFstabDirs(anaconda)
        try:
            anaconda.storage.umountFilesystems(swapoff = False)
            os.rmdir(anaconda.rootPath)
        except Exception, e:
            log.error("Unable to unmount filesystems: %s" % e) 

    def doPreInstall(self, anaconda):
        if anaconda.dir == DISPATCH_BACK:
            self._unmountNonFstabDirs(anaconda)
            return
        anaconda.storage.umountFilesystems(swapoff = False)

    def doInstall(self, anaconda):
        log.info("Preparing to install packages")

        progress = anaconda.intf.instProgress
        progress.set_label(_("Copying live image to hard drive."))
        progress.processEvents()

        osimg = self.osimg
        osfd = os.open(osimg, os.O_RDONLY)


        rootDevice = anaconda.storage.rootDevice
        rootDevice.setup()
        rootfd = os.open(rootDevice.path, os.O_WRONLY)

        readamt = 1024 * 1024 * 8 # 8 megs at a time
        size = self._getLiveSize()
        copied = 0
        while copied < size:
            try:
                buf = os.read(osfd, readamt)
                written = os.write(rootfd, buf)
            except:
                rc = anaconda.intf.messageWindow(_("Error"),
                        _("There was an error installing the live image to "
                          "your hard drive.  This could be due to bad media.  "
                          "Please verify your installation media.\n\nIf you "
                          "exit, your system will be left in an inconsistent "
                          "state that will require reinstallation."),
                        type="custom", custom_icon="error",
                        custom_buttons=[_("_Exit installer"), _("_Retry")])

                if rc == 0:
                    sys.exit(0)
                else:
                    os.lseek(osfd, 0, 0)
                    os.lseek(rootfd, 0, 0)
                    copied = 0
                    continue

            if (written < readamt) and (written < len(buf)):
                raise RuntimeError, "error copying filesystem!"
            copied += written
            progress.set_fraction(pct = copied / float(size))
            progress.processEvents()

        os.close(osfd)
        os.close(rootfd)

        anaconda.intf.setInstallProgressClass(None)

    def doPostInstall(self, anaconda):

        self._doFilesystemMangling(anaconda)

        storage.writeEscrowPackets(anaconda)

        packages.rpmSetupGraphicalSystem(anaconda)

        # now write out the "real" fstab and mtab
        anaconda.storage.write(anaconda.rootPath)
        f = open(anaconda.rootPath + "/etc/mtab", "w+")
        f.write(anaconda.storage.mtab)
        f.close()

        # rebuild the initrd(s)
        vers = self.kernelVersionList(anaconda.rootPath)
        for (n, arch, tag) in vers:
            packages.recreateInitrd(n, anaconda.rootPath)

    def writeConfiguration(self):
        pass

    def kernelVersionList(self, rootPath = "/"):
        # FIXME: implement
        return ["--kernel-to-implement"]

    def doBackendSetup(self, anaconda):
        # ensure there's enough space on the rootfs
        # FIXME: really, this should be in the general sanity checking, but
        # trying to weave that in is a little tricky at present.
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
                sys.exit(1)

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