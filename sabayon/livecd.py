# -*- coding: utf-8 -*-
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
from constants import productPath as PRODUCT_PATH, productName as PRODUCT_NAME, \
    DISPATCH_BACK
import backend
import isys
import iutil
import logging
from anaconda_log import PROGRAM_LOG_FILE
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
        self.supportsUpgrades = True
        self.supportsPackageSelection = False
        self._root = anaconda.rootPath

        self.osimg = anaconda.methodstr[8:]
        if not os.path.ismount(self.osimg):
            anaconda.intf.messageWindow(_("Unable to find image"),
               _("The given location [%s] isn't a valid %s "
                 "live CD to use as an installation source.")
               %(self.osimg, PRODUCT_NAME), type = "custom",
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
            os.rmdir(self._root)
        except Exception, e:
            log.error("Unable to unmount filesystems: %s" % e)

    def checkSupportedUpgrade(self, anaconda):
        if anaconda.dir == DISPATCH_BACK:
            return

    def doPreInstall(self, anaconda):
        self._progress = sabayon.utils.SabayonProgress(anaconda)
        self._progress.start()
        self._entropy = Entropy()
        self._entropy.connect_progress(self._progress)
        self._sabayon_install = sabayon.utils.SabayonInstall(anaconda)
        # We use anaconda.upgrade as bootloader recovery step
        self._bootloader_recovery = anaconda.upgrade
        self._install_grub = not self.anaconda.dispatch.stepInSkipList(
            "instbootloader")

    def doInstall(self, anaconda):

        # Disable internal Anaconda bootloader setup, doesn't support GRUB2
        anaconda.dispatch.skipStep("instbootloader", skip = 1)

        if self._bootloader_recovery:
            log.info("Preparing to recover Sabayon")
            self._progress.set_label(_("Recovering Sabayon."))
            self._progress.set_fraction(0.0)
            return
        else:
            log.info("Preparing to install Sabayon")

        self._progress.set_label(_("Installing Sabayon onto hard drive."))
        self._progress.set_fraction(0.0)

        # Actually install
        self._sabayon_install.live_install()
        self._sabayon_install.setup_secureboot()
        self._sabayon_install.setup_users()
        self._sabayon_install.setup_language() # before ldconfig, thx
        # if simple networking is enabled, disable NetworkManager
        if self.anaconda.instClass.simplenet:
            self._sabayon_install.setup_manual_networking()
        else:
            self._sabayon_install.setup_networkmanager_networking()
        self._sabayon_install.setup_keyboard()

        action = _("Configuring Sabayon")
        self._progress.set_label(action)
        self._progress.set_fraction(0.7)

        self._sabayon_install.setup_sudo()
        self._sabayon_install.setup_audio()
        self._sabayon_install.setup_xorg()
        self._sabayon_install.remove_proprietary_drivers()
        try:
            self._sabayon_install.setup_nvidia_legacy()
        except Exception as e:
            # caused by Entropy bug <0.99.47.2, remove in future
            log.error("Unable to install legacy nvidia drivers: %s" % e)

        self._progress.set_fraction(0.8)
        self._sabayon_install.configure_services()
        self._sabayon_install.copy_udev()
        self._sabayon_install.env_update()
        self._sabayon_install.spawn_chroot("locale-gen", silent = True)
        self._sabayon_install.spawn_chroot("ldconfig")
        # Fix a possible /tmp problem
        self._sabayon_install.spawn("chmod a+w "+self._root+"/tmp")
        var_tmp = self._root + "/var/tmp"
        if not os.path.isdir(var_tmp): # wtf!
            os.makedirs(var_tmp)
        var_tmp_keep = os.path.join(var_tmp, ".keep")
        if not os.path.isfile(var_tmp_keep):
            with open(var_tmp_keep, "w") as wt:
                wt.flush()

        action = _("Sabayon configuration complete")
        self._progress.set_label(action)

    def doPostInstall(self, anaconda):

        if not self._bootloader_recovery:
            self._sabayon_install.setup_entropy_mirrors()
            self._sabayon_install.language_packs_install()

        self._progress.set_fraction(1.0)

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
        # ignore crypt_filter_callback here
        self.anaconda.storage.fsset.write()

        log.info("Do we need to run GRUB2 setup? => %s" % (self._install_grub,))

        if self._install_grub:

            # HACK: since Anaconda doesn't support grub2 yet
            # Grub configuration is disabled
            # and this code overrides it
            encrypted, root_crypted, swap_crypted = self._setup_grub2()
            swap_dev_name_changed = False
            if encrypted:
                swap_dev = None
                root_dev = None
                if swap_crypted:
                    # in case of encrypted swap_dev sitting on top of
                    # LVMLogicalVolumeDevice, do not force fstabSpec
                    # to /dev/mapper/swap, otherwise fstab will end up
                    # having wrong devspec.
                    swap_name, swap_dev = swap_crypted
                    if not isinstance(swap_dev,
                                  storage.devices.LVMLogicalVolumeDevice):
                        old_swap_name = swap_dev._name
                        swap_dev._name = swap_name
                        swap_dev_name_changed = True

                if root_crypted:
                    root_name, root_dev = root_crypted
                    old_root_name = root_dev._name
                    if root_name == "root": # comes from /dev/mapper/root
                        root_dev._name = root_name

                def _crypt_filter_callback(cb_dev):
                    # this is required in order to not get
                    # crypt root device and crypt swap written
                    # into /etc/conf.d/dmcrypt, as per bug #2522
                    handled_devs = [swap_dev, root_dev]
                    # use is and not ==, so, loop manually
                    for handled_dev in handled_devs:
                        if cb_dev is handled_dev:
                            # we are already handling this device,
                            # so skip it
                            return False
                        if handled_dev is not None:
                            if handled_dev.dependsOn(cb_dev):
                                # already handling this device, root dev?
                                return False
                    return True

                # HACK: since swap device path value is potentially changed
                # it is required to rewrite the fstab
                # (circular dependency, sigh)
                self.anaconda.storage.fsset.write(
                    crypt_filter_callback=_crypt_filter_callback)
                if swap_crypted and swap_dev_name_changed:
                    swap_dev._name = old_swap_name
                if root_crypted:
                    root_dev._name = old_root_name

        self._copy_logs()
        # also remove hw.hash
        hwhash_file = os.path.join(self._root, "etc/entropy/.hw.hash")
        try:
            os.remove(hwhash_file)
        except (OSError, IOError):
            pass

    def _copy_logs(self):

        # copy log files into chroot
        isys.sync()
        config_files = ["/tmp/anaconda.log", "/tmp/lvmout", "/tmp/resize.out",
             "/tmp/program.log", "/tmp/storage.log"]
        install_dir = self._root + "/var/log/installer"
        if not os.path.isdir(install_dir):
            os.makedirs(install_dir)
        for config_file in config_files:
            if not os.path.isfile(config_file):
                continue
            dest_path = os.path.join(install_dir, os.path.basename(config_file))
            shutil.copy2(config_file, dest_path)

    def _get_bootloader_args(self):

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
        console_kbd, xxx, aaa, yyy, zzz = \
            self._sabayon_install.get_keyboard_layout()
        gk_kbd = keymaps_map.get(console_kbd)

        # look for kernel arguments we know should be preserved and add them
        ourargs = ["speakup_synth=", "apic", "noapic", "apm=", "ide=", "noht",
            "acpi=", "video=", "vga=", "gfxpayload=", "init=", "splash=",
            "console=", "pci=routeirq", "irqpoll", "nohdparm", "pci=",
            "floppy.floppy=", "all-generic-ide", "gentoo=", "res=", "hsync=",
            "refresh=", "noddc", "xdriver=", "onlyvesa", "nvidia=", "dodmraid",
            "dmraid", "sabayonmce", "quiet", "scandelay=", "doslowusb",
            "docrypt", "dokeymap", "keymap=", "radeon.modeset=", "modeset=",
            "nomodeset", "domdadm", "vconsole"]

        # Sabayon MCE install -> MCE support
        # use reference, yeah
        cmdline = self._sabayon_install.cmdline
        if Entropy.is_sabayon_mce() and ("sabayonmce" not in cmdline):
            cmdline.append("sabayonmce")

        # Setup genkernel (init) keyboard layout
        if gk_kbd is not None:
            if "dokeymap" not in cmdline:
                cmdline.append("dokeymap")
                cmdline.append("keymap=%s" % (gk_kbd,))

        # setup USB parameters, if installing on USB
        root_is_removable = getattr(self.anaconda.storage.rootDevice,
            "removable", False)
        if root_is_removable:
            cmdline.append("scandelay=10")

        # check if root device is ext2, ext3 or ext4. In case,
        # add rootfstype=ext* to avoid genkernel crap to mount
        # it wrongly (for example: ext3 as ext2).
        root_dev_type = getattr(self.anaconda.storage.rootDevice.format,
            "name", "")
        if root_dev_type in ("ext2", "ext3", "ext4"):
            cmdline.append("rootfstype=" + root_dev_type)

        # always add md support (we don't know if md have been created)
        if "domdadm" not in cmdline:
            cmdline.append("domdadm")

        previous_vga = None
        final_cmdline = []
        for arg in cmdline:
            for check in ourargs:
                if arg.startswith(check):
                    final_cmdline.append(arg)
                    if arg.startswith("vga="):
                        if previous_vga in final_cmdline:
                            final_cmdline.remove(previous_vga)
                        previous_vga = arg

        fsset = self.anaconda.storage.fsset
        swap_devices = fsset.swapDevices
        # <storage.devices.Device> subclass
        root_device = self.anaconda.storage.rootDevice
        # device.format.mountpoint, device.format.type, device.format.mountable,
        # device.format.options, device.path, device.fstabSpec
        root_crypted = False
        swap_crypted = False
        delayed_crypt_swap = None
        any_crypted = len(fsset.cryptTab.mappings.keys()) > 0

        if swap_devices:
            log.info("Found swap devices: %s" % (swap_devices,))
            swap_dev = swap_devices[0]

            swap_crypto_dev = None
            for name in fsset.cryptTab.mappings.keys():
                swap_crypto_dev = fsset.cryptTab[name]['device']
                if swap_dev == swap_crypto_dev or swap_dev.dependsOn(
                    swap_crypto_dev):
                    swap_crypted = True
                    break

            if swap_crypted:
                # genkernel hardcoded bullshit, cannot change /dev/mapper/swap
                # change inside swap_dev, fstabSpec should return
                # /dev/mapper/swap
                swap_crypted = ("swap", swap_dev)
                # if the swap device is on top of LVM LV device, don't
                # force /dev/mapper/swap, because it's not going to work
                # with current genkernel.
                if not isinstance(swap_dev,
                                  storage.devices.LVMLogicalVolumeDevice):
                    final_cmdline.append("resume=swap:/dev/mapper/swap")
                    final_cmdline.append("real_resume=/dev/mapper/swap")
                else:
                    final_cmdline.append("resume=swap:%s" % (
                            swap_dev.fstabSpec,))
                    final_cmdline.append("real_resume=%s" % (
                            swap_dev.fstabSpec,))
                # NOTE: cannot use swap_crypto_dev.fstabSpec because
                # genkernel doesn't support UUID= on crypto
                delayed_crypt_swap = swap_crypto_dev.path
            else:
                final_cmdline.append("resume=swap:%s" % (swap_dev.fstabSpec,))
                final_cmdline.append("real_resume=%s" % (swap_dev.fstabSpec,))

        # setup LVM
        lvscan_out = commands.getoutput("LANG=C LC_ALL=C lvscan").split(
            "\n")[0].strip()
        if not lvscan_out.startswith("No volume groups found"):
            final_cmdline.append("dolvm")

        crypto_dev = None
        for name in fsset.cryptTab.mappings.keys():
            crypto_dev = fsset.cryptTab[name]['device']
            if root_device == crypto_dev or root_device.dependsOn(crypto_dev):
                root_crypted = True
                break

        # - in case of real device being crypted, crypto_dev is
        #   a storage.devices.PartitionDevice object
        # - in case of crypt over lvm, crypto_dev is
        #   storage.devices.LVMLogicalVolumeDevice

        # crypt over raid?

        def is_parent_a_simple_device(root_device):
            if not hasattr(root_device, 'parents'):
                return False
            for parent in root_device.parents:
                if not isinstance(parent, storage.devices.PartitionDevice):
                    return False
            return True

        def is_parent_a_md_device(root_device):
            if not hasattr(root_device, 'parents'):
                return False
            for parent in root_device.parents:
                if isinstance(parent, storage.devices.MDRaidArrayDevice):
                    return True
            return False

        def is_parent_a_lv_device(root_device):
            if not hasattr(root_device, 'parents'):
                return False
            for parent in root_device.parents:
                if isinstance(parent, storage.devices.LVMVolumeGroupDevice):
                    return True
            return False

        def translate_real_root(root_device, crypted):
            # crypt over anything, == "/dev/mapper/root"
            if crypted and isinstance(root_device, storage.devices.LUKSDevice):
                return "/dev/mapper/root"
            if crypted and is_parent_a_md_device(root_device):
                return "/dev/mapper/root"
            if crypted and is_parent_a_simple_device(root_device):
                return "/dev/mapper/root"

            # not needed anymore with grub 1.99
            # if isinstance(root_device, storage.devices.MDRaidArrayDevice):
            #    return root_device.path
            return root_device.fstabSpec

        crypt_root = None
        if root_crypted:
            log.info("Root crypted? %s, %s, crypto_dev: %s" % (root_crypted,
                root_device.path, crypto_dev.fstabSpec))

            translated_real_root = translate_real_root(root_device, True)
            root_crypted = (os.path.basename(translated_real_root), root_device)
            # must use fstabSpec now, since latest genkernel supports it
            final_cmdline.append("root=%s crypt_root=%s" % (
                translated_real_root, crypto_dev.fstabSpec,))
            # due to genkernel initramfs stupidity, when crypt_root = crypt_swap
            # do not add crypt_swap.
            if delayed_crypt_swap == crypto_dev.path:
                delayed_crypt_swap = None

        else:
            log.info("Root crypted? Nope!")
            final_cmdline.append("root=%s" % (
                translate_real_root(root_device, False),))

        # always add docrypt, loads kernel mods required by cryptsetup devices
        if "docrypt" not in final_cmdline:
            final_cmdline.append("docrypt")

        if delayed_crypt_swap:
            final_cmdline.append("crypt_swap=%s" % (delayed_crypt_swap,))

        log.info("Generated boot cmdline: %s" % (final_cmdline,))

        return final_cmdline, root_crypted, swap_crypted, any_crypted

    def _setup_grub2(self):

        cmdline_args, root_crypted, swap_crypted, any_crypted = \
            self._get_bootloader_args()

        log.info("_setup_grub2, cmdline_args: %s | "
            "root_crypted: %s | swap_crypted: %s" % (cmdline_args,
            root_crypted, swap_crypted,))

        # "sda" <string>
        grub_target = self.anaconda.bootloader.getDevice()
        try:
            # <storage.device.PartitionDevice>
            boot_device = self.anaconda.storage.mountpoints["/boot"]
        except KeyError:
            boot_device = self.anaconda.storage.mountpoints["/"]

        cmdline_str = ' '.join(cmdline_args)

        log.info("_setup_grub2, grub_target: %s | "
            "boot_device: %s | cmdline_str: %s" % (grub_target,
            boot_device, cmdline_str,))

        self._write_grub2(cmdline_str, grub_target)
        # disable Anaconda bootloader code
        self.anaconda.bootloader.defaultDevice = -1
        return root_crypted or swap_crypted, root_crypted, swap_crypted

    def _write_grub2(self, cmdline, grub_target):

        default_file_noroot = "/etc/default/grub"
        grub_cfg_noroot = "/boot/grub/grub.cfg"

        log.info("%s: %s => %s\n" % ("_write_grub2", "begin", locals()))

        # setup grub variables
        # this file must exist

        # drop vga= from cmdline
        #cmdline = ' '.join([x for x in cmdline.split() if \
        #    not x.startswith("vga=")])

        # Since Sabayon 5.4, we also write to /etc/default/sabayon-grub
        grub_sabayon_file = self._root + "/etc/default/sabayon-grub"
        grub_sabayon_dir = os.path.dirname(grub_sabayon_file)
        if not os.path.isdir(grub_sabayon_dir):
            os.makedirs(grub_sabayon_dir)
        with open(grub_sabayon_file, "w") as f_w:
            f_w.write("# this file has been added by the Anaconda Installer\n")
            f_w.write("# containing default installer bootloader arguments.\n")
            f_w.write("# DO NOT EDIT NOR REMOVE THIS FILE DIRECTLY !!!\n")
            f_w.write('GRUB_CMDLINE_LINUX="${GRUB_CMDLINE_LINUX} %s"\n' % (
                cmdline,))
            f_w.flush()

        if self.anaconda.bootloader.password and self.anaconda.bootloader.pure:
            # still no proper support, so implement what can be implemented
            # XXX: unencrypted password support
            pass_file = self._root + "/etc/grub.d/00_password"
            f_w = open(pass_file, "w")
            f_w.write("""\
set superuser="root"
password root """+str(self.anaconda.bootloader.pure)+"""
            """)
            f_w.flush()
            f_w.close()

        # remove device.map if found
        dev_map = self._root + "/boot/grub/device.map"
        if os.path.isfile(dev_map):
            os.remove(dev_map)

        # disable efi by forcing i386-pc if noefi is set
        efi_args = []
        if "noefi" in cmdline.split():
            # we assume that we only support x86_64 and i686
            efi_args.append("--target=i386-pc")

        # this must be done before, otherwise gfx mode is not enabled
        grub2_install = self._root + "/usr/sbin/grub2-install"
        if os.path.lexists(grub2_install):
            iutil.execWithRedirect('/usr/sbin/grub2-install',
                                   ["/dev/" + grub_target,
                                    "--recheck", "--force"] + efi_args,
                                   stdout = PROGRAM_LOG_FILE,
                                   stderr = PROGRAM_LOG_FILE,
                                   root = self._root
                                   )
        else:
            iutil.execWithRedirect('/sbin/grub2-install',
                                   ["/dev/" + grub_target,
                                    "--recheck", "--force"] + efi_args,
                                   stdout = PROGRAM_LOG_FILE,
                                   stderr = PROGRAM_LOG_FILE,
                                   root = self._root
                                   )

        grub2_mkconfig = self._root + "/usr/sbin/grub2-mkconfig"
        if os.path.lexists(grub2_mkconfig):
            iutil.execWithRedirect('/usr/sbin/grub2-mkconfig',
                                   ["--output=%s" % (grub_cfg_noroot,)],
                                   stdout = PROGRAM_LOG_FILE,
                                   stderr = PROGRAM_LOG_FILE,
                                   root = self._root
                                   )
        else:
            iutil.execWithRedirect('/sbin/grub-mkconfig',
                                   ["--output=%s" % (grub_cfg_noroot,)],
                                   stdout = PROGRAM_LOG_FILE,
                                   stderr = PROGRAM_LOG_FILE,
                                   root = self._root
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
            rc = anaconda.intf.messageWindow(_("Warning"),
                _("The root filesystem you created is "
                  "not large enough for this live "
                  "image (%.2f MB required). But I "
                  "could be mistaken.") % ossize,
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
