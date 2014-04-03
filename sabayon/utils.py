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

# Entropy imports
from entropy.exceptions import EntropyPackageException, DependenciesNotFound, \
    DependenciesCollision
from entropy.const import etpConst, etpSys
try:
    from entropy.const import etpUi # Entropy 145
    is_mute, set_mute = None, None
except ImportError:
    etpUi = None
    from entropy.output import is_mute, set_mute
import entropy.tools
import entropy.dep
from entropy.core.settings.base import SystemSettings
from entropy.core import Singleton
from entropy.services.client import WebService

# Anaconda imports
import logging
from constants import productPath
from sabayon import Entropy
from sabayon.const import LIVE_USER, LANGUAGE_PACKS, REPO_NAME, \
    ASIAN_FONTS_PACKAGES, FIREWALL_SERVICE, SB_PRIVATE_KEY, \
    SB_PUBLIC_X509, SB_PUBLIC_DER

import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)

STDERR_LOG = open("/tmp/anaconda.log","aw")
log = logging.getLogger("anaconda")


def _set_mute(status):
    if etpUi is not None:
        etpUi['mute'] = status
    else:
        set_mute(status)


class SabayonProgress(Singleton):

    def init_singleton(self, anaconda):
        self._intf = anaconda.intf
        self._display_mode = anaconda.displayMode
        self._prog = self._intf.instProgress
        self.__updater = None
        self._pix_count = 0
        self.__alive = False
        self.__adbox_running = False
        self.__image_t = time.time()

    def _process_events(self):
        self._prog.processEvents()
        self._spawn_adimage()
        return self.__alive

    def start(self):
        self.__alive = True
        if (self.__updater is None) and (self._display_mode == "g"):
            self.__updater = glib.timeout_add(2000, self._process_events,
                priority = glib.PRIORITY_HIGH + 10)
        if self._display_mode == "g":
            self.__adbox_running = True

    def __kill_updater(self):
        if self.__updater is not None:
            glib.source_remove(self.__updater)
            self.__updater = None

    def stop(self):
        self.__kill_updater()
        self.__alive = False

    def progress(self):
        return self._prog

    def set_label(self, label):
        if self._display_mode == "g":
            def do_it():
                self._prog.set_label(label)
                return False
            glib.idle_add(do_it)
            self._process_events()
        else:
            self._prog.set_label(label)

    def set_text(self, text):
        if self._display_mode == "g":
            def do_it():
                self._prog.set_text(text)
                return False
            glib.idle_add(do_it)
            self._process_events()
        else:
            self._prog.set_text(text)

    def set_fraction(self, pct):

        if pct > 1.0:
            pct = 1.0
        elif pct < 0.0:
            pct = 0.0

        if self._display_mode == "g":
            def do_it(pct):
                self._prog.set_fraction(pct)
                return False
            glib.idle_add(do_it, pct)
            self._process_events()
        else:
            self._prog.set_fraction(pct)

    def _spawn_adimage(self):

        if not self.__adbox_running:
            return

        cur_t = time.time()
        if cur_t <= (self.__image_t + 10):
            return
        self.__image_t = cur_t

        pixmaps = getattr(self._prog, 'pixmaps', [])
        pix_len = len(pixmaps)
        if pix_len == 0:
            log.warning("Shutting down _spawn_adimage, no images")
            self.__adbox_running = False
            return

        if not self._prog.adpix:
            log.warning("Shutting down _spawn_adimage, no adpix")
            self.__adbox_running = False
            return

        try:
            pix_path = pixmaps[self._pix_count]
        except IndexError:
            self._pix_count = 0
            pix_path = pixmaps[0]

        self._pix_count += 1

        import gui
        pix = gui.readImageFromFile(pix_path)
        if pix:
            self._prog.adbox.remove(self._prog.adpix)
            self._prog.adpix.destroy()
            pix.set_alignment(0.5, 0.5)
            self._prog.adbox.add(pix)
            self._prog.adpix = pix
        else:
            log.warning("Shutting down _spawn_adimage, no pixmap: %s" % (
                pix_path,))

        self._prog.adbox.show_all()


