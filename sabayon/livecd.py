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
from anaconda_log import MAIN_LOG_FILE
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
        self._sabayon_install = sabayon.utils.SabayonInstall(anaconda)

    def doInstall(self, anaconda):
        log.info("Preparing to install Sabayon")

        self._progress.set_label(_("Installing Sabayon onto hard drive."))
        self._progress.set_fraction(0.0)

        # sabayonmce boot param if mce is selected
        if Entropy.is_sabayon_mce():
            anaconda.bootloader.args.append("sabayonmce")

        # Actually install
        self._sabayon_install.live_install()
        self._sabayon_install.setup_users()
        self._sabayon_install.spawn_chroot("ldconfig")

        action = _("Configuring Sabayon")
        self._progress.set_label(action)
        self._progress.set_fraction(0.9)

        self._sabayon_install.setup_sudo()
        self._sabayon_install.setup_audio()
        self._sabayon_install.setup_xorg()
        self._sabayon_install.remove_proprietary_drivers()
        self._sabayon_install.setup_nvidia_legacy()
        self._progress.set_fraction(0.95)
        self._sabayon_install.setup_misc_language()
        self._sabayon_install.configure_services()
        self._sabayon_install.copy_udev()
        self._sabayon_install.env_update()

        action = _("Sabayon configuration complete")
        self._progress.set_label(action)
        self._progress.set_fraction(1.0)

    def doPostInstall(self, anaconda):

        self._sabayon_install.emit_install_done()

        storage.writeEscrowPackets(anaconda)

        self._sabayon_install.destroy()
        if hasattr(self._entropy, "shutdown"):
            self._entropy.shutdown()
        else:
            self._entropy.destroy()
            EntropyCacher().stop()

        const_kill_threads()
        anaconda.intf.setInstallProgressClass(None)

    def writeConfiguration(self):
        """
        System configuration is written in anaconda.write().
        Add extra config files setup here.
        """

        # Write critical configuration not automatically written
        self.anaconda.storage.fsset.write()
        # if simple networking is enabled, disable NetworkManager
        if self.anaconda.instClass.simplenet:
            self._sabayon_install.setup_manual_networking()

        self._sabayon_install.spawn_chroot("locale-gen", silent = True)
        # Fix a possible /tmp problem
        self._sabayon_install.spawn("chmod a+w "+self.anaconda.rootPath+"/tmp")

        # HACK: since Anaconda doesn't support grub2 yet
        # Grub configuration is disabled
        # and this code overrides it
        self._setup_grub2()

    def _get_bootloader_args(self):

        # look for kernel arguments we know should be preserved and add them
        ourargs = ["speakup_synth=", "apic", "noapic", "apm=", "ide=", "noht",
            "acpi=", "video=", "vga=", "init=", "splash=", "console=",
            "pci=routeirq", "irqpoll", "nohdparm", "pci=", "floppy.floppy=",
            "all-generic-ide", "gentoo=", "res=", "hsync=", "refresh=", "noddc",
            "xdriver=", "onlyvesa", "nvidia=", "dodmraid", "dmraid",
            "sabayonmce", "quiet", "scandelay=", "gentoo=" ]
        usb_storage_dir = "/sys/bus/usb/drivers/usb-storage"
        if os.path.isdir(usb_storage_dir):
            for cdir, subdirs, files in os.walk(usb_storage_dir):
                if subdirs:
                    ourargs.append("doslowusb")
                    ourargs.append("scandelay=3")
                    break

        # Sabayon MCE install -> MCE support
        # use reference, yeah
        cmdline = self._sabayon_install.cmdline
        if Entropy.is_sabayon_mce() and ("sabayonmce" not in cmdline):
            cmdline.append("sabayonmce")

        final_cmdline = []
        for arg in cmdline:
            for check in ourargs:
                if arg.startswith(check):
                    final_cmdline.append(arg)

        fsset = self.anaconda.storage.fsset
        swap_devices = fsset.swapDevices
        # <storage.devices.Device> subclass
        root_device = self.anaconda.storage.rootDevice
        # device.format.mountpoint, device.format.type, device.format.mountable,
        # device.format.options, device.path, device.fstabSpec
        swap_crypted = False
        root_crypted = False

        if swap_devices:

            log.info("Found swap devices: %s" % (swap_devices,))

            swap_dev = swap_devices[0]
            swap_crypted = False
            crypto_dev = None
            for name in fsset.cryptTab.mappings.keys():
                crypto_dev = fsset.cryptTab[name]['device']
                if swap_dev == crypto_dev or swap_dev.dependsOn(crypto_dev):
                    swap_crypted = True
                    break

            if swap_crypted:
                log.info("Swap crypted? %s, %s, %s" % (swap_crypted,
                    crypto_dev.fstabSpec, crypto_dev.path))
            else:
                log.info("Swap crypted? NO!")

            if swap_crypted:
                final_cmdline.append("resume=swap:%s" % (crypto_dev.fstabSpec,))
                final_cmdline.append("real_resume=%s" % (crypto_dev.fstabSpec,))
                final_cmdline.append("crypt_swap=%s" % (swap_dev.fstabSpec,))
            else:
                final_cmdline.append("resume=swap:%s" % (swap_dev.fstabSpec,))
                final_cmdline.append("real_resume=%s" % (swap_dev.fstabSpec,))

        # setup LVM
        lvscan_out = commands.getoutput("LANG=C LC_ALL=C lvscan").split("\n")[0].strip()
        if not lvscan_out.startswith("No volume groups found"):
            final_cmdline.append("dolvm")
        # Device.fstabSpec => UUID= stuff automatically handled
        final_cmdline.extend(["root=/dev/ram0", "ramdisk=8192"])

        for name in fsset.cryptTab.mappings.keys():
            crypto_dev = fsset.cryptTab[name]['device']
            if root_device == crypto_dev or root_device.dependsOn(crypto_dev):
                root_crypted = True
                break

        log.info("Root crypted? %s, %s, %s" % (root_crypted,
            root_device.fstabSpec, root_device.path))

        if root_crypted:
            final_cmdline.append("real_root=/dev/mapper/root")
            final_cmdline.append("crypt_root=%s" % (root_device.fstabSpec,))
        else:
            final_cmdline.append("real_root=%s" % (root_device.fstabSpec,))

        log.info("Generated boot cmdline: %s" % (final_cmdline,))

        return final_cmdline, swap_crypted, root_crypted

    def _setup_grub2(self):

        cmdline_args, swap_crypted, root_crypted = self._get_bootloader_args()

        # "sda" <string>
        grub_target = self.anaconda.bootloader.getDevice()
        try:
            # <storage.device.PartitionDevice>
            boot_device = self.anaconda.storage.mountpoints["/boot"]
        except KeyError:
            boot_device = self.anaconda.storage.mountpoints["/"]

        cmdline_str = ' '.join(cmdline_args)

        # if root_device or swap encrypted, replace splash=silent
        if swap_crypted or root_crypted:
            cmdline_str = cmdline_str.replace('splash=silent', 'splash=verbose')

        self._write_grub2(cmdline_str, grub_target)
        # disable Anaconda bootloader code
        self.anaconda.bootloader.defaultDevice = -1

    def _write_grub2(self, cmdline, grub_target):

        root_path = self.anaconda.rootPath
        timeout = 5
        default_file_noroot = "/etc/default/grub"
        grub_cfg_noroot = "/boot/grub/grub.cfg"

        log.info("%s: %s => %s\n" % ("_write_grub2", "begin", locals()))

        # setup grub variables
        # this file must exist

        # drop vga= from cmdline
        cmdline = ' '.join([x for x in cmdline.split() if \
            not x.startswith("vga=")])

        f_r = open(root_path + default_file_noroot, "r")
        default_cont = f_r.readlines()
        f_r.close()
        f_w = open(root_path + default_file_noroot, "w")
        for line in default_cont:
            if line.strip().startswith("GRUB_CMDLINE_LINUX="):
                line = 'GRUB_CMDLINE_LINUX="%s"\n' % (cmdline,)
            elif line.strip().startswith("GRUB_TIMEOUT="):
                line = 'GRUB_TIMEOUT=%s\n' % (timeout,)
            elif line.find("/proc/cmdline") != -1:
                # otherwise grub-mkconfig won't work
                continue

            f_w.write(line)
        f_w.flush()
        f_w.close()

        if self.anaconda.bootloader.password and self.anaconda.bootloader.pure:
            # still no proper support, so implement what can be implemented
            # XXX: unencrypted password support
            pass_file = root_path + "/etc/grub.d/00_password"
            f_w = open(pass_file, "w")
            f_w.write("""\
set superuser="root"
password root """+str(self.anaconda.bootloader.pure)+"""
            """)
            f_w.flush()
            f_w.close()

        # write config file, temp mount /proc
        iutil.execWithRedirect('/bin/mount',
            ["-t", "proc", "proc", "/proc"],
            stdout = MAIN_LOG_FILE,
            stderr = MAIN_LOG_FILE,
            root = root_path
        )
        # and /sys
        iutil.execWithRedirect('/bin/mount',
            ["-t", "sysfs", "sysfs", "/sys"],
            stdout = MAIN_LOG_FILE,
            stderr = MAIN_LOG_FILE,
            root = root_path
        )

        # this must be done before, otherwise gfx mode is not enabled
        iutil.execWithRedirect('/sbin/grub2-install',
            ["/dev/" + grub_target],
            stdout = MAIN_LOG_FILE,
            stderr = MAIN_LOG_FILE,
            root = root_path
        )

        iutil.execWithRedirect('/sbin/grub-mkconfig',
            ["--output=%s" % (grub_cfg_noroot,)],
            stdout = MAIN_LOG_FILE,
            stderr = MAIN_LOG_FILE,
            root = root_path
        )

        iutil.execWithRedirect('/bin/umount',
            ["/proc"],
            stdout = MAIN_LOG_FILE,
            stderr = MAIN_LOG_FILE,
            root = root_path
        )
        iutil.execWithRedirect('/bin/umount',
            ["/sys"],
            stdout = MAIN_LOG_FILE,
            stderr = MAIN_LOG_FILE,
            root = root_path
        )

        log.info("%s: %s => %s\n" % ("_write_grub2", "end", locals()))

    def kernelVersionList(self, rootPath = "/"):
        """
        This won't be used, because our Anaconda codebase is using grub2
        """
        return []

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
