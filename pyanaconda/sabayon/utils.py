# -*- coding: utf-8 -*-
#
# sabayon/utils.py
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

# Python imports
import grp
import os
import subprocess
import shutil
import commands
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser
import logging

# Entropy imports
from entropy.exceptions import EntropyPackageException
from entropy.const import etpConst, etpSys
from entropy.core.settings.base import SystemSettings
from entropy.services.client import WebService

# Anaconda imports
from pyanaconda import iutil
from pyanaconda.constants import INSTALL_TREE
from pyanaconda.progress import progressQ
from pyanaconda.sabayon.const import REPO_NAME, \
    SB_PRIVATE_KEY, SB_PUBLIC_X509, SB_PUBLIC_DER, LIVE_USER
from pyanaconda.sabayon import Entropy
from pyanaconda.i18n import _
from pyanaconda.users import Users

from blivet import arch

log = logging.getLogger("packaging")


class SabayonInstall(object):

    def __init__(self, backend):
        self._backend = backend
        self._live_repo = self._open_live_installed_repository()

    def spawn_chroot(self, args):
        return iutil.execWithRedirect(
            args[0], args[1:], root=iutil.getSysroot())

    def _open_live_installed_repository(self):
        dbpath = INSTALL_TREE + etpConst['etpdatabaseclientfilepath']
        try:
            dbconn = self._backend.entropy.open_generic_repository(
                dbpath, xcache = False, read_only = True,
                dbname = "live_client", indexing_override = False)
        except TypeError:
            # new API
            dbconn = self._backend.entropy.open_generic_repository(
                dbpath, xcache = False, read_only = True,
                name = "live_client", indexing_override = False)
        return dbconn

    def _change_entropy_chroot(self, chroot = None):
        if not chroot:
            self._backend.entropy._installed_repo_enable = True
            self._backend.entropy.noclientdb = False
        else:
            self._backend.entropy._installed_repo_enable = False
            self._backend.entropy.noclientdb = True
        if chroot is None:
            chroot = ""
        self._backend.entropy.switch_chroot(chroot)

    def remove_package(self, atom, match = None):

        chroot = iutil.getSysroot()
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        inst_repo = self._backend.entropy.installed_repository()
        if match is None:
            match = inst_repo.atomMatch(atom)

        try:
            action_factory = self._backend.entropy.PackageActionFactory()
            action = action_factory.REMOVE_ACTION
        except AttributeError:
            action_factory = None
            action = "remove"

        rc = 0
        if match[0] != -1:

            if action_factory is not None:
                pkg = action_factory.get(
                    action, (match[0], inst_repo.name))
                rc = pkg.start()
                pkg.finalize()

            else:
                pkg = self._backend.entropy.Package()
                pkg.prepare((match[0],), "remove")
                if 'remove_installed_vanished' not in pkg.pkgmeta:
                    rc = pkg.run()
                    pkg.kill()

        if chroot != root:
            self._change_entropy_chroot(root)

        return rc

    def install_package_file(self, package_file):
        chroot = iutil.getSysroot()
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:

            try:
                atomsfound = self._backend.entropy.add_package_repository(
                    package_file)
            except EntropyPackageException:
                return -1

            action_factory = self._backend.entropy.PackageActionFactory()
            action = action_factory.INSTALL_ACTION

            repo = 0
            for match in atomsfound:
                repo = match[1]

                pkg = action_factory.get(
                    action, match)
                try:
                    exit_st = pkg.start()
                finally:
                    pkg.finalize()

                if exit_st != 0:
                    return exit_st

            if repo != 0:
                self._backend.entropy.remove_repository(repo)

        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

        return 0

    def install_package(self, package):
        chroot = iutil.getSysroot()
        root = etpSys['rootdir']

        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:

            match = self._backend.entropy.atom_match(package)
            package_id, _repository_id = match
            if package_id == -1:
                return -1

            action_factory = self._backend.entropy.PackageActionFactory()

            pkg = action_factory.get(action_factory.FETCH_ACTION, match)
            try:
                exit_st = pkg.start()
            finally:
                pkg.finalize()

            if exit_st != 0:
                return exit_st

            pkg = action_factory.get(
                action_factory.INSTALL_ACTION, match)
            try:
                exit_st = pkg.start()
            finally:
                pkg.finalize()

            return exit_st

        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def configure_steambox(self, steambox_user):

        log.info("Configuring SteamBox mode using user: %s" % (
                steambox_user,))
        steambox_user_file = iutil.getSysroot() + "/etc/sabayon/steambox-user"
        steambox_user_dir = os.path.dirname(steambox_user_file)
        if not os.path.isdir(steambox_user_dir):
            os.makedirs(steambox_user_dir, 0755)

        with open(steambox_user_file, "w") as f:
            f.write(steambox_user)

    def configure_admin_user_groups(self, username):
        """Configure the admin user groups."""
        def get_all_groups(user):
            for group in grp.getgrall():
                if user in group.gr_mem:
                    yield group.gr_name

        users = Users()
        groups = [x for x in list(get_all_groups(LIVE_USER))]
        users.addUserToGroups(username, groups)

    def configure_skel(self):

        # copy Rigo on the desktop
        rigo_desktop = iutil.getSysroot()+"/usr/share/applications/rigo.desktop"
        if os.path.isfile(rigo_desktop):
            rigo_user_desktop = iutil.getSysroot()+"/etc/skel/Desktop/rigo.desktop"
            shutil.copy2(rigo_desktop, rigo_user_desktop)
            try:
                os.chmod(rigo_user_desktop, 0775)
            except OSError:
                pass

    def _detect_virt(self):
        """
        Return a virtualization environment identifier using
        systemd-detect-virt. This code is systemd only.
        """
        proc = subprocess.Popen(
            ["/usr/bin/systemd-detect-virt"],
            stdout=subprocess.PIPE)
        exit_st = proc.wait()
        outcome = proc.stdout.read(256)
        proc.stdout.close()
        if exit_st == 0:
            return outcome.strip()

    def is_virtualbox(self):
        return self._detect_virt() == "oracle"

    def is_kvm(self):
        return self._detect_virt() == "kvm"

    def is_hyperv(self):
        return self._detect_virt() == "microsoft"

    def _is_encrypted(self):
        if self._backend.storage.encryptionPassphrase:
            return True
        return False

    def configure_services(self):

        action = _("Configuring System Services")
        progressQ.send_message(action)

         # Remove Installer services
        disable_srvs = [
            "installer-gui",
            "installer-text",
            "sabayonlive",
            "music",
            "cdeject",

            ]
        enable_srvs = [
            "x-setup",
            "vixie-cron",
            "oemsystem",
            ]

        if self._backend.entropy.is_sabayon_mce():
            enable_srvs.append("sabayon-mce")
            enable_srvs.append("NetworkManager-wait-online")
        else:
            disable_srvs.append("sabayon-mce")

        if self.is_virtualbox():
            enable_srvs.append("virtualbox-guest-additions")
        else:
            disable_srvs.append("virtualbox-guest-additions")

        for srv in disable_srvs:
            self.spawn_chroot(
                ["systemctl", "--no-reload", "disable",
                 srv + ".service"])

        for srv in enable_srvs:
            self.spawn_chroot(
                ["systemctl", "--no-reload", "enable",
                 srv + ".service"])

        # For GDM, set DefaultSession= to /etc/skel/.dmrc value
        # This forces GDM to respect the default session and load Cinnamon
        # as default xsession. (This is equivalent of using:
        # /usr/libexec/gdm-set-default-session
        custom_gdm = os.path.join(iutil.getSysroot(), "etc/gdm/custom.conf")
        skel_dmrc = os.path.join(iutil.getSysroot(), "etc/skel/.dmrc")
        if os.path.isfile(custom_gdm) and os.path.isfile(skel_dmrc):
            skel_config = ConfigParser.ConfigParser()
            skel_session = None
            if skel_dmrc in skel_config.read(skel_dmrc):
                skel_session = skel_config.get("Desktop", "Session")
            if skel_session:
                # set inside custom_gdm
                gdm_config = ConfigParser.ConfigParser()
                gdm_config.optionxform = str
                if custom_gdm in gdm_config.read(custom_gdm):
                    gdm_config.set("daemon", "DefaultSession", skel_session)
                    with open(custom_gdm, "w") as gdm_f:
                        gdm_config.write(gdm_f)

        # drop /install-data now, bug 4019
        install_data_dir = os.path.join(iutil.getSysroot(), "install-data")
        if os.path.isdir(install_data_dir):
            shutil.rmtree(install_data_dir, True)

    def remove_proprietary_drivers(self):
        """
        Detect a possible OSS video card and remove /etc/env.d/*ati
        """
        bb_enabled = os.path.exists("/tmp/.bumblebee.enabled")

        xorg_x11 = self._get_opengl() == "xorg-x11"

        if xorg_x11 and not bb_enabled:

            try:
                os.remove(iutil.getSysroot() + "/etc/env.d/09ati")
            except OSError:
                pass

            for d in ("ati", "nvidia"):
                d = os.path.join(iutil.getSysroot(), "usr/lib/opengl", d)
                try:
                    shutil.rmtree(d, True)
                except (shutil.Error, OSError):
                    pass

            self.remove_package("ati-drivers")
            self.remove_package("ati-userspace")
            self.remove_package("nvidia-settings")
            self.remove_package("nvidia-drivers")
            self.remove_package("nvidia-userspace")

        # bumblebee support
        if bb_enabled:
            self.spawn_chroot(
                [
                    "systemctl", "--no-reload", "enable",
                    "bumblebeed.service",
                    ]
                )

            udev_bl = iutil.getSysroot() + "/etc/modprobe.d/bbswitch-blacklist.conf"
            with open(udev_bl, "w") as bl_f:
                bl_f.write("""\
# Added by the Sabayon Installer to avoid a race condition
# between udev loading nvidia.ko or nouveau.ko and bbswitch,
# which wants to manage the driver itself.
blacklist nvidia
blacklist nouveau
""")


    def _get_opengl(self, chroot = None):
        """
        get the current OpenGL subsystem (ati,nvidia,xorg-x11)
        """

        if chroot is None:
            oglprof = os.getenv('OPENGL_PROFILE')
            if oglprof:
                return oglprof
            chroot = ""

        ogl_path = chroot+"/etc/env.d/03opengl"
        if os.path.isfile(ogl_path) and os.access(ogl_path,os.R_OK):
            f = open(ogl_path,"r")
            cont = [x.strip() for x in f.readlines() if \
                x.strip().startswith("OPENGL_PROFILE")]
            f.close()
            if cont:
                xprofile = cont[-1]
                if "nvidia" in xprofile:
                    return "nvidia"
                elif "ati" in xprofile:
                    return "ati"

        return "xorg-x11"

    def setup_sudo(self):
        sudoers_file = iutil.getSysroot() + '/etc/sudoers'
        if os.path.isfile(sudoers_file):
            subprocess.call("sed -i '/NOPASSWD/ s/^/#/' %s" % (sudoers_file,),
                            shell=True)
            with open(sudoers_file, "a") as sudo_f:
                sudo_f.write("\n#Added by Sabayon Installer\n%wheel  ALL=ALL\n")
                sudo_f.flush()

    def setup_secureboot(self):
        if not arch.isEfi():
            # nothing to do about SecureBoot crap
            return

        make = "/usr/lib/quickinst/make-secureboot.sh"
        private = iutil.getSysroot() + SB_PRIVATE_KEY
        public = iutil.getSysroot() + SB_PUBLIC_X509
        der = iutil.getSysroot() + SB_PUBLIC_DER

        orig_der = der[:]
        count = 0
        while os.path.lexists(der):
            count += 1
            der = orig_der + ".%d" % (count,)
            assert count < 1000, "Infinite loop"

        for path in (private, public, der):
            _dir = os.path.dirname(path)
            if not os.path.isdir(_dir):
                os.makedirs(_dir)

        exit_st = subprocess.call(
            [make, private, public, der])
        if exit_st != 0:
            log.warning(
                "Cannot execute make-secureboot, error: %d", exit_st)

    def setup_nvidia_legacy(self):

        # Configure NVIDIA legacy drivers, if needed
        running_file = "/lib/nvidia/legacy/running"
        drivers_dir = "/install-data/drivers"
        if not os.path.isfile(running_file):
            return
        if not os.path.isdir(drivers_dir):
            return

        f = open(running_file)
        # this contains the version we need to match.
        nv_ver = f.readline().strip()
        f.close()

        matches = [
            "=x11-drivers/nvidia-drivers-" + nv_ver + "*",
            "=x11-drivers/nvidia-userspace-" + nv_ver + "*",
            ]
        files = [
            "x11-drivers:nvidia-drivers-" + nv_ver,
            "x11-drivers:nvidia-userspace-" + nv_ver,
            ]

        # remove current
        self.remove_package("nvidia-drivers")
        self.remove_package("nvidia-userspace")

        # install new
        packages = os.listdir(drivers_dir)
        _packages = []
        for pkg_file in packages:
            for target_file in files:
                if pkg_file.startswith(target_file):
                    _packages.append(pkg_file)

        packages = [os.path.join(drivers_dir, x) for x in _packages]
        completed = True

        for pkg_filepath in packages:

            pkg_file = os.path.basename(pkg_filepath)
            if not os.path.isfile(pkg_filepath):
                continue

            dest_pkg_filepath = os.path.join(
                iutil.getSysroot() + "/", pkg_file)
            shutil.copy2(pkg_filepath, dest_pkg_filepath)

            rc = self.install_package_file(dest_pkg_filepath)
            _completed = rc == 0

            if not _completed:
                log.error("An issue occurred while installing %s" % (pkg_file,))

            try:
                os.remove(dest_pkg_filepath)
            except OSError:
                pass

            if not _completed:
                completed = False

        if completed:
            # mask all the nvidia-drivers, this avoids having people
            # updating their drivers resulting in a non working system
            mask_file = os.path.join(iutil.getSysroot()+'/',
                "etc/entropy/packages/package.mask")
            unmask_file = os.path.join(iutil.getSysroot()+'/',
                "etc/entropy/packages/package.unmask")

            if os.access(mask_file, os.W_OK) and os.path.isfile(mask_file):
                with open(mask_file,"a+") as f:
                    f.write("\n# added by the Sabayon Installer\n")
                    f.write("x11-drivers/nvidia-drivers\n")
                    f.write("x11-drivers/nvidia-userspace\n")

            if os.access(unmask_file, os.W_OK) and os.path.isfile(unmask_file):
                with open(unmask_file, "a+") as f:
                    f.write("\n# added by the Sabayon Installer\n")
                    for dep in matches:
                        f.write("%s\n" % (dep,))

        # force OpenGL reconfiguration
        for t in ("xorg-x11", "nvidia"):
            self.spawn_chroot(["eselect", "opengl", "set", t])

    def _get_entropy_webservice(self):
        factory = self._backend.entropy.WebServices()
        webserv = factory.new(REPO_NAME)
        return webserv

    def emit_install_done(self):
        # user installed Sabayon, w00hooh!
        try:
            webserv = self._get_entropy_webservice()
        except WebService.UnsupportedService:
            return
        try:
            webserv.add_downloads(["installer"])
        except Exception as err:
            log.error("Unable to emit_install_done(): %s" % err)

    def setup_entropy_mirrors(self):

        progressQ.send_message("%s: %s" % (
            _("Reordering Entropy mirrors"), _("can take some time..."),))

        chroot = iutil.getSysroot()
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)
        try:
            self._backend.entropy.reorder_mirrors(REPO_NAME)
        except Exception as err:
            log.error("Mirror reordering failure: %s" % (err,))
        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def update_entropy_repositories(self):

        progressQ.send_message(_("Downloading software repositories..."))

        settings = SystemSettings()
        chroot = iutil.getSysroot()
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        repos = list(settings['repositories']['available'].keys())

        try:
            # fetch_security = False => avoid spamming stdout
            try:
                repo_intf = self._backend.entropy.Repositories(
                    repos, fetch_security=False)
            except AttributeError as err:
                log.error("No repositories in repositories.conf")
                return False
            except Exception as err:
                log.error("Unhandled exception: %s" % (err,))
                return False

            try:
                update_rc = repo_intf.sync()
            except Exception as err:
                log.error("Sync error: %s" % (err,))
                return False

            if repo_intf.sync_errors or (update_rc != 0):
                log.error("Cannot download repositories atm")
                return False

            return update_rc == 0

        finally:

            self._backend.entropy.close_repositories()
            settings.clear()
            if chroot != root:
                self._change_entropy_chroot(root)

    def maybe_install_packages(self, packages):

        chroot = iutil.getSysroot()
        root = etpSys['rootdir']

        install = []

        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:
            repo = self._backend.entropy.installed_repository()

            for package in packages:
                pkg_id, _pkg_rc = repo.atomMatch(package)
                if pkg_id == -1:
                    install.append(package)

            if not install:
                return

            updated = self.update_entropy_repositories()
            if not updated:
                return # ouch

            for package in install:
                progressQ.send_message(
                    _("Installing package: %s") % (package,))
                self.install_package(package)

        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def cleanup_packages(self):

        progressQ.send_message(_("Removing install packages..."))

        packages = [
            "app-arch/rpm",
            "app-admin/anaconda",
            "app-admin/authconfig",
            "app-admin/calamares-sabayon",
            "app-admin/calamares-sabayon-branding",
            "app-admin/calamares-sabayon-base-modules",
            "app-admin/calamares",
            "dev-libs/libreport",
            "dev-libs/satyr",
            "dev-python/python-blivet",
            "dev-python/python-meh",
            "dev-util/glade",
            "dev-util/pykickstart",
            "libselinux",
            "sys-process/audit",
            "sys-apps/usermode",
            ]

        chroot = iutil.getSysroot()
        root = etpSys['rootdir']

        if chroot != root:
            self._change_entropy_chroot(chroot)
        try:
            repo = self._backend.entropy.installed_repository()

            if not self.is_virtualbox:
                self.remove_package("virtualbox-guest-additions")

            for package in packages:

                pkg_id, _pkg_rc = repo.atomMatch(package)
                if pkg_id == -1:
                    continue

                self.remove_package(package)

        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def _get_base_kernel_cmdline(self):

        # look for kernel arguments we know should be preserved and add them
        ourargs = ["speakup_synth=", "apic", "noapic", "apm=", "ide=", "noht",
                   "acpi=", "video=", "vga=", "gfxpayload=", "init=", "splash=",
                   "splash", "console=", "pci=routeirq", "irqpoll", "nohdparm",
                   "pci=", "floppy.floppy=", "all-generic-ide", "gentoo=",
                   "res=", "hsync=", "refresh=", "noddc", "xdriver=",
                   "onlyvesa", "nvidia=", "dodmraid", "dmraid", "sabayonmce",
                   "steambox", "quiet", "scandelay=", "doslowusb",
                   "radeon.modeset=", "modeset=", "nomodeset", "domdadm",
                   "dohyperv", "dovirtio"]

        # use reference, yeah
        with open("/proc/cmdline") as cmd_f:
            cmdline = cmd_f.readline().strip().split()
        final_cmdline = []

        if self.is_hyperv() and ("dohyperv" not in cmdline):
            cmdline.append("dohyperv")

        if self.is_kvm() and ("dovirtio" not in cmdline):
            cmdline.append("dovirtio")

        # Sabayon MCE install -> MCE support
        if Entropy.is_sabayon_mce() and ("sabayonmce" not in cmdline):
            cmdline.append("sabayonmce")

        # Sabayon Steam Box support
        if Entropy.is_sabayon_steambox() and ("steambox" not in cmdline):
            cmdline.append("steambox")

        # setup USB parameters, if installing on USB
        root_is_removable = getattr(self._backend.storage.rootDevice,
            "removable", False)
        if root_is_removable:
            cmdline.append("scandelay=10")

        # only add domdadm if we managed to configure some kind of raid
        if self._backend.storage.mdarrays and "domdadm" not in cmdline:
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

        return final_cmdline

    def _get_encrypted_fs_boot_args(self):

        final_cmdline = []

        fsset = self._backend.storage.fsset
        swap_devices = fsset.swapDevices or []
        # <storage.devices.Device> subclass
        root_device = self._backend.storage.rootDevice
        # device.format.mountpoint, device.format.type, device.format.mountable,
        # device.format.options, device.path, device.fstabSpec
        swap_crypto_dev = None
        crypt_uuids = set()

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
            crypt_uuids.add(root_crypto_dev.format.uuid)

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
                    crypt_uuids.add(swap_crypto_dev.format.uuid)
                else:
                    log.info("Not adding crypt_swap= because "
                             "swap_crypto_dev is in root_crypto_devs")

        log.info("Generated boot cmdline: %s, crypt_uuids: %s" % (
                final_cmdline, sorted(crypt_uuids),))
        return final_cmdline, crypt_uuids

    def _fixup_crypttab(self, crypt_uuids):
        """
        python-blivet writes to /etc/crypttab entries that are
        already handled by genkernel. This causes some troubles with
        both openrc and systemd. Both are trying to open them again.
        """
        log.info("called _fixup_crypttab with %s" % (crypt_uuids,))

        crypt_file = iutil.getSysroot() + "/etc/crypttab"
        if not os.path.isfile(crypt_file):
            log.error("%s not found, aborting _fixup_crypttab" % (crypt_file,))
            return

        new_lines = []
        with open(crypt_file, "r") as f:
            for line in f.readlines():

                found = False
                for uuid in crypt_uuids:
                    target = " UUID=%s " % (uuid,)
                    if target in line:
                        found = True
                        break
                if not found:
                    log.info("Skipping line: %s" % (line,))
                    new_lines.append(line)

        with open(crypt_file, "w") as f:
            f.writelines(new_lines)

    def get_boot_args(self):
        """Get Sabayon extra boot args."""
        cmdline = self._get_base_kernel_cmdline()
        parts_cmdline, unused = self._get_encrypted_fs_boot_args()
        cmdline += parts_cmdline

        log.info("Backend generated boot cmdline: %s" % (cmdline,))
        return cmdline

    def setup_boot(self):
        """Setup Sabayon boot config."""
        unused, crypt_uuids = self._get_encrypted_fs_boot_args()
        if crypt_uuids:
            self._fixup_crypttab(crypt_uuids)

    def remove_hwhash(self):
        """Remove the hw.hash file that was copied from the live system.
        """
        hwhash_file = os.path.join(iutil.getSysroot(), "etc/entropy/.hw.hash")
        try:
            os.remove(hwhash_file)
        except (OSError, IOError):
            pass

    def setup_machine_id(self):
        """Setup the machine id configuration, make systemd happy."""
        self.spawn_chroot(["/usr/bin/systemd-machine-id-setup"])
