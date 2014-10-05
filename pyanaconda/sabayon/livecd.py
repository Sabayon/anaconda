# -*- coding: utf-8 -*-
#
# livecd.py
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

import os
import time
import logging
import threading

from pyanaconda.errors import errorHandler, ERROR_RAISE
from pyanaconda import iutil
from pyanaconda.flags import flags
from pyanaconda.packaging import ImagePayload, PayloadInstallError
from pyanaconda.threads import threadMgr, AnacondaThread
from pyanaconda.i18n import _
from pyanaconda.constants import ROOT_PATH, INSTALL_TREE, THREAD_LIVE_PROGRESS
from pyanaconda.progress import progressQ

from blivet.size import Size

from pyanaconda.sabayon import utils
from pyanaconda.sabayon import Entropy

log = logging.getLogger("packaging")


class LiveCDCopyBackend(ImagePayload):

    def __init__(self, *args, **kwargs):
        super(LiveCDCopyBackend, self).__init__(*args, **kwargs)

        # Used to adjust size of ROOT_PATH when files are already present
        self._adj_size = 0
        self.pct = 0
        self.pct_lock = None
        self._source_size = None
        self._sabayon_install = None

        self._packages = None

        self._entropy_prop = None
        self._entropy_prop_lock = threading.RLock()

    @property
    def entropy(self):
        with self._entropy_prop_lock:
            if self._entropy_prop is None:
                self._entropy_prop = Entropy()

        return self._entropy_prop

    @property
    def kernelVersionList(self):
        vers = []
        for name in os.listdir("/boot"):
            if name.startswith("kernel-genkernel-"):
                vers.append(name[len("kernel-genkernel-"):])
        return vers

    @property
    def spaceRequired(self):
        return Size(bytes=iutil.getDirSize(
                os.path.realpath(INSTALL_TREE)) * 1024)

    def recreateInitrds(self, force=False):
        log.info("calling recreateInitrds()")

    def dracutSetupArgs(self):
        log.info("calling dracutSetupArgs()")
        return []

    def bootFilterArgs(self, boot_args):
        log.info("calling bootFilterArgs with: %s" % (sorted(boot_args),))

        drop_args = set()
        for arg in boot_args:
            if arg.startswith("rd."): # rd.luks, rd.lvm, rd.md
                drop_args.add(arg)

        log.info("bootFilterArgs, filtering: %s" % (sorted(drop_args),))
        boot_args.difference_update(drop_args)

    @property
    def repos(self):
        return self.entropy.repositories()

    def setup(self, storage):
        super(LiveCDCopyBackend, self).setup(storage)

    def progress(self):
        """Monitor the amount of disk space used on the target and source and
           update the hub's progress bar.
        """
        mountpoints = self.storage.mountpoints.copy()
        last_pct = -1
        while self.pct < 100:
            dest_size = 0
            for mnt in mountpoints:
                mnt_stat = os.statvfs(ROOT_PATH+mnt)
                dest_size += mnt_stat.f_frsize * (mnt_stat.f_blocks - mnt_stat.f_bfree)
            if dest_size >= self._adj_size:
                dest_size -= self._adj_size

            pct = 0
            source_size = int(self._source_size)
            if source_size:
                pct = int(100 * dest_size / source_size)
            if pct != last_pct:
                with self.pct_lock:
                    self.pct = pct
                last_pct = pct
                progressQ.send_message(_("Installing software") + (" %d%%") % (min(100, self.pct),))
            time.sleep(0.777)

    def preInstall(self, packages=None, groups=None):
        """ Perform pre-installation tasks. """
        super(LiveCDCopyBackend, self).preInstall(
            packages=packages, groups=groups)
        progressQ.send_message(_("Installing software") + (" %d%%") % (0,))
        self._sabayon_install = utils.SabayonInstall(self)

        self._packages = packages

    def install(self):
        """ Install the payload. """
        self.pct_lock = threading.Lock()
        self.pct = 0
        self._source_size = self.spaceRequired

        threadMgr.add(AnacondaThread(name=THREAD_LIVE_PROGRESS,
                                     target=self.progress))

        cmd = "rsync"
        # preserve: permissions, owners, groups, ACL's, xattrs, times,
        #           symlinks, hardlinks
        # go recursively, include devices and special files, don't cross
        # file system boundaries
        args = ["-pogAXtlHrDx", "--exclude", "/dev/", "--exclude", "/proc/",
                "--exclude", "/sys/", "--exclude", "/run/",
                "--exclude", "/etc/machine-id", INSTALL_TREE+"/", ROOT_PATH]
        try:
            rc = iutil.execWithRedirect(cmd, args)
        except (OSError, RuntimeError) as e:
            msg = None
            err = str(e)
            log.error(err)
        else:
            err = None
            msg = "%s exited with code %d" % (cmd, rc)
            log.info(msg)

        if err or rc == 12:
            exn = PayloadInstallError(err or msg)
            if errorHandler.cb(exn) == ERROR_RAISE:
                raise exn

        # Wait for progress thread to finish
        with self.pct_lock:
            self.pct = 100
        threadMgr.wait(THREAD_LIVE_PROGRESS)

    def _setDefaultBootTarget(self):
        """ Set the default systemd target for the system. """
        # If X was already requested we don't have to continue
        if self.data.xconfig.startX:
            return

        if not flags.usevnc:
            # We only manipulate the ksdata.  The symlink is made later
            # during the config write out.
            self.data.xconfig.startX = True

    def postInstall(self):
        super(LiveCDCopyBackend, self).postInstall()

        log.info("Preparing to configure Sabayon (backend postInstall)")

        self._sabayon_install.spawn_chroot(
            ["/usr/bin/systemd-machine-id-setup"]
            )
        self._sabayon_install.setup_secureboot()
        self._sabayon_install.setup_sudo()
        self._sabayon_install.remove_proprietary_drivers()
        self._sabayon_install.setup_nvidia_legacy()
        self._sabayon_install.configure_skel()
        self._sabayon_install.configure_services()
        self._sabayon_install.spawn_chroot(["env-update"])
        self._sabayon_install.spawn_chroot(["ldconfig"])

        if self._packages:
            log.info("Preparing to install these packages: %s" % (
                    self._packages,))
            self._sabayon_install.setup_entropy_mirrors()
            self._sabayon_install.maybe_install_packages(self._packages)

        self._sabayon_install.configure_boot_args()

        self._sabayon_install.emit_install_done()

        progressQ.send_message(_("Sabayon configuration complete"))

    def configure(self):
        super(LiveCDCopyBackend, self).configure()

        log.info("Preparing to configure Sabayon (backend configure)")

        self._sabayon_install.spawn_chroot(["locale-gen"])

        try:
            username = self.data.user.userList[0].name
        except IndexError as err:
            log.error(
                "Cannot get default username, default to root: %s" % (
                    err,))
            username = "root"  # if no admin user was created
        self._sabayon_install.configure_steambox(username)

        # also remove hw.hash
        hwhash_file = os.path.join(ROOT_PATH, "etc/entropy/.hw.hash")
        try:
            os.remove(hwhash_file)
        except (OSError, IOError):
            pass

        self._sabayon_install.cleanup_packages()
