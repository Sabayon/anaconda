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
from pyanaconda.anaconda import Anaconda
from pyanaconda.constants import INSTALL_TREE, ROOT_PATH
from pyanaconda.sabayon import Entropy
from pyanaconda.sabayon.const import LIVE_USER, LANGUAGE_PACKS, REPO_NAME, \
    ASIAN_FONTS_PACKAGES, FIREWALL_SERVICE, SB_PRIVATE_KEY, \
    SB_PUBLIC_X509, SB_PUBLIC_DER
from pyanaconda.i18n import _

STDERR_LOG = open("/tmp/anaconda.log","aw")
log = logging.getLogger("packaging")


class SabayonInstall(object):

    def __init__(self, backend):
        self._backend = backend

        self._anaconda = Anaconda.INSTANCE
        self._intf = Anaconda.INSTANCE.intf
        self._live_repo = self._open_live_installed_repository()
        self._package_identifiers_to_remove = set()

    def spawn_chroot(self, args, silent = False):

        pid = os.fork()
        if pid == 0:

            os.chroot(ROOT_PATH)
            os.chdir("/")
            do_shell = False
            myargs = args
            if not isinstance(args, (list, tuple)):
                do_shell = True
            if silent:
                p = subprocess.Popen(args, stdout = STDERR_LOG,
                    stderr = STDERR_LOG, shell = do_shell)
            else:
                p = subprocess.Popen(args, shell = do_shell)
            rc = p.wait()
            os._exit(rc)

        else:

            rcpid, rc = os.waitpid(pid,0)
            return rc

    def spawn(self, args):
        myargs = args
        if isinstance(args, (list, tuple)):
            myargs = ' '.join(args)
        return subprocess.call(myargs, shell = True)

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

    def install_package(self, atom, match = None, silent = False,
                        fetch = False):

        if silent and os.getenv('SABAYON_DEBUG'):
            silent = False

        chroot = ROOT_PATH
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        if match is None:
            match = self._backend.entropy.atom_match(atom)

        oldstdout = sys.stdout
        if silent:
            sys.stdout = STDERR_LOG
            set_mute(True)

        action_factory = self._backend.entropy.PackageActionFactory()
        install_action = action_factory.INSTALL_ACTION
        fetch_action = action_factory.FETCH_ACTION

        try:
            rc = 0
            if match[0] != -1:

                action = install_action
                if fetch:
                    action = fetch_action

                pkg = action_factory.get(
                    action, match)
                rc = pkg.start()
                pkg.finalize()

        finally:
            if silent:
                sys.stdout = oldstdout
                set_mute(False)
            if chroot != root:
                self._change_entropy_chroot(root)

        return rc

    def remove_package(self, atom, match = None, silent = False):

        if silent and os.getenv('SABAYON_DEBUG'):
            silent = False

        chroot = ROOT_PATH
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        inst_repo = self._backend.entropy.installed_repository()
        if match is None:
            match = inst_repo.atomMatch(atom)

        oldstdout = sys.stdout
        if silent:
            sys.stdout = STDERR_LOG
            set_mute(True)

        try:
            action_factory = self._backend.entropy.PackageActionFactory()
            action = action_factory.REMOVE_ACTION
        except AttributeError:
            action_factory = None
            action = "remove"

        try:
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

        finally:
            if silent:
                sys.stdout = oldstdout
                set_mute(False)

        if chroot != root:
            self._change_entropy_chroot(root)

        return rc

    def install_package_file(self, package_file):
        chroot = ROOT_PATH
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:
            atomsfound = self._backend.entropy.add_package_repository(
                package_file)
        except EntropyPackageException:
            return -1

        try:
            action_factory = self._backend.entropy.PackageActionFactory()
            action = action_factory.INSTALL_ACTION
        except AttributeError:
            action_factory = None
            action = "install"

        repo = 0
        for match in atomsfound:
            repo = match[1]

            rc2 = 0

            if action_factory is not None:
                pkg = action_factory.get(
                    action, match)
                rc2 = pkg.start()
                pkg.finalize()

            else:
                pkg = self._backend.entropy.Package()
                pkg.prepare(match, action)
                rc2 = pkg.run()
                pkg.kill()

            if rc2 != 0:
                if chroot != root:
                    self._change_entropy_chroot(root)
                return rc2

        if chroot != root:
            self._change_entropy_chroot(root)

        if repo != 0:
            self._backend.entropy.remove_repository(repo)

        return 0

    def _configure_steambox(self):

        steambox_user_file = ROOT_PATH + "/etc/sabayon/steambox-user"
        steambox_user_dir = os.path.dirname(steambox_user_file)
        if not os.path.isdir(steambox_user_dir):
            os.makedirs(steambox_user_dir, 0755)

        steambox_user = self._anaconda.users.otherUsers[LIVE_USER]['username']
        with open(steambox_user_file, "w") as f:
            f.write(steambox_user)

    def _configure_skel(self):

        # copy Rigo on the desktop
        rigo_desktop = ROOT_PATH+"/usr/share/applications/rigo.desktop"
        if os.path.isfile(rigo_desktop):
            rigo_user_desktop = ROOT_PATH+"/etc/skel/Desktop/rigo.desktop"
            shutil.copy2(rigo_desktop, rigo_user_desktop)
            try:
                os.chmod(rigo_user_desktop, 0775)
            except OSError:
                pass

        gparted_desktop = ROOT_PATH+"/etc/skel/Desktop/gparted.desktop"
        if os.path.isfile(gparted_desktop):
            os.remove(gparted_desktop)

        installer_desk = ROOT_PATH+"/etc/skel/Desktop/liveinst.desktop"
        if os.path.isfile(installer_desk):
            os.remove(installer_desk)

        # install welcome loader
        orig_welcome_desk = ROOT_PATH+"/etc/sabayon/sabayon-welcome-loader.desktop"
        if os.path.isfile(orig_welcome_desk):
            autostart_dir = ROOT_PATH+"/etc/skel/.config/autostart"
            if not os.path.isdir(autostart_dir):
                os.makedirs(autostart_dir)
            desk_name = os.path.basename(orig_welcome_desk)
            desk_path = os.path.join(autostart_dir, desk_name)
            shutil.copy2(orig_welcome_desk, desk_path)

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
        if self._anaconda.storage.encryptionPassphrase:
            return True
        return False

    def _is_firewall_enabled(self):
        if self._anaconda.network.useFirewall:
            return True
        return False

    def _is_systemd_running(self):
        return os.path.isdir("/run/systemd/system")

    def _is_openrc_running(self):
        return os.path.exists("/run/openrc/softlevel")

    def configure_services(self):

        action = _("Configuring System Services")
        self._progress.set_text(action)

        is_sabayon_mce = "1"
        if not Entropy.is_sabayon_mce():
            is_sabayon_mce = "0"

        # Remove Installer services
        config_script = """\
        systemctl --no-reload disable installer-gui.service
        systemctl --no-reload disable installer-text.service

        systemctl --no-reload disable sabayonlive.service
        systemctl --no-reload enable x-setup.service

        systemctl --no-reload enable vixie-cron.service

        systemctl --no-reload disable music.service

        systemctl --no-reload disable cdeject.service

        systemctl --no-reload enable oemsystem.service

        if [ "0" = """+is_sabayon_mce+""" ]; then
            systemctl --no-reload disable sabayon-mce.service
        else
            systemctl --no-reload enable NetworkManager-wait-online.service
        fi
        """
        self.spawn_chroot(config_script, silent = True)

        if self.is_virtualbox():
            self.spawn_chroot("""\
            systemctl --no-reload enable virtualbox-guest-additions.service
            """, silent = True)
        else:
            self.spawn_chroot("""\
            systemctl --no-reload disable virtualbox-guest-additions.service
            """, silent = True)

        if self._is_firewall_enabled():
            self.spawn_chroot("""\
            systemctl --no-reload enable %s.service
            """ % (FIREWALL_SERVICE,), silent = True)
        else:
            self.spawn_chroot("""\
            systemctl --no-reload disable %s.service
            """ % (FIREWALL_SERVICE,), silent = True)

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
            ogl_script = """
                rm -f /etc/env.d/09ati
                rm -rf /usr/lib/opengl/ati
                rm -rf /usr/lib/opengl/nvidia
            """
            self.spawn_chroot(ogl_script)
            self.remove_package('ati-drivers', silent = True)
            self.remove_package('ati-userspace', silent = True)
            self.remove_package('nvidia-settings', silent = True)
            self.remove_package('nvidia-drivers', silent = True)
            self.remove_package('nvidia-userspace', silent = True)

        # bumblebee support
        if bb_enabled:
            bb_script = """
            systemctl --no-reload enable bumblebeed.service
            """
            self.spawn_chroot(bb_script, silent = True)

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

    def get_keyboard_layout(self):
        console_kbd = self._anaconda.keyboard.get()
        kbd = self._anaconda.keyboard.modelDict[console_kbd]
        (name, layout, model, variant, options) = kbd
        # for X, KDE and GNOME
        keylayout = layout.split(",")[0].split("_")[0]
        return console_kbd, keylayout, layout, variant, options

    def setup_keyboard(self):
        console_kbd, keylayout, xorglayout, variant, options = \
            self.get_keyboard_layout()
        def _spawn(args):
            subprocess.call(args, shell=True)
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s gnome &> /dev/null" % (
            ROOT_PATH, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s kde &> /dev/null" % (
            ROOT_PATH, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s lxde &> /dev/null" % (
            ROOT_PATH, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s e17 &> /dev/null" % (
            ROOT_PATH, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 \"%s\" \"%s\" \"%s\" xorg &> /dev/null" % (
            ROOT_PATH, xorglayout, variant, options))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s system &> /dev/null" % (
            ROOT_PATH, console_kbd))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s xfce &> /dev/null" % (
            ROOT_PATH, console_kbd))

    def setup_sudo(self):
        sudoers_file = ROOT_PATH + '/etc/sudoers'
        if os.path.isfile(sudoers_file):
            self.spawn("sed -i '/NOPASSWD/ s/^/#/' %s" % (sudoers_file,))
            with open(sudoers_file, "a") as sudo_f:
                sudo_f.write("\n#Added by Sabayon Installer\n%wheel  ALL=ALL\n")
                sudo_f.flush()

    def setup_secureboot(self):
        if not self._anaconda.platform.isEfi:
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
            msg = _("Cannot generate a SecureBoot key, error: %d") % (
                exit_st,)
            self._intf.messageWindow(
                _("SecureBoot Problem"), msg,
                custom_icon="warning")

    def setup_audio(self):
        asound_state = "/etc/asound.state"
        asound_state2 = "/var/lib/alsa/asound.state"
        if os.path.isfile(asound_state) and os.access(asound_state, os.R_OK):
            asound_state_dest_dir = os.path.dirname(ROOT_PATH+asound_state)
            asound_state_dest_dir2 = os.path.dirname(ROOT_PATH+asound_state2)

            if not os.path.isdir(asound_state_dest_dir):
                os.makedirs(asound_state_dest_dir, 0755)

            if not os.path.isdir(asound_state_dest_dir2):
                os.makedirs(asound_state_dest_dir2, 0755)

            source_f = open(asound_state, "r")
            dest_f = open(ROOT_PATH+asound_state, "w")
            dest2_f = open(ROOT_PATH+asound_state2, "w")
            asound_data = source_f.readlines()
            dest_f.writelines(asound_data)
            dest2_f.writelines(asound_data)
            dest_f.flush()
            dest_f.close()
            dest2_f.flush()
            dest2_f.close()
            source_f.close()

    def _setup_consolefont(self, system_font):
        # /etc/vconsole.conf support
        vconsole_conf = ROOT_PATH + "/etc/vconsole.conf"
        content = []
        if os.path.isfile(vconsole_conf):
            with open(vconsole_conf, "r") as f:
                for line in f.readlines():
                    if line.startswith("FONT="):
                        continue
                    content.append(line)

        content.append("FONT=%s\n" % (system_font,))
        with open(vconsole_conf, "w") as f:
            f.writelines(content)
            f.flush()

    def setup_language(self):
        # Prepare locale variables

        info = self._anaconda.instLanguage.info

        with open(ROOT_PATH + "/etc/env.d/02locale", "w") as f:
            for key in info.keys():
                if info[key] is not None:
                    f.write("%s=\"%s\"\n" % (key, info[key]))
            f.flush()

        # systemd support, same syntax as 02locale for now
        with open(ROOT_PATH + "/etc/locale.conf", "w") as f:
            for key in info.keys():
                if info[key] is not None:
                    f.write("%s=\"%s\"\n" % (key, info[key]))
            f.flush()

        # write locale.gen
        supported_file = "/usr/share/i18n/SUPPORTED"
        if os.path.isfile(supported_file):
            f = open(supported_file, "r")
            locale_supported = [x.strip() for x in f.readlines()]
            f.close()

            libc_locale = info['LANG'].split(".")[0].split("@")[0]
            valid_locales = []
            for locale in locale_supported:
                if locale.startswith(libc_locale):
                    valid_locales.append(locale)

            f = open(ROOT_PATH + "/etc/locale.gen", "w")
            f.write("en_US.UTF-8 UTF-8\n")
            f.write("en_US ISO-8859-1\n")
            for locale in valid_locales:
                f.write("%s\n" % (locale,))
            f.flush()
            f.close()

        # See Sabayon bug #2582
        system_font = self._anaconda.instLanguage.info.get("SYSFONT")
        if system_font is not None:
            consolefont_dir = ROOT_PATH + "/usr/share/consolefonts"
            system_font_path = os.path.join(consolefont_dir,
                system_font + ".psfu.gz")
            if os.path.isfile(system_font_path):
                self._setup_consolefont(system_font)

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
        self.remove_package('nvidia-drivers', silent = True)
        self.remove_package('nvidia-userspace', silent = True)

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
                question_text = "%s: %s" % (
                    _("An issue occured while installing"),
                    pkg_file,)
                buttons = [_("Meh.")]
                self._intf.messageWindow(_("Drivers installation issue"),
                    question_text, custom_icon="question", type="custom",
                    custom_buttons = buttons)

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
        ogl_script = """
            eselect opengl set xorg-x11 &> /dev/null
            eselect opengl set nvidia &> /dev/null
        """
        self.spawn_chroot(ogl_script)

    def env_update(self):
        self.spawn_chroot("env-update &> /dev/null")

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

    def language_packs_install(self):
        langpacks = []

        # some language packs are available for download
        # internet required, let's see if we should fetch them
        if self._anaconda.instLanguage.fullLanguageSupport:
            langpacks += self._get_installable_language_packs()

        if not langpacks and \
            not (self._anaconda.instLanguage.asianLanguageSupport):
            # nothing to install
            log.info("nothing to install by language_packs_install")
            return

        chroot = ROOT_PATH
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:

            action = _("Installing Language Packs")
            self._progress.set_label(action)

            # update repos
            done = self.update_entropy_repositories()
            if not done:
                log.warning(
                    "unable to update repositories for langpack install")
                return

            if self._anaconda.instLanguage.asianLanguageSupport:
                asian_langpacks = self._get_installable_asian_fonts()
                log.info("asian language install support enabled: %s" % (
                    asian_langpacks,))
                langpacks += asian_langpacks

            log.info("language packs install: %s" % (" ".join(langpacks),))

            lang_matches = [self._backend.entropy.atom_match(x) for x in langpacks]
            lang_matches = [x for x in lang_matches if x[0] != -1]
            if not lang_matches:
                log.warning(
                    "No language packs are available for download, sorry!")
                return

            # calculate deps, use relaxed algo
            try:
                queue_obj = self._backend.entropy.get_install_queue(lang_matches,
                    False, False, relaxed = True)
                if len(queue_obj) == 2:
                    install_queue, conflicts_queue = queue_obj
                else:
                    install_queue, conflicts_queue, status = queue_obj
                    if status == -2:
                        raise DependenciesNotFound(install_queue)
                    elif status == -3:
                        raise DependenciesCollision(install_queue)
            except (DependenciesCollision, DependenciesNotFound) as exc:
                log.warning(
                    "No language packs are available for install, %s, %s" % (
                        repr(exc), exc.value))
                return

            # fetch packages
            for match in install_queue:
                dbc = self._backend.entropy.open_repository(match[1])
                langpack = dbc.retrieveAtom(match[0])
                self._progress.set_text("%s: %s" % (
                    _("Downloading package"), langpack,))
                self.install_package(None, match = match, silent = True,
                    fetch = True)

            # install packages
            for match in install_queue:
                dbc = self._backend.entropy.open_repository(match[1])
                langpack = dbc.retrieveAtom(match[0])
                self._progress.set_text("%s: %s" % (
                    _("Installing package"), langpack,))
                self.install_package(None, match = match, silent = True)

        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def setup_entropy_mirrors(self):

        if not hasattr(self._backend.entropy, 'reorder_mirrors'):
            # Entropy version does not support it
            return
        # disable by default, pkg.sabayon.org was always selected
        # as first, causing massive bandwidth usage
        if not os.getenv('SABAYON_ENABLE_MIRROR_SORTING'):
            return

        self._progress.set_label("%s: %s" % (
            _("Reordering Entropy mirrors"), _("can take some time..."),))

        chroot = ROOT_PATH
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)
        try:
            self._backend.entropy.reorder_mirrors(REPO_NAME)
        except Exception as err:
            msg = "%s: %s" % (_("Error"), err)
            self._intf.messageWindow(_("Reordering Entropy mirrors"), msg,
                custom_icon="warning")
        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def update_entropy_repositories(self):

        settings = SystemSettings()
        chroot = ROOT_PATH
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        silent = True
        if os.getenv('SABAYON_DEBUG'):
            silent = False
        # XXX add stdout silence
        oldstdout = sys.stdout
        if silent:
            sys.stdout = STDERR_LOG
            set_mute(True)

        try:
            # fetch_security = False => avoid spamming stdout
            try:
                repo_intf = self._backend.entropy.Repositories(fetch_security = False,
                    entropy_updates_alert = False)
            except AttributeError:
                msg = "%s: %s" % (_('No repositories specified in'),
                    "repositories.conf",)
                self._intf.messageWindow(_("Repositories update"), msg,
                    custom_icon="warning")
                return False
            except Exception as e:
                msg = "%s: %s" % (_('Unhandled error'), e,)
                self._intf.messageWindow(_("Repositories update"), msg,
                    custom_icon="warning")
                return False

            try:
                update_rc = repo_intf.sync()
            except Exception as e:
                msg = "%s: %s" % (_('Sync error'), e,)
                self._intf.messageWindow(_("Repositories update"), msg,
                    custom_icon="warning")
                return False

            if repo_intf.sync_errors or (update_rc != 0):
                msg = _("Cannot download repositories right now, no big deal")
                self._intf.messageWindow(_("Repositories update"), msg,
                    custom_icon="warning")
                return False
            return True

        finally:

            if silent:
                sys.stdout = oldstdout
                set_mute(False)
            self._backend.entropy.close_repositories()
            settings.clear()
            if chroot != root:
                self._change_entropy_chroot(root)

    def _get_langpacks(self):
        return [x.strip() for x in LANGUAGE_PACKS.split("\n") if \
            (not x.strip().startswith("#")) and x.strip()]

    def __get_langs(self):
        def_lang = self._anaconda.instLanguage.instLang
        def_lang = def_lang.split(".")[0] # remove .UTF-8
        def_lang_2 = def_lang.split("_")[0]
        langs = [def_lang, def_lang_2]
        return set(langs)

    def _get_removable_localized_packages(self):
        langpacks = self._get_langpacks()
        # get cur lang
        langs = self.__get_langs()

        new_langpacks = set()
        for langpack in langpacks:
            found = False
            for lang in langs:
                if langpack.endswith("-%s" % (lang,)):
                    found = True
                    break
            if not found:
                new_langpacks.add(langpack)
        langpacks = new_langpacks

        client_repo = self._backend.entropy.installed_repository()
        for langpack in langpacks:
            matches, m_rc = client_repo.atomMatch(langpack, multiMatch = True)
            if m_rc != 0:
                continue
            for pkg_id in matches:
                valid = self._backend.entropy.validate_package_removal(pkg_id)
                if not valid:
                    continue
                yield pkg_id

    def _get_installable_asian_fonts(self):
        """
        This method must be called after having switched to install chroot.
        """
        packages = self._backend.entropy.packages_expand(ASIAN_FONTS_PACKAGES)
        if not packages:
            log.error("tried to expand asian fonts packages, got nothing!")
            return []

        client_repo = self._backend.entropy.installed_repository()

        def _pkg_filter(package):
            pkg_id, rc = client_repo.atomMatch(package)
            if pkg_id != -1:
                # already installed
                return False
            return True

        packages = list(filter(_pkg_filter, packages))
        if not packages:
            log.warning("all the required asian packages are already installed")
            return []

        log.info("got these asian packages to deal with: %s" % (
            " ".join(packages),))
        return packages

    def _get_installable_language_packs(self):
        """
        Return a list of packages not available on the CD/DVD that
        could be downloaded and installed.
        """
        langpacks = self._get_langpacks()
        # get cur lang
        langs = self.__get_langs()

        new_langpacks = set()
        for langpack in langpacks:
            found = False
            for lang in langs:
                if langpack.endswith("-%s" % (lang,)):
                    found = True
                    break
            if found:
                new_langpacks.add(langpack)
        langpacks = new_langpacks

        # filter out unwanted packages
        # see sabayon.const

        client_repo = self._backend.entropy.installed_repository()

        # KDE
        matches, m_rc = client_repo.atomMatch("kde-base/kdebase-startkde")
        if m_rc != 0:
            # remove kde* packages
            langpacks = [x for x in langpacks if x.find("kde") == -1]

        # Openoffice
        matches, m_rc = client_repo.atomMatch("openoffice")
        if m_rc != 0:
            # remove openoffice* packages
            langpacks = [x for x in langpacks if x.find("openoffice") == -1]

        # aspell
        matches, m_rc = client_repo.atomMatch("aspell")
        if m_rc != 0:
            # remove aspell* packages
            langpacks = [x for x in langpacks if x.find("aspell") == -1]

        # man-pages
        matches, m_rc = client_repo.atomMatch("man-pages")
        if m_rc != 0:
            # remove man-pages* packages
            langpacks = [x for x in langpacks if x.find("man-pages") == -1]

        packs = []
        for langpack in langpacks:
            matches, m_rc = client_repo.atomMatch(langpack)
            if m_rc != 0:
                packs.append(langpack)
        return packs

    def _setup_packages_to_remove(self):

        # remove anaconda if installed
        client_repo = self._backend.entropy.installed_repository()
        pkgs_rm = ["app-admin/anaconda", "app-misc/anaconda-runtime",
            "app-misc/anaconda-runtime-gui", "libselinux", "sys-process/audit"]
        for pkg_name in pkgs_rm:
            pkg_id, pkg_rc = client_repo.atomMatch(pkg_name)
            if pkg_id != -1:
                self._package_identifiers_to_remove.add(pkg_id)

        if not self._anaconda.instLanguage.fullLanguageSupport:
            localized_pkgs = self._get_removable_localized_packages()
            if localized_pkgs:
                self._package_identifiers_to_remove.update(localized_pkgs)
