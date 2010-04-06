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
import commands
import shutil
import statvfs

# Entropy imports
from entropy.const import etpUi, etpConst, etpSys
import entropy.tools
from entropy.misc import TimeScheduled
from entropy.core.settings.base import SystemSettings
from entropy.core import Singleton

# Anaconda imports
import logging
from constants import productPath
from sabayon import Entropy
from sabayon.const import LIVE_USER, LANGUAGE_PACKS

import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)

STDERR_LOG = open("/tmp/anaconda.log","aw")
log = logging.getLogger("anaconda")

class SabayonProgress(Singleton):

    def init_singleton(self, anaconda):
        self._intf = anaconda.intf
        self._prog = self._intf.instProgress
        self.__updater = None
        self._pix_count = 0

    def start(self):
        if self.__updater is None:
            self.__updater = TimeScheduled(2, self._prog.processEvents)
            self.__updater.start()

    def stop(self):
        if self.__updater is not None:
            self.__updater.kill()
            self.__updater.join()

    def progress(self):
        return self._prog

    def set_label(self, label):
        def do_it():
            self._prog.set_label(label)
            return False
        glib.timeout_add(0, do_it)

    def set_text(self, text):
        def do_it():
            self._prog.set_text(text)
            return False
        glib.timeout_add(0, do_it)

    def set_fraction(self, pct):
        def do_it():
            self._prog.set_fraction(pct)
            return False
        glib.timeout_add(0, do_it)

    def spawn_adimage(self):
        pixmaps = getattr(self._prog, 'pixmaps', [])
        pix_len = len(pixmaps)
        if pix_len == 0:
            return

        if not self._prog.adpix:
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
            self._cmdline = cmd_f.readline().strip().split()
        #sys.stderr = STDERR_LOG

        self.__start_system_health_check()

        self._files_db_path = self._root+"/files.db"
        self._files_db = self._entropy.open_generic_repository(
             self._files_db_path, dbname = "filesdb",
            indexing_override = True)
        self._files_db.initializeDatabase()
        self._live_repo = self._open_live_installed_repository()
        self._package_identifiers_to_remove = set()

    def destroy(self):
        # remove files db if exists
        self._files_db.closeDB()
        try:
            os.remove(self._files_db_path)
        except OSError:
            pass

        if self.__sys_health_checker != None:
            self.__sys_health_checker.kill()
            self.__sys_health_checker.join()

    def __start_system_health_check(self):
        self.__health_msg = ''
        self.__sys_health_warn_shown = False
        self.__sys_health_checker = TimeScheduled(30, self.__health_check)
        self.__sys_health_checker.start()

    def __health_check(self):
        if self.__sys_health_warn_shown:
            self.__sys_health_checker.kill()
            return

        kern_msg_out = commands.getoutput("dmesg -s 1024000")
        data = [x for x in kern_msg_out.split("\n") if \
            x.find("SQUASHFS error") != -1]

        if data:
            self.__health_msg = data[0].strip()
            self._intf.messageWindow(
                _("System Health Status Warning"),
                "Your system is having HARDWARE issues, "
                "continue at your risk, error: %s" % (self.__health_msg,),
                custom_icon="error")
            self.__sys_health_warn_shown = True

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
        dbconn = self._entropy.open_generic_repository(
            dbfile = dbpath, xcache = False, readOnly = True,
            dbname = "live_client", indexing_override = False)
        return dbconn

    def _change_entropy_chroot(self, chroot = None):
        if not chroot:
            self._entropy.noclientdb = False
            etpUi['nolog'] = True
        else:
            self._entropy.noclientdb = True
            etpUi['nolog'] = False
        self._entropy.switch_chroot(chroot)
        sys_settings_plg_id = etpConst['system_settings_plugins_ids']['client_plugin']
        del self._settings[sys_settings_plg_id]['misc']['configprotectskip'][:]

    def remove_package(self, atom, match = None, silent = False):

        chroot = self._root
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        if match is None:
            match = self._entropy.installed_repository().atomMatch(atom)

        oldstdout = sys.stdout
        if silent:
            sys.stdout = STDERR_LOG

        try:
            rc = 0
            if match[0] != -1:
                Package = self._entropy.Package()
                Package.prepare((match[0],),"remove")
                if not Package.pkgmeta.has_key('remove_installed_vanished'):
                    rc = Package.run()
                    Package.kill()
        finally:
            if silent:
                sys.stdout = oldstdout

        if chroot != root:
            self._change_entropy_chroot(root)

        return rc

    def insall_package_file(self, package_file):
        chroot = self._root
        root = etpSys['rootdir']
        if chroot != root:
            self._change_entropy_chroot(chroot)

        rc, atomsfound = self._entropy.add_package_to_repositories(
            package_file)
        repo = 0
        if rc != 0:
            return rc
        for match in atomsfound:
            repo = match[1]
            Package = self._entropy.Package()
            Package.prepare(match,"install")
            rc2 = Package.run()
            if rc2 != 0:
                if chroot != root:
                    self._change_entropy_chroot(root)
                return rc2
            Package.kill()

        if chroot != root:
            self._change_entropy_chroot(root)

        if repo != 0:
            self._entropy.remove_repository(repo)

        return 0

    def _configure_skel(self):

        # copy Sulfur on the desktop
        sulfur_desktop = self._root+"/usr/share/applications/sulfur.desktop"
        if os.path.isfile(sulfur_desktop):
            sulfur_user_desktop = self._root+"/etc/skel/Desktop/sulfur.desktop"
            shutil.copy2(sulfur_desktop, sulfur_user_desktop)
            try:
                os.chmod(sulfur_user_desktop, 0775)
            except OSError:
                pass

        gparted_desktop = self._root+"/etc/skel/Desktop/gparted.desktop"
        if os.path.isfile(gparted_desktop):
            os.remove(gparted_desktop)

        installer_desk = self._root+"/etc/skel/Desktop/Anaconda Installer.desktop"
        if os.path.isfile(installer_desk):
            os.remove(installer_desk)

    def _is_encrypted(self):
        if self._anaconda.storage.encryptionPassphrase:
            return True
        return False

    def configure_services(self):

        action = _("Configuring System Services")
        self._progress.set_text(action)

        # Remove Installer services
        config_script = """
            rc-update del installer-gui boot default
            rm -f /etc/init.d/installer-gui
            rc-update del installer-text boot default
            rm -f /etc/init.d/installer-text
            rc-update del music boot default
            rm -f /etc/init.d/music
            rc-update del sabayonlive boot default
            rm -f /etc/init.d/sabayonlive
            rc-update add vixie-cron default
            if [ ! -e "/etc/init.d/net.eth0" ]; then
                cd /etc/init.d && ln -s net.lo net.eth0
            fi
            if [ -e "/etc/init.d/nfsmount" ]; then
                rc-update add nfsmount default
            fi
        """
        self.spawn_chroot(config_script, silent = True)

        # setup dmcrypt service if user enabled encryption
        if self._is_encrypted():
            self.spawn_chroot("rc-update add dmcrypt boot", silent = True)

        # Copy the kernel modules blacklist configuration file
        if os.access("/etc/modules.d/blacklist",os.F_OK):
            self.spawn(
                "cp -p /etc/modules.d/blacklist %s/etc/modules.d/blacklist" % (
                    self._root,))

    def remove_proprietary_drivers(self):
        """
        Detect a possible OSS video card and remove /etc/env.d/*ati
        """
        if self._get_opengl() == "xorg-x11":
            ogl_script = """
                rm -f /etc/env.d/09ati
                rm -rf /usr/lib/opengl/ati
                rm -rf /usr/lib/opengl/nvidia
            """
            self.spawn_chroot(ogl_script)
            self.remove_package('ati-drivers', silent = True)
            self.remove_package('nvidia-settings', silent = True)
            self.remove_package('nvidia-drivers', silent = True)

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

        # remove live user and its home dir
        pid = os.fork()
        if pid > 0:
            os.waitpid(pid, 0)
        else:
            os.chroot(self._root)
            proc = subprocess.Popen(("userdel", "-f", "-r", LIVE_USER),
                stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            os._exit(proc.wait())

    def setup_manual_networking(self):
        mn_script = """
            rc-update del NetworkManager default
            rc-update del avahi-daemon default
            rc-update del dhcdbd default
            if [ -f "/etc/rc.conf" ]; then
                sed -i 's/^#rc_hotplug=".*"/rc_hotplug="*"/g' /etc/rc.conf
                sed -i 's/^rc_hotplug=".*"/rc_hotplug="*"/g' /etc/rc.conf
            fi
        """
        self.spawn_chroot(mn_script, silent = True)

    def setup_sudo(self):
        sudoers_file = self._root + '/etc/sudoers'
        if os.path.isfile(sudoers_file):
            self.spawn("sed -i '/NOPASSWD/ s/^/#/' %s" % (sudoers_file,))
            with open(sudoers_file, "a") as sudo_f:
                sudo_f.write("\n#Added by Sabayon Installer\n%wheel  ALL=ALL\n")
                sudo_f.flush()

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
        xorg_conf = self._root + live_xorg_conf
        shutil.copy2(live_xorg_conf, xorg_conf)
        shutil.copy2(live_xorg_conf, xorg_conf+".original")

    def setup_dev(self):
        # @deprecated
        # Copy /dev from DVD to HD
        # required even in baselayout-2
        os.system("mkdir /tmp/dev-move "+REDIRECT_OUTPUT+" ; mount --move "+self._root+"/dev /tmp/dev-move &> /dev/null")
        os.system("cp /dev/* "+self._root+"/dev/ -Rp &> /dev/null")
        os.system("cp /dev/.u* "+self._root+"/dev/ -Rp &> /dev/null")
        os.system("mount --move /tmp/dev-move "+self._root+"/dev &> /dev/null")

    def setup_misc_language(self):
        # Prepare locale variables
        localization = self._anaconda.instLanguage.instLang.split(".")[0]
        # Configure KDE language
        if os.path.isfile(self._root + "/sbin/language-setup"):
            self.spawn_chroot(("/sbin/language-setup", localization, "kde"),
                silent = True)
            self.spawn_chroot(("/sbin/language-setup", localization, "openoffice"),
                silent = True)
            self.spawn_chroot(("/sbin/language-setup", localization, "mozilla"),
                silent = True)

    def setup_nvidia_legacy(self):

        # Configure NVIDIA legacy drivers, if needed
        running_file = "/lib/nvidia/legacy/running"
        drivers_dir = "/install-data/drivers"
        if not os.path.isfile(running_file):
            return
        if not os.path.isdir(drivers_dir):
            return

        f = open(running_file)
        nv_ver = f.readline().strip()
        f.close()

        if nv_ver.find("17x.xx.xx") != -1:
            nv_ver = "17"
        elif nv_ver.find("9x.xx") != -1:
            nv_ver = "9"
        else:
            nv_ver = "7"

        legacy_unmask_map = {
            "7": "=x11-drivers/nvidia-drivers-7*",
            "9": "=x11-drivers/nvidia-drivers-9*",
            "17": "=x11-drivers/nvidia-drivers-17*"
        }

        self.remove_package('nvidia-drivers')
        for pkg_file in os.listdir(drivers_dir):

            if not pkg_file.startswith("x11-drivers:nvidia-drivers-"+nv_ver):
                continue

            pkg_filepath = os.path.join(drivers_dir, pkg_file)
            try:
                shutil.copy2(pkg_filepath, self._root+"/")
            except:
                continue

            rc = self.insall_package_file(self._root+'/'+pkg_file)

            # mask all the nvidia-drivers, this avoids having people
            # updating their drivers resulting in a non working system
            mask_file = os.path.join(self._root+'/',"etc/entropy/packages/package.mask")
            unmask_file = os.path.join(self._root+'/',"etc/entropy/packages/package.unmask")
            if os.access(mask_file, os.W_OK) and os.path.isfile(mask_file):
                f = open(mask_file,"aw")
                f.write("\n# added by Sabayon Installer\nx11-drivers/nvidia-drivers\n")
                f.flush()
                f.close()
            if os.access(unmask_file, os.W_OK) and os.path.isfile(unmask_file):
                f = open(unmask_file,"aw")
                f.write("\n# added by Sabayon Installer\n%s\n" % (
                    legacy_unmask_map[nv_ver],))
                f.flush()
                f.close()

            if rc != 0:
                question_text = "%s: %s" % (
                    _("An issue occured while installing"),
                    pkg_file,)
                buttons = [_("Meh.")]
                self._intf.messageWindow(_("Drivers installation issue"),
                    question_text, custom_icon="question", type="custom",
                    custom_buttons = buttons)

        # force OpenGL reconfiguration
        ogl_script = """
            eselect opengl set xorg-x11 &> /dev/null
            eselect opengl set nvidia &> /dev/null
        """
        self.spawn_chroot(ogl_script)

    def env_update(self):
        self.spawn_chroot("env-update &> /dev/null")

    def emit_install_done(self):
        # user installed Sabayon, w00hooh!
        try:
            self._entropy.UGC.add_download_stats("sabayonlinux.org",
                ["installer"])
        except Exception as err:
            log.error("Unable to emit_install_done(): %s" % err) 

    def live_install(self):
        """
        This function copy the LiveCD/DVD content into self._root
        """

        self._setup_packages_to_remove()

        action = _("System Installation")
        client_repo = self._entropy.installed_repository()
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
            os.symlink(source_link, tofile)

        current_counter = 0
        currentfile = "/"
        image_dir_len = len(image_dir)
        # Create the directory structure
        # self.InstallFilesToIgnore
        for currentdir, subdirs, files in os.walk(image_dir):

            copy_update_counter += 1

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

            for path_file in sorted(files):

                current_counter += 1
                fromfile = currentdir + "/" + path_file
                currentfile = fromfile[image_dir_len:]

                # @deprecated
                #if currentfile.startswith("/dev"):
                #    continue
                elif currentfile == "/boot/grub/grub.conf":
                    continue
                elif currentfile == "/boot/grub/grub.cfg":
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
                frac = float(current_counter)/total_files*100
                self._progress.set_fraction(frac)

        self._progress.set_fraction(100.0)

        self._change_entropy_chroot(self._root)
        # Removing Unwanted Packages
        if self._package_identifiers_to_remove:

            # this makes packages removal much faster
            client_repo.indexing = True
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
                """
                category = client_repo.retrieveCategory(pkg_id)
                version = client_repo.retrieveVersion(pkg_id)
                name = client_repo.retrieveName(pkg_id)
                ebuild_path = self._root+"/var/db/pkg/%s/%s-%s" % (
                    category, name, version)
                if os.path.isdir(ebuild_path):
                    shutil.rmtree(ebuild_path, True)
                """
                ### XXX

                self.remove_package(None, match = (pkg_id,0))
                frac = float(current_counter)/total_counter*100
                self._progress.set_fraction(frac)
                self._progress.set_text("%s: %s" % (
                    _("Cleaning package"), atom,))
                self._entropy.oldcount = [current_counter,total_counter]

        while 1:
            change = False
            mydirs = set()
            mydirs = self._files_db.retrieveContent(None, contentType = "dir")
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
        inst_packages = ['%s:%s\n' % (entropy.tools.dep_getkey(atom),slot,) \
            for idpk, atom, slot, revision in client_repo.listAllPackages(
                get_scope = True, order_by = "atom")]
        # perfectly fine w/o self._root
        pkgset_dir = etpConst['confsetsdir']
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

        self._progress.set_fraction(100)
        self._progress.set_text(_("Installation complete"))

    def _get_removable_localized_packages(self):
        langpacks = [x.strip() for x in LANGUAGE_PACKS.split("\n") if \
            (not x.strip().startswith("#")) and x.strip()]

        # get cur lang
        def_lang = self._anaconda.instLanguage.instLang
        langpacks = set([x for x in langpacks if not \
            x.endswith("-%s" % (def_lang,))])

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

    def _setup_packages_to_remove(self):

        # remove anaconda if installed
        client_repo = self._entropy.installed_repository()
        pkg_id, pkg_rc = client_repo.atomMatch("anaconda")
        if pkg_id != -1:
            self._package_identifiers_to_remove.add(pkg_id)

        self._package_identifiers_to_remove.update(
            self._get_removable_localized_packages())

        if self._package_identifiers_to_remove:

            current_counter = 0
            total_counter = len(self._package_identifiers_to_remove)
            self._progress.set_fraction(current_counter)
            self._progress.set_text(_("Generating list of files to copy"))

            for pkg in self._package_identifiers_to_remove:
                current_counter += 1
                self._progress.set_fraction(
                    float(current_counter)/total_counter*100)
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

            self._progress.set_fraction(100)

        self._files_db.commitChanges()
        self._files_db.indexing = True
        self._files_db.createAllIndexes()

    def _add_file_to_ignore(self, f_path, ctype):
        self._files_db._cursor().execute(
            'INSERT into content VALUES (?,?,?)' , ( None, f_path, ctype, ))
