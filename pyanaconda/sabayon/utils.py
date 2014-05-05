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

# Glib imports
import glib

# Python imports
import os
import sys
import stat
import sys
import subprocess
import shutil
import statvfs
import tempfile
import time
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser
import logging

# Entropy imports
from entropy.exceptions import EntropyPackageException, DependenciesNotFound, \
    DependenciesCollision
from entropy.const import etpConst, etpSys
from entropy.output import set_mute
import entropy.tools
import entropy.dep
from entropy.core.settings.base import SystemSettings
from entropy.core import Singleton
from entropy.services.client import WebService

# Anaconda imports
from pyanaconda import iutil
from pyanaconda.anaconda import Anaconda
from pyanaconda.constants import INSTALL_TREE, ROOT_PATH
from pyanaconda.progress import progressQ
from pyanaconda.sabayon.const import LIVE_USER, REPO_NAME, \
    FIREWALL_SERVICE, SB_PRIVATE_KEY, SB_PUBLIC_X509, SB_PUBLIC_DER
from pyanaconda.i18n import _

from blivet import arch

log = logging.getLogger("packaging")


class SabayonInstall(object):

    def __init__(self, backend):
        self._backend = backend
        self._live_repo = self._open_live_installed_repository()

    def spawn_chroot(self, args):
        return iutil.execWithRedirect(
            args[0], args[1:], root=ROOT_PATH)

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

        chroot = ROOT_PATH
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
        chroot = ROOT_PATH
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
        chroot = ROOT_PATH
        root = etpSys['rootdir']

        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:
            action_factory = self._backend.entropy.PackageActionFactory()
            action = action_factory.INSTALL_ACTION

            match = self._backend.entropy.atom_match(package)
            package_id, repository_id = match
            if package_id == -1:
                return -1

            pkg = action_factory.get(action, match)
            try:
                exit_st = pkg.start()
            finally:
                pkg.finalize()

            return exit_st

        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def configure_steambox(self, steambox_user):

        steambox_user_file = ROOT_PATH + "/etc/sabayon/steambox-user"
        steambox_user_dir = os.path.dirname(steambox_user_file)
        if not os.path.isdir(steambox_user_dir):
            os.makedirs(steambox_user_dir, 0755)

        with open(steambox_user_file, "w") as f:
            f.write(steambox_user)

    def configure_skel(self):

        # copy Rigo on the desktop
        rigo_desktop = ROOT_PATH+"/usr/share/applications/rigo.desktop"
        if os.path.isfile(rigo_desktop):
            rigo_user_desktop = ROOT_PATH+"/etc/skel/Desktop/rigo.desktop"
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
            FIREWALL_SERVICE,
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

        # XXX: hack
        # For GDM, set DefaultSession= to /etc/skel/.dmrc value
        # This forces GDM to respect the default session and load Cinnamon
        # as default xsession. (This is equivalent of using:
        # /usr/libexec/gdm-set-default-session
        custom_gdm = os.path.join(ROOT_PATH, "etc/gdm/custom.conf")
        skel_dmrc = os.path.join(ROOT_PATH, "etc/skel/.dmrc")
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
        install_data_dir = os.path.join(ROOT_PATH, "install-data")
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
                os.remove(ROOT_PATH + "/etc/env.d/09ati")
            except OSError:
                pass

            for d in ("ati", "nvidia"):
                d = os.path.join(ROOT_PATH, "usr/lib/opengl", d)
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

            udev_bl = ROOT_PATH + "/etc/modprobe.d/bbswitch-blacklist.conf"
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
        sudoers_file = ROOT_PATH + '/etc/sudoers'
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
        private = ROOT_PATH + SB_PRIVATE_KEY
        public = ROOT_PATH + SB_PUBLIC_X509
        der = ROOT_PATH + SB_PUBLIC_DER

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
                ROOT_PATH + "/", pkg_file)
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
            mask_file = os.path.join(ROOT_PATH+'/',
                "etc/entropy/packages/package.mask")
            unmask_file = os.path.join(ROOT_PATH+'/',
                "etc/entropy/packages/package.unmask")

            if os.access(mask_file, os.W_OK) and os.path.isfile(mask_file):
                with open(mask_file,"aw") as f:
                    f.write("\n# added by the Sabayon Installer\n")
                    f.write("x11-drivers/nvidia-drivers\n")
                    f.write("x11-drivers/nvidia-userspace\n")

            if os.access(unmask_file, os.W_OK) and os.path.isfile(unmask_file):
                with open(unmask_file, "aw") as f:
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

        chroot = ROOT_PATH
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

        settings = SystemSettings()
        chroot = ROOT_PATH
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

        chroot = ROOT_PATH
        root = etpSys['rootdir']

        install = []
        self._change_entropy_chroot(chroot)
        try:
            repo = self._backend.entropy.installed_repository()

            for package in packages:
                pkg_id, pkg_rc = repo.atomMatch(package)
                if pkg_id == -1:
                    install.append(package)

            if not install:
                return

            updated = self.update_entropy_repositories()
            if not updated:
                return # ouch

            for package in install:
                self.install_package(package)

        finally:
            self._change_entropy_chroot(root)

    def cleanup_packages(self):

        packages = [
            "app-admin/anaconda",
            "app-misc/anaconda-runtime",
            "app-misc/anaconda-runtime-gui",
            "dev-python/python-blivet",
            "dev-python/python-meh",
            "dev-util/pykickstart",
            "libselinux",
            "sys-process/audit",
            ]

        chroot = ROOT_PATH
        root = etpSys['rootdir']

        self._change_entropy_chroot(chroot)
        try:
            repo = self._backend.entropy.installed_repository()

            for package in packages:

                pkg_id, pkg_rc = repo.atomMatch(package)
                if pkg_id == -1:
                    continue

                self.remove_package(package)

        finally:
            self._change_entropy_chroot(root)