class SabayonInstall:

    def __init__(self, anaconda):

        self._anaconda = anaconda
        self._root = anaconda.rootPath
        self._prod_root = productPath
        self._intf = anaconda.intf
        self._progress = SabayonProgress(anaconda)
        self._entropy = Entropy()
        self._settings = SystemSettings()
        with open("/proc/cmdline", "r") as cmd_f:
            self.cmdline = cmd_f.readline().strip().split()
        #sys.stderr = STDERR_LOG

        self._files_db_path = self._root+"/files.db"
        try:
            self._files_db = self._entropy.open_generic_repository(
                 self._files_db_path, dbname = "filesdb",
                indexing_override = True)
        except TypeError:
            # new API
            self._files_db = self._entropy.open_generic_repository(
                 self._files_db_path, name = "filesdb",
                indexing_override = True)
        if hasattr(self._files_db, "initializeDatabase"):
            self._files_db.initializeDatabase()
        else:
            self._files_db.initializeRepository()
        self._live_repo = self._open_live_installed_repository()
        self._package_identifiers_to_remove = set()

    def destroy(self):
        # remove files db if exists
        if hasattr(self._files_db, "close"):
            self._files_db.close()
        else:
            self._files_db.closeDB()
        try:
            os.remove(self._files_db_path)
        except OSError:
            pass

        self._progress.stop()

    def spawn_chroot(self, args, silent = False):

        pid = os.fork()
        if pid == 0:

            os.chroot(self._root)
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
        dbpath = self._prod_root + etpConst['etpdatabaseclientfilepath']
        try:
            dbconn = self._entropy.open_generic_repository(
                dbpath, xcache = False, read_only = True,
                dbname = "live_client", indexing_override = False)
        except TypeError:
            # new API
            dbconn = self._entropy.open_generic_repository(
                dbpath, xcache = False, read_only = True,
                name = "live_client", indexing_override = False)
        return dbconn

    def _change_entropy_chroot(self, chroot = None):
        if not chroot:
            self._entropy._installed_repo_enable = True
            self._entropy.noclientdb = False
        else:
            self._entropy._installed_repo_enable = False
            self._entropy.noclientdb = True
        if chroot is None:
            chroot = ""
        self._entropy.switch_chroot(chroot)

    def install_package(self, atom, match = None, silent = False, fetch = False):

        if silent and os.getenv('SABAYON_DEBUG'):
            silent = False

        chroot = self._root
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        if match is None:
            match = self._entropy.atom_match(atom)

        oldstdout = sys.stdout
        if silent:
            sys.stdout = STDERR_LOG
            _set_mute(True)

        try:
            action_factory = self._entropy.PackageActionFactory()
            install_action = action_factory.INSTALL_ACTION
            fetch_action = action_factory.FETCH_ACTION
        except AttributeError:
            action_factory = None
            install_action = "install"
            fetch_action = "fetch"

        try:
            rc = 0
            if match[0] != -1:

                action = install_action
                if fetch:
                    action = fetch_action

                if action_factory is not None:
                    pkg = action_factory.get(
                        action, match)
                    rc = pkg.start()
                    pkg.finalize()

                else:
                    pkg = self._entropy.Package()
                    pkg.prepare(match, action)
                    rc = pkg.run()
                    pkg.kill()

        finally:
            if silent:
                sys.stdout = oldstdout
                _set_mute(False)
            if chroot != root:
                self._change_entropy_chroot(root)

        return rc

    def remove_package(self, atom, match = None, silent = False):

        if silent and os.getenv('SABAYON_DEBUG'):
            silent = False

        chroot = self._root
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        inst_repo = self._entropy.installed_repository()
        if match is None:
            match = inst_repo.atomMatch(atom)

        oldstdout = sys.stdout
        if silent:
            sys.stdout = STDERR_LOG
            _set_mute(True)

        try:
            action_factory = self._entropy.PackageActionFactory()
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
                    pkg = self._entropy.Package()
                    pkg.prepare((match[0],), "remove")
                    if 'remove_installed_vanished' not in pkg.pkgmeta:
                        rc = pkg.run()
                        pkg.kill()

        finally:
            if silent:
                sys.stdout = oldstdout
                _set_mute(False)

        if chroot != root:
            self._change_entropy_chroot(root)

        return rc

    def install_package_file(self, package_file):
        chroot = self._root
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:
            atomsfound = self._entropy.add_package_repository(
                package_file)
        except EntropyPackageException:
            return -1

        try:
            action_factory = self._entropy.PackageActionFactory()
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
                pkg = self._entropy.Package()
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
            self._entropy.remove_repository(repo)

        return 0

    def _configure_steambox(self):

        steambox_user_file = self._root + "/etc/sabayon/steambox-user"
        steambox_user_dir = os.path.dirname(steambox_user_file)
        if not os.path.isdir(steambox_user_dir):
            os.makedirs(steambox_user_dir, 0755)

        steambox_user = self._anaconda.users.otherUsers[LIVE_USER]['username']
        with open(steambox_user_file, "w") as f:
            f.write(steambox_user)

    def _configure_skel(self):

        # copy Rigo on the desktop
        rigo_desktop = self._root+"/usr/share/applications/rigo.desktop"
        if os.path.isfile(rigo_desktop):
            rigo_user_desktop = self._root+"/etc/skel/Desktop/rigo.desktop"
            shutil.copy2(rigo_desktop, rigo_user_desktop)
            try:
                os.chmod(rigo_user_desktop, 0775)
            except OSError:
                pass

        gparted_desktop = self._root+"/etc/skel/Desktop/gparted.desktop"
        if os.path.isfile(gparted_desktop):
            os.remove(gparted_desktop)

        installer_desk = self._root+"/etc/skel/Desktop/liveinst.desktop"
        if os.path.isfile(installer_desk):
            os.remove(installer_desk)

        # install welcome loader
        orig_welcome_desk = self._root+"/etc/sabayon/sabayon-welcome-loader.desktop"
        if os.path.isfile(orig_welcome_desk):
            autostart_dir = self._root+"/etc/skel/.config/autostart"
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
        custom_gdm = os.path.join(self._root, "etc/gdm/custom.conf")
        skel_dmrc = os.path.join(self._root, "etc/skel/.dmrc")
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
        install_data_dir = os.path.join(self._root, "install-data")
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

            udev_bl = self._root + "/etc/modprobe.d/bbswitch-blacklist.conf"
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

    def setup_users(self):

        # configure .desktop files on Desktop
        self._configure_skel()

        # configure steambox user
        self._configure_steambox()

        # remove live user and its home dir
        pid = os.fork()
        if pid > 0:
            os.waitpid(pid, 0)
        else:
            os.chroot(self._root)
            # backward compat
            proc = subprocess.Popen(("userdel", "-f", "-r", LIVE_USER),
                stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            os._exit(proc.wait())

        # fixup root password
        # see bug #2175
        pid = os.fork()
        if pid > 0:
            os.waitpid(pid, 0)
        else:
            os.chroot(self._root)
            root_pass = self._anaconda.users.rootPassword["password"]
            root_str = "root:%s\n" % (root_pass,)
            proc = subprocess.Popen(["chpasswd"],
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            proc.stdin.write(root_str)
            proc.stdin.close()
            os._exit(proc.wait())

    def setup_manual_networking(self):
        # TODO: check if we need this with systemd. I'd say no.
        # systemctl --no-reload disable NetworkManager.service
        # systemctl --no-reload disable NetworkManager-wait-online.service
        pass

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
            self._root, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s kde &> /dev/null" % (
            self._root, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s lxde &> /dev/null" % (
            self._root, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s e17 &> /dev/null" % (
            self._root, keylayout))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 \"%s\" \"%s\" \"%s\" xorg &> /dev/null" % (
            self._root, xorglayout, variant, options))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s system &> /dev/null" % (
            self._root, console_kbd))
        _spawn("ROOT=%s /sbin/keyboard-setup-2 %s xfce &> /dev/null" % (
            self._root, console_kbd))

    def setup_sudo(self):
        sudoers_file = self._root + '/etc/sudoers'
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
        private = self._root + SB_PRIVATE_KEY
        public = self._root + SB_PUBLIC_X509
        der = self._root + SB_PUBLIC_DER

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
            asound_state_dest_dir = os.path.dirname(self._root+asound_state)
            asound_state_dest_dir2 = os.path.dirname(self._root+asound_state2)

            if not os.path.isdir(asound_state_dest_dir):
                os.makedirs(asound_state_dest_dir, 0755)

            if not os.path.isdir(asound_state_dest_dir2):
                os.makedirs(asound_state_dest_dir2, 0755)

            source_f = open(asound_state, "r")
            dest_f = open(self._root+asound_state, "w")
            dest2_f = open(self._root+asound_state2, "w")
            asound_data = source_f.readlines()
            dest_f.writelines(asound_data)
            dest2_f.writelines(asound_data)
            dest_f.flush()
            dest_f.close()
            dest2_f.flush()
            dest2_f.close()
            source_f.close()

    def setup_xorg(self):
        # Copy current xorg.conf
        live_xorg_conf = "/etc/X11/xorg.conf"
        if not os.path.isfile(live_xorg_conf):
            return
        xorg_conf = self._root + live_xorg_conf
        shutil.copy2(live_xorg_conf, xorg_conf)
        shutil.copy2(live_xorg_conf, xorg_conf+".original")

    def _setup_consolefont(self, system_font):
        # /etc/vconsole.conf support
        vconsole_conf = self._root + "/etc/vconsole.conf"
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

        with open(self._root + "/etc/env.d/02locale", "w") as f:
            for key in info.keys():
                if info[key] is not None:
                    f.write("%s=\"%s\"\n" % (key, info[key]))
            f.flush()

        # systemd support, same syntax as 02locale for now
        with open(self._root + "/etc/locale.conf", "w") as f:
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

            f = open(self._root + "/etc/locale.gen", "w")
            f.write("en_US.UTF-8 UTF-8\n")
            f.write("en_US ISO-8859-1\n")
            for locale in valid_locales:
                f.write("%s\n" % (locale,))
            f.flush()
            f.close()

        # See Sabayon bug #2582
        system_font = self._anaconda.instLanguage.info.get("SYSFONT")
        if system_font is not None:
            consolefont_dir = self._root + "/usr/share/consolefonts"
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
                self._root + "/", pkg_file)
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
            mask_file = os.path.join(self._root+'/',
                "etc/entropy/packages/package.mask")
            unmask_file = os.path.join(self._root+'/',
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
        factory = self._entropy.WebServices()
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

    def live_install(self):
        """
        This function copy the LiveCD/DVD content into self._root
        """

        if not os.getenv("SABAYON_DISABLE_PKG_REMOVAL"):
            self._setup_packages_to_remove()

        action = _("System Installation")
        copy_update_interval = 300
        copy_update_counter = 299
        # get file counters
        total_files = 0
        image_dir = self._prod_root
        for z,z,files in os.walk(image_dir):
            for file in files:
                total_files += 1

        self._progress.set_fraction(0.0)
        self._progress.set_text(action)

        def copy_other(fromfile, tofile):
            proc = subprocess.Popen(("/bin/cp", "-a", fromfile, tofile),
                stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            proc.wait()
            del proc

        def copy_reg(fromfile, tofile):
            try:
                shutil.copy2(fromfile, tofile)
                user = os.stat(fromfile)[4]
                group = os.stat(fromfile)[5]
                os.chown(tofile, user, group)
                shutil.copystat(fromfile, tofile)
            except IOError, e:
                if (e[0] == 40) or (e[0] == 2):
                    # workaround for Too many levels of symbolic links
                    copy_other(fromfile, tofile)
                else:
                    raise

        def copy_lnk(fromfile, tofile):
            source_link = os.readlink(fromfile)
            if os.path.lexists(tofile):
                os.remove(tofile)
            os.symlink(source_link, tofile)

        current_counter = 0
        currentfile = "/"
        image_dir_len = len(image_dir)
        # Create the directory structure
        # self.InstallFilesToIgnore
        for currentdir, subdirs, files in os.walk(image_dir):

            copy_update_counter += 1
            to_currentdir = currentdir[image_dir_len:]
            for t_dir in ("/proc", "/dev", "/sys"):
                if to_currentdir.startswith(t_dir):
                    # don't touch subdirs
                    subdirs = []
                    break

            for xdir in subdirs:

                image_path_dir = currentdir + "/" + xdir
                mydir = image_path_dir[image_dir_len:]
                rootdir = self._root + mydir

                # handle broken symlinks
                if os.path.islink(rootdir) and not os.path.exists(rootdir):
                    # broken symlink
                    os.remove(rootdir)

                # if our directory is a file on the live system
                elif os.path.isfile(rootdir): # really weird...!
                    os.remove(rootdir)

                # if our directory is a symlink instead, then copy the symlink
                if os.path.islink(image_path_dir) and not os.path.isdir(rootdir):
                    # for security we skip live items that are dirs
                    tolink = os.readlink(image_path_dir)
                    if os.path.islink(rootdir):
                        os.remove(rootdir)
                    os.symlink(tolink,rootdir)
                elif (not os.path.isdir(rootdir)) and \
                    (not os.access(rootdir,os.R_OK)):
                    os.makedirs(rootdir)

                if not os.path.islink(rootdir):
                    # symlink don't need permissions, also until os.walk
                    # ends they might be broken
                    user = os.stat(image_path_dir)[4]
                    group = os.stat(image_path_dir)[5]
                    os.chown(rootdir,user,group)
                    shutil.copystat(image_path_dir,rootdir)

            files.sort()
            for path_file in files:

                current_counter += 1
                fromfile = currentdir + "/" + path_file
                currentfile = fromfile[image_dir_len:]

                if currentfile.startswith("/dev/"):
                    continue
                if currentfile.startswith("/proc/"):
                    continue
                if currentfile.startswith("/sys/"):
                    continue

                try:
                    # if file is in the ignore list
                    if self._files_db.isFileAvailable(
                        currentfile.decode('raw_unicode_escape')):
                        continue
                except:
                    import traceback
                    traceback.print_exc()

                tofile = self._root + currentfile
                st_info = os.lstat(fromfile)
                if stat.S_ISREG(st_info[stat.ST_MODE]):
                    copy_reg(fromfile, tofile)
                elif stat.S_ISLNK(st_info[stat.ST_MODE]):
                    copy_lnk(fromfile, tofile)
                else:
                    copy_other(fromfile, tofile)


            if (copy_update_counter == copy_update_interval) or \
                ((total_files - 1000) < current_counter):
                # do that every 1000 iterations
                copy_update_counter = 0
                frac = float(current_counter)/total_files
                self._progress.set_fraction(frac)

        self._progress.set_fraction(1)

        self._change_entropy_chroot(self._root)
        # doing here, because client_repo should point to self._root chroot
        client_repo = self._entropy.installed_repository()
        # Removing Unwanted Packages
        if self._package_identifiers_to_remove:

            # this makes packages removal much faster
            client_repo.createAllIndexes()

            total_counter = len(self._package_identifiers_to_remove)
            current_counter = 0
            self._progress.set_fraction(current_counter)
            self._progress.set_text(_("Cleaning packages"))
            self._entropy.oldcount = [0,total_counter]

            for pkg_id in self._package_identifiers_to_remove:
                current_counter += 1
                atom = client_repo.retrieveAtom(pkg_id)
                if not atom:
                    continue

                ### XXX needed to speed up removal process
                #"""
                category = client_repo.retrieveCategory(pkg_id)
                version = client_repo.retrieveVersion(pkg_id)
                name = client_repo.retrieveName(pkg_id)
                ebuild_path = self._root+"/var/db/pkg/%s/%s-%s" % (
                    category, name, version)
                if os.path.isdir(ebuild_path):
                    shutil.rmtree(ebuild_path, True)
                #"""
                ### XXX

                self.remove_package(None, match = (pkg_id,0), silent = True)
                frac = float(current_counter)/total_counter
                self._progress.set_fraction(frac)
                self._progress.set_text("%s: %s" % (
                    _("Cleaning package"), atom,))
                self._entropy.oldcount = [current_counter, total_counter]

        while 1:
            change = False
            mydirs = set()
            try:
                mydirs = self._files_db.retrieveContent(None, contentType = "dir")
            except TypeError:
                mydirs = set([x for x, y in self._files_db.retrieveContent(None,
                    extended = True) if y == "dir"])
            for mydir in mydirs:
                mytree = os.path.join(self._root,mydir)
                if os.path.isdir(mytree) and not client_repo.isFileAvailable(
                    mydir):
                    try:
                        os.rmdir(mytree)
                        change = True
                    except OSError:
                        pass
            if not change:
                break

        # list installed packages and setup a package set
        inst_packages = ['%s:%s\n' % (entropy.dep.dep_getkey(atom),slot,) \
            for idpk, atom, slot, revision in client_repo.listAllPackages(
                get_scope = True, order_by = "atom")]
        # perfectly fine w/o self._root
        pkgset_dir = SystemSettings.packages_sets_directory()
        if not os.path.isdir(pkgset_dir):
            os.makedirs(pkgset_dir, 0755)
        set_name = "install_base"
        set_filepath = os.path.join(pkgset_dir, set_name)
        try:
            f = open(set_filepath,"w")
            f.writelines(inst_packages)
            f.flush()
            f.close()
        except (IOError,):
            pass

        self._change_entropy_chroot()

        self._progress.set_fraction(1)
        self._progress.set_text(_("Installation complete"))

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

        chroot = self._root
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        try:

            action = _("Installing Language Packs")
            self._progress.set_label(action)
            self._progress.set_fraction(0.85)

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

            lang_matches = [self._entropy.atom_match(x) for x in langpacks]
            lang_matches = [x for x in lang_matches if x[0] != -1]
            if not lang_matches:
                log.warning(
                    "No language packs are available for download, sorry!")
                return

            # calculate deps, use relaxed algo
            try:
                queue_obj = self._entropy.get_install_queue(lang_matches,
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
                dbc = self._entropy.open_repository(match[1])
                langpack = dbc.retrieveAtom(match[0])
                self._progress.set_text("%s: %s" % (
                    _("Downloading package"), langpack,))
                self.install_package(None, match = match, silent = True,
                    fetch = True)

            # install packages
            for match in install_queue:
                dbc = self._entropy.open_repository(match[1])
                langpack = dbc.retrieveAtom(match[0])
                self._progress.set_text("%s: %s" % (
                    _("Installing package"), langpack,))
                self.install_package(None, match = match, silent = True)

        finally:
            if chroot != root:
                self._change_entropy_chroot(root)
            self._progress.set_fraction(0.9)

    def setup_entropy_mirrors(self):

        if not hasattr(self._entropy, 'reorder_mirrors'):
            # Entropy version does not support it
            return
        # disable by default, pkg.sabayon.org was always selected
        # as first, causing massive bandwidth usage
        if not os.getenv('SABAYON_ENABLE_MIRROR_SORTING'):
            return

        self._progress.set_label("%s: %s" % (
            _("Reordering Entropy mirrors"), _("can take some time..."),))

        chroot = self._root
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)
        try:
            self._entropy.reorder_mirrors(REPO_NAME)
        except Exception as err:
            msg = "%s: %s" % (_("Error"), err)
            self._intf.messageWindow(_("Reordering Entropy mirrors"), msg,
                custom_icon="warning")
        finally:
            if chroot != root:
                self._change_entropy_chroot(root)

    def update_entropy_repositories(self):

        chroot = self._root
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
            _set_mute(True)

        try:
            # fetch_security = False => avoid spamming stdout
            try:
                repo_intf = self._entropy.Repositories(fetch_security = False,
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
                _set_mute(False)
            self._entropy.close_repositories()
            self._settings.clear()
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

        client_repo = self._entropy.installed_repository()
        for langpack in langpacks:
            matches, m_rc = client_repo.atomMatch(langpack, multiMatch = True)
            if m_rc != 0:
                continue
            for pkg_id in matches:
                valid = self._entropy.validate_package_removal(pkg_id)
                if not valid:
                    continue
                yield pkg_id

    def _get_installable_asian_fonts(self):
        """
        This method must be called after having switched to install chroot.
        """
        packages = self._entropy.packages_expand(ASIAN_FONTS_PACKAGES)
        if not packages:
            log.error("tried to expand asian fonts packages, got nothing!")
            return []

        client_repo = self._entropy.installed_repository()

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

        client_repo = self._entropy.installed_repository()

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
        client_repo = self._entropy.installed_repository()
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

        if self._package_identifiers_to_remove:

            current_counter = 0
            total_counter = len(self._package_identifiers_to_remove)
            self._progress.set_fraction(current_counter)
            self._progress.set_text(_("Generating list of files to copy"))

            for pkg in self._package_identifiers_to_remove:
                current_counter += 1
                self._progress.set_fraction(
                    float(current_counter)/total_counter)
                # get its files
                mycontent = self._live_repo.retrieveContent(pkg,
                    extended = True)
                mydirs = [x[0] for x in mycontent if x[1] == "dir"]
                for x in mydirs:
                    if x.find("/usr/lib64") != -1:
                        x = x.replace("/usr/lib64","/usr/lib")
                    elif x.find("/lib64") != -1:
                        x = x.replace("/lib64","/lib")
                    self._add_file_to_ignore(x, "dir")
                mycontent = [x[0] for x in mycontent if x[1] == "obj"]
                for x in mycontent:
                    if x.find("/usr/lib64") != -1:
                        x = x.replace("/usr/lib64","/usr/lib")
                    elif x.find("/lib64") != -1:
                        x = x.replace("/lib64","/lib")
                    self._add_file_to_ignore(x, "obj")
                del mycontent

            self._progress.set_fraction(1)

        if hasattr(self._files_db, "commit"):
            self._files_db.commit()
        else:
            self._files_db.commitChanges()
        if hasattr(self._files_db, "setIndexing"):
            self._files_db.setIndexing(True)
        else:
            self._files_db.indexing = True
        self._files_db.createAllIndexes()

    def _add_file_to_ignore(self, f_path, ctype):
        self._files_db._cursor().execute(
            'INSERT into content VALUES (?,?,?)' , ( None, f_path, ctype, ))
