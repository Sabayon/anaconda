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
import statvfs
import subprocess
import commands
import stat
import time
import shutil
import logging
import threading

from pyanaconda.anaconda import Anaconda
from pyanaconda.anaconda_log import PROGRAM_LOG_FILE
from pyanaconda.errors import errorHandler, ERROR_RAISE
from pyanaconda import isys
from pyanaconda.product import productName as PRODUCT_NAME
from pyanaconda import iutil
from pyanaconda import flags
from pyanaconda.packaging import ImagePayload, PayloadSetupError, \
    PayloadInstallError
from pyanaconda.threads import threadMgr, AnacondaThread
from pyanaconda.i18n import _
from pyanaconda.constants import ROOT_PATH, INSTALL_TREE, THREAD_LIVE_PROGRESS
from pyanaconda.progress import progressQ

from blivet.size import Size
import blivet.util

from pyanaconda.sabayon import utils
from pyanaconda.sabayon import Entropy

# Entropy imports
from entropy.const import etpConst, const_kill_threads
from entropy.misc import TimeScheduled, ParallelTask
from entropy.cache import EntropyCacher
import entropy.tools

log = logging.getLogger("packaging")


class LiveCDCopyBackend(ImagePayload):

    def __init__(self, *args, **kwargs):
        super(LiveCDCopyBackend, self).__init__(*args, **kwargs)

        # Used to adjust size of ROOT_PATH when files are already present
        self._adj_size = 0
        self.pct = 0
        self.pct_lock = None

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
        return []

    @property
    def spaceRequired(self):
        return Size(bytes=iutil.getDirSize(
                os.path.realpath(INSTALL_TREE)) * 1024)

    def recreateInitrds(self, force=False):
        log.info("calling recreateInitrds()")

    def dracutSetupArgs(self):
        log.info("calling dracutSetupArgs()")

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

            pct = int(100 * dest_size / int(self._source_size))
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

    ### XXX ###

    def postInstall(self):
        super(LiveCDCopyBackend, self).postInstall()

        log.info("Preparing to configure Sabayon (backend postInstall)")
        self._sabayon_install.setup_secureboot()
        self._sabayon_install.setup_sudo()
        self._sabayon_install.remove_proprietary_drivers()
        self._sabayon_install.setup_nvidia_legacy()
        self._sabayon_install.configure_skel()
        self._sabayon_install.configure_services()
        self._sabayon_install.env_update()
        self._sabayon_install.spawn_chroot("ldconfig")
        self._sabayon_install.setup_entropy_mirrors()
        self._sabayon_install.cleanup_packages()
        self._sabayon_install.emit_install_done()

        progressQ.send_message(_("Sabayon configuration complete"))

    def configure(self):
        super(LiveCDCopyBackend, self).configure()

        log.info("Preparing to configure Sabayon (backend configure)")

        self._sabayon_install.spawn_chroot("locale-gen", silent = True)

        username = self.data.user.userList[0].name
        self._sabayon_install.configure_steambox(username)

        # also remove hw.hash
        hwhash_file = os.path.join(ROOT_PATH, "etc/entropy/.hw.hash")
        try:
            os.remove(hwhash_file)
        except (OSError, IOError):
            pass

    def _get_bootloader_args(self):

        # XXX
        

        # keymaps genkernel vs system map
        keymaps_map = {
            'azerty': 'azerty',
            'be-latin1': 'be',
            'bg_bds-utf8': 'bg',
            'br-abnt2': 'br-a',
            'by': 'by',
            'cf': 'cf',
            'croat': 'croat',
            'cz-lat2': 'cz',
            'de': 'de',
            'dk': 'dk',
            'es': 'es',
            'et': 'et',
            'fi': 'fi',
            'fr-latin9': 'fr',
            'gr': 'gr',
            'hu': 'hu',
            'is-latin1': 'is',
            'it': 'it',
            'jp106': 'jp',
            'mk': 'mk',
            'nl': 'nl',
            'no': 'no',
            'pl2': 'pl',
            'pt-latin1': 'pt',
            'ro': 'ro',
            'ru': 'ru',
            'sk-qwerty': 'sk-y',
            'slovene': 'slovene',
            'trq': 'trq',
            'ua-utf': 'ua',
            'uk': 'uk',
            'us': 'us',
        }
        console_kbd = self.data.keyboard.get()
        gk_kbd = keymaps_map.get(console_kbd)

        # look for kernel arguments we know should be preserved and add them
        ourargs = ["speakup_synth=", "apic", "noapic", "apm=", "ide=", "noht",
            "acpi=", "video=", "vga=", "gfxpayload=", "init=", "splash=",
            "splash", "console=", "pci=routeirq", "irqpoll", "nohdparm", "pci=",
            "floppy.floppy=", "all-generic-ide", "gentoo=", "res=", "hsync=",
            "refresh=", "noddc", "xdriver=", "onlyvesa", "nvidia=", "dodmraid",
            "dmraid", "sabayonmce", "steambox", "quiet", "scandelay=",
            "doslowusb", "dokeymap", "keymap=", "radeon.modeset=",
            "modeset=", "nomodeset", "domdadm", "dohyperv", "dovirtio"]

        # use reference, yeah
        cmdline = cmd_f.readline().strip().split()
        final_cmdline = []

        if self._sabayon_install.is_hyperv() and ("dohyperv" not in cmdline):
            cmdline.append("dohyperv")

        if self._sabayon_install.is_kvm() and ("dovirtio" not in cmdline):
            cmdline.append("dovirtio")

        # Sabayon MCE install -> MCE support
        if Entropy.is_sabayon_mce() and ("sabayonmce" not in cmdline):
            cmdline.append("sabayonmce")

        # Sabayon Steam Box support
        if Entropy.is_sabayon_steambox() and ("steambox" not in cmdline):
            cmdline.append("steambox")

        # Setup genkernel (init) keyboard layout
        if gk_kbd is not None:
            if "dokeymap" not in cmdline:
                cmdline.append("dokeymap")
                cmdline.append("keymap=%s" % (gk_kbd,))

        # setup USB parameters, if installing on USB
        root_is_removable = getattr(self.storage.rootDevice,
            "removable", False)
        if root_is_removable:
            cmdline.append("scandelay=10")

        # TODO(lxnay): drop this when genkernel-next-39 is rolled out
        # check if root device is ext2, ext3 or ext4. In case,
        # add rootfstype=ext* to avoid genkernel crap to mount
        # it wrongly (for example: ext3 as ext2).
        root_dev_type = getattr(self.storage.rootDevice.format,
            "name", "")
        if root_dev_type in ("ext2", "ext3", "ext4"):
            cmdline.append("rootfstype=" + root_dev_type)

        raid_devs = self.storage.mdarrays
        raid_devs += self.storage.mdcontainers
        # only add domdadm if we managed to configure some kind of raid
        if raid_devs and "domdadm" not in cmdline:
            cmdline.append("domdadm")

        # setup LVM
        lvscan_out = commands.getoutput("LANG=C LC_ALL=C lvscan").split(
            "\n")[0].strip()
        if not lvscan_out.startswith("No volume groups found"):
            final_cmdline.append("dolvm")

        previous_vga = None
        for arg in cmdline:
            for check in ourargs:
                if arg.startswith(check):
                    final_cmdline.append(arg)
                    if arg.startswith("vga="):
                        if previous_vga in final_cmdline:
                            final_cmdline.remove(previous_vga)
                        previous_vga = arg

        fsset = self.storage.fsset
        swap_devices = fsset.swapDevices or []
        # <storage.devices.Device> subclass
        root_device = self.storage.rootDevice
        # device.format.mountpoint, device.format.type, device.format.mountable,
        # device.format.options, device.path, device.fstabSpec
        swap_crypto_dev = None

        root_crypto_devs = []
        for name in fsset.cryptTab.mappings.keys():
            root_crypto_dev = fsset.cryptTab[name]['device']
            if root_device == root_crypto_dev or \
                    root_device.dependsOn(root_crypto_dev):
                root_crypto_devs.append(root_crypto_dev)

        log.info("Found root crypt devices: %s" % (root_crypto_devs,))
        for root_crypto_dev in root_crypto_devs:
            # must use fstabSpec now, since latest genkernel supports it
            final_cmdline.append("crypt_roots=%s" % (
                    root_crypto_dev.fstabSpec,))


        log.info("Found swap devices: %s" % (swap_devices,))
        for swap_dev in swap_devices:

            log.info("Working on swap device: %s" % (swap_dev,))

            this_swap_crypted = False
            for name in fsset.cryptTab.mappings.keys():
                swap_crypto_dev = fsset.cryptTab[name]['device']
                swap_depends = swap_dev.dependsOn(swap_crypto_dev)
                log_s = "Checking cryptTab name=%s, swap_dev=%s,"
                log_s += "swap_crypto_dev=%s {%s}, "
                log_s += "swap_dev.dependsOn(swap)=%s"
                log.info(log_s % (
                        name, swap_dev, swap_crypto_dev,
                        swap_crypto_dev.fstabSpec, swap_depends))
                if swap_dev == swap_crypto_dev or swap_depends:
                    this_swap_crypted = True
                    break

            log.info("this_swap_crypted set to %s" % (this_swap_crypted,))

            # Use .path instead of fstabSpec for cmdline because
            # genkernel must create an appropriate device node
            # inside /dev/mapper/ that starts with luks-<UUID>
            # so that the generic /dev/mapper/swap will not be used
            # and systemd won't shit in its pants.
            final_cmdline.append("resume=%s" % (swap_dev.path,))
            if this_swap_crypted:
                add_crypt_swap = True
                for root_crypto_dev in root_crypto_devs:
                    if root_crypto_dev.fstabSpec == swap_crypto_dev.fstabSpec:
                        # due to genkernel initramfs stupidity,
                        # when crypt_root = crypt_swap
                        # do not add crypt_swap.
                        add_crypt_swap = False
                        break

                if add_crypt_swap:
                    # must use fstabSpec now, since latest genkernel supports it
                    final_cmdline.append(
                        "crypt_swaps=%s" % (swap_crypto_dev.fstabSpec,))
                else:
                    log.info("Not adding crypt_swap= because "
                             "swap_crypto_dev is in root_crypto_devs")

        log.info("Generated boot cmdline: %s" % (final_cmdline,))
        return final_cmdline
