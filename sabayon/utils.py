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

import glib

import stat
import sys
import subprocess
import shutil
import statvfs

from entropy.const import etpUi, etpConst, etpSys
import entropy.tools
from entropy.cache import EntropyCacher
from entropy.misc import TimeScheduled
from entropy.core.settings.base import SystemSettings
from entropy.core import Singleton

STDERR_LOG = open("/tmp/anaconda.stderr.log","aw")

class SabayonProgress(Singleton):

    def init_singleton(self, anaconda):
        self._intf = anaconda.intf
        self._prog = self._intf.instProgress
        self.__updater = None
        self._pix_count = 0

    def start(self):
        if self.__updater is None:
            self.__updater = TimeScheduled(3, self._prog.processEvents)
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


class Tools:

    def __init__(self, id = None, intf = None, progressTools = None):

        self.id = None
        self.intf = None
        self.SystemHealthChecker = None
        self.healthMessage = ''
        self.unhealthySystemWarningShown = False
        self.progressTools = progressTools
        self.Entropy = Entropy
        self._settings = SystemSettings()
        f = open("/proc/cmdline","r")
        self.cmdline = f.readline().strip().split()
        f.close()

        sys.stderr = STDERR_LOG

        self.instPath = chrootPath
        # instdata stuff - for the GUI
        if id is not None:
            self.id = id

        if intf != None:
            self.intf = intf

        self.startSystemHealthCheck()

        self.filesDb = None
        self.liveDatabasePath = productPath + etpConst['etpdatabaseclientfilepath']
        self.chrootDatabasePath = self.instPath+etpConst['etpdatabaseclientfilepath']
        self.clientDbconn = self.openLiveDatabase()

    def destroy(self):
        if self.SystemHealthChecker != None:
            self.SystemHealthChecker.kill()
            self.SystemHealthChecker.join()
        EntropyCacher().stop()

    def umountAll(self):
        if not os.access("/etc/mtab",os.R_OK): return
        f = open("/etc/mtab","r")
        sab_mounts = sorted([x.strip().split()[1] for x in f.readlines() if (x.strip().find(self.instPath) != -1)], reverse = True)
        f.close()
        for mount in sab_mounts:
            self.execCmd("umount %s &> /dev/null" % (mount,))

    def checkBootAvailSpace(self):
        boot_path = self.instPath+"/boot"
        if not os.path.isdir(boot_path):
            return
        boot_size = (1024000*40)
        # check if we have enough space on disk
        st = os.statvfs(boot_path)
        freeblocks = st[statvfs.F_BFREE]
        blocksize = st[statvfs.F_BSIZE]
        freespace = freeblocks*blocksize
        if boot_size > freespace:
            if self.intf != None:
                self.intf.messageWindow(_("Not enough /boot partition space"),
                        "You don't have enough space in /boot, you need at least 40Mb",
                        custom_icon="error")
                raise SystemExit(1)
            else:
                print "You don't have enough space in /boot, you need at least 40Mb."
                raise SystemExit(1)

    def startSystemHealthCheck(self):
        self.SystemHealthChecker = TimeScheduled(20, self.healthCheck)
        self.SystemHealthChecker.start()

    def healthCheck(self):
        if self.unhealthySystemWarningShown: return

        msg_file = "/var/log/messages"
        found_error = False
        if not (os.path.isfile(msg_file) and os.access(msg_file,os.R_OK)):
            return

        f = open(msg_file,"r")
        try:
            f.seek(-500,2)
        except IOError:
            f.close()
            return

        data = [x for x in f.read().split("\n") if x.find("SQUASHFS error") != -1]
        f.close()
        if data:
            self.healthMessage = data[0].strip()
            self.showBrokenSystemWarning()


    def showBrokenSystemWarning(self):

        if self.intf != None:
            self.intf.messageWindow(
                _("System Health Status Warning"),
                "Your system is having HARDWARE issues, continue at your risk, error: "+self.healthMessage,
                custom_icon="error"
        )
        self.unhealthySystemWarningShown = True

    def execChrootCommand(self, args, chroot, silent = False):

        pid = os.fork()
        if pid == 0:

            os.chroot(chroot)
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

    def execCmd(self, args):
        myargs = args
        if isinstance(args,(list, tuple)):
            myargs = ' '.join(args)
        return subprocess.call(myargs, shell = True)

    # Flush data from RAM to hard drives
    def syncDisks(self):
        os.system("sync ; sync; sync")

    # This create the "first time run" file
    def createNativeEntropyFile(self):
        if not os.path.isdir(self.instPath+"/etc/entropy"):
            os.makedirs(self.instPath+"/etc/entropy")
        f = open(self.instPath+"/etc/entropy/native","w")
        f.write("# do not remove this file !!\n")
        f.close()

    def runLdconfig(self):
        self.execChrootCommand("ldconfig", self.instPath)

    def openLiveDatabase(self):
        dbconn = self.Entropy.open_generic_repository(
            dbfile = self.liveDatabasePath,
            xcache = False, readOnly = True, dbname = "live_client",
            indexing_override = False)
        return dbconn

    def switchEntropyChroot(self, chroot = ""):
        if chroot == "":
            self.Entropy.noclientdb = False
            etpUi['nolog'] = True
        else:
            self.Entropy.noclientdb = True
            etpUi['nolog'] = False
        self.Entropy.switch_chroot(chroot)
        sys_settings_plg_id = etpConst['system_settings_plugins_ids']['client_plugin']
        del self._settings[sys_settings_plg_id]['misc']['configprotectskip'][:]

    def removePackage(self, atom, match = None, silent = False):

        chroot = self.instPath
        root = etpSys['rootdir']
        if chroot != root:
            self.switchEntropyChroot(chroot)

        if match == None:
            match = self.Entropy.installed_repository().atomMatch(atom)

        oldstdout = sys.stdout
        if silent:
            sys.stdout = STDERR_LOG

        try:
            rc = 0
            if match[0] != -1:
                Package = self.Entropy.Package()
                Package.prepare((match[0],),"remove")
                if not Package.pkgmeta.has_key('remove_installed_vanished'):
                    rc = Package.run()
                    Package.kill()
        finally:
            if silent:
                sys.stdout = oldstdout

        if chroot != root:
            self.switchEntropyChroot(root)

        return rc

    def installPackage(self, tbz2):
        chroot = self.instPath
        root = etpSys['rootdir']
        if chroot != root:
            self.switchEntropyChroot(chroot)

        rc, atomsfound = self.Entropy.add_package_to_repositories(tbz2)
        repo = 0
        if rc != 0:
            return rc
        for match in atomsfound:
            repo = match[1]
            Package = self.Entropy.Package()
            Package.prepare(match,"install")
            rc2 = Package.run()
            if rc2 != 0:
                if chroot != root:
                    self.switchEntropyChroot(root)
                return rc2
            Package.kill()

        if chroot != root:
            self.switchEntropyChroot(root)

        if repo != 0:
            self.Entropy.remove_repository(repo)

        return 0

    def isSabayonCoreCD(self):
        rc = self.id.getDefaultDesktopChoose()
        if rc == "corecd":
            return True
        return False

    def configureDesktopSkel(self):

        # copy Sulfur on the desktop
        sulfur_desktop = self.instPath+"/usr/share/applications/sulfur.desktop"
        if os.path.isfile(sulfur_desktop):
            sulfur_user_desktop = self.instPath+"/etc/skel/Desktop/sulfur.desktop"
            shutil.copy2(sulfur_desktop, sulfur_user_desktop)
            try:
                os.chmod(sulfur_user_desktop, 0775)
            except OSError:
                pass

        gparted_desktop = self.instPath+"/etc/skel/Desktop/gparted.desktop"
        if os.path.isfile(gparted_desktop):
            os.remove(gparted_desktop)

        installer_desk = self.instPath+"/etc/skel/Desktop/Anaconda Installer.desktop"
        if os.path.isfile(installer_desk):
            os.remove(installer_desk)

    def removeLiveUser(self):

        # configure .desktop files on Desktop
        self.configureDesktopSkel()

        # remove live user and its home dir
        pid = os.fork()
        if pid > 0:
            os.waitpid(pid, 0)
        else:
            os.chroot(self.instPath)
            live_user = self.getLiveUsername()
            proc = subprocess.Popen(("userdel", "-f", "-r", live_user),
                stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            os._exit(proc.wait())

    def setParallelBoot(self, enable = False):
        if "noparallel" in self.cmdline: return

        rc_conf = self.instPath+"/etc/rc.conf"
        if not os.path.isfile(rc_conf):
            return
        f = open(rc_conf,"r")
        content = [x.strip() for x in f.readlines()]
        f.close()
        new_content = []
        for line in content:
            if line.startswith("rc_parallel="):
                if enable:
                    line = "rc_parallel=\"YES\""
                else:
                    line = "rc_parallel=\"NO\""
            new_content.append(line)
        f = open(rc_conf,"w")
        for line in new_content:
            f.write(line+"\n")
        f.flush()
        f.close()


    # Add/Remove system services
    def configureServices(self):

        action = "Configuring System Services"
        self.progressTools.setPartialProgress(0,100,action)

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
        self.execChrootCommand(config_script, self.instPath, silent = True)

        # configure user choosen services
        if self.id is not None:
            if self.id.RemoveServices:
                for service in self.id.RemoveServices:
                    self.execChrootCommand("rc-update del %s boot default" % (service,), self.instPath, silent = True)
            for service, runlevel in self.id.AddServices:
                self.execChrootCommand("rc-update add %s %s" % (service,runlevel,), self.instPath, silent = True)

        self.progressTools.setPartialProgress(50,100,action)

        # setup dmcrypt service if user enabled encryption
        if self.id.isEncryptionOn():
            self.execChrootCommand("rc-update add dmcrypt boot", self.instPath, silent = True)

        # Copy the kernel modules blacklist configuration file
        if os.access("/etc/modules.d/blacklist",os.F_OK):
            self.execCmd("cp -p /etc/modules.d/blacklist %s//etc/modules.d/blacklist" % (self.instPath,))

        self.progressTools.setPartialProgress(100,100,action)

    # Detect a possible OSS video card and remove /etc/env.d/*ati
    def removeProprietaryDrivers(self):
        if self.getOpenGL() == "xorg-x11":
            ogl_script = """
                rm -f /etc/env.d/09ati
                rm -rf /usr/lib/opengl/ati
                rm -rf /usr/lib/opengl/nvidia
            """
            self.execChrootCommand(ogl_script, self.instPath)
            self.removePackage('ati-drivers', silent = True)
            self.removePackage('nvidia-settings', silent = True)
            self.removePackage('nvidia-drivers', silent = True)

    # get the current OpenGL subsystem (ati,nvidia,xorg-x11)
    def getOpenGL(self, chroot = None):

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

    def setupManualNetworking(self):
        mn_script = """
            rc-update del NetworkManager default
            rc-update del avahi-daemon default
            rc-update del dhcdbd default
            if [ -f "/etc/rc.conf" ]; then
                sed -i 's/^#rc_hotplug=".*"/rc_hotplug="*"/g' /etc/rc.conf
                sed -i 's/^rc_hotplug=".*"/rc_hotplug="*"/g' /etc/rc.conf
            fi
        """
        self.execChrootCommand(mn_script, self.instPath, silent = True)

    def setupSplashSettings(self):
        mn_script = """
            if [ -f "/etc/conf.d/splash" ]; then
                sed -i 's/SPLASH_VERBOSE_ON_ERRORS=".*"/SPLASH_VERBOSE_ON_ERRORS="no"/g' /etc/conf.d/splash
                sed -i 's/SPLASH_AUTOVERBOSE=".*"/SPLASH_AUTOVERBOSE="no"/g' /etc/conf.d/splash
            fi
        """
        self.execChrootCommand(mn_script, self.instPath, silent = True)

    # get the default livecd username
    def getLiveUsername(self):
        return "sabayonuser"

    # This function copy the LiveCD/DVD content into self.instPath
    def RunInstallFileCopy(self):

        self.handleSelectedPackagesCategory()

        action = "System Installation"
        copy_update_interval = 300
        copy_update_counter = 299
        # get file counters
        total_files = 0
        imageDir = productPath
        for z,z,files in os.walk(imageDir):
            for file in files:
                total_files += 1

        self.progressTools.setPartialProgress(0,total_files,action)

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
        imageDir_len = len(imageDir)
        # Create the directory structure
        # self.InstallFilesToIgnore
        for currentdir, subdirs, files in os.walk(imageDir):

            copy_update_counter += 1

            for xdir in subdirs:

                imagepathDir = currentdir + "/" + xdir
                mydir = imagepathDir[imageDir_len:]
                rootdir = self.instPath + mydir # os.path.join(self.instPath,mydir) NOW TELL ME WHY THE HELL IT DOESN'T WORK

                # handle broken symlinks
                if os.path.islink(rootdir) and not os.path.exists(rootdir):# broken symlink
                    os.remove(rootdir)

                # if our directory is a file on the live system
                elif os.path.isfile(rootdir): # really weird...!
                    os.remove(rootdir)

                # if our directory is a symlink instead, then copy the symlink
                if os.path.islink(imagepathDir) and not os.path.isdir(rootdir): # for security we skip live items that are dirs
                    tolink = os.readlink(imagepathDir)
                    if os.path.islink(rootdir):
                        os.remove(rootdir)
                    os.symlink(tolink,rootdir)
                elif (not os.path.isdir(rootdir)) and (not os.access(rootdir,os.R_OK)):
                    #print "creating dir "+rootdir
                    os.makedirs(rootdir)

                if not os.path.islink(rootdir): # symlink don't need permissions, also until os.walk ends they might be broken
                    user = os.stat(imagepathDir)[4]
                    group = os.stat(imagepathDir)[5]
                    os.chown(rootdir,user,group)
                    shutil.copystat(imagepathDir,rootdir)

            for file in sorted(files):

                current_counter += 1
                fromfile = currentdir+"/"+file
                currentfile = fromfile[imageDir_len:]

                if currentfile.startswith("/opt/anaconda"):
                    continue
                if currentfile.startswith("/dev"):
                    continue
                elif currentfile == "/boot/grub/grub.conf":
                    continue
                elif currentfile == "/boot/grub/grub.cfg":
                    continue

                try:
                    # if file is in the ignore list
                    if self.filesDb.isFileAvailable(
                        currentfile.decode('raw_unicode_escape')):
                        continue
                except:
                    import traceback
                    traceback.print_exc()
                    pass

                tofile = self.instPath + currentfile
                st_info = os.lstat(fromfile)
                if stat.S_ISREG(st_info[stat.ST_MODE]):
                    copy_reg(fromfile, tofile)
                elif stat.S_ISLNK(st_info[stat.ST_MODE]):
                    copy_lnk(fromfile, tofile)
                else:
                    copy_other(fromfile, tofile)


            if (copy_update_counter == copy_update_interval) or ((total_files - 1000) < current_counter):
                # do that every 1000 iterations
                copy_update_counter = 0
                self.progressTools.setPartialProgress(current_counter,total_files,action)
                total_counter = round(float (current_counter) / total_files * 75,2)
                self.progressTools.setTotalProgress(total_counter)
                # for the Text part

        self.switchEntropyChroot(self.instPath)
        # Removing Unwanted Packages
        if self.id.idpackagesToRemove:

            # this makes packages removal much faster
            self.Entropy.installed_repository().indexing = True
            self.Entropy.installed_repository().createAllIndexes()

            total_counter = len(self.id.idpackagesToRemove)
            current_counter = 0
            self.progressTools.setPartialProgress(current_counter,total_counter,"Cleaning Packages")
            self.Entropy.oldcount = [0,total_counter]

            for idpackage in self.id.idpackagesToRemove:
                current_counter += 1
                atom = self.Entropy.installed_repository().retrieveAtom(idpackage)
                if not atom:
                    continue

                ### XXX needed to speed up removal process
                category = self.Entropy.installed_repository().retrieveCategory(idpackage)
                version = self.Entropy.installed_repository().retrieveVersion(idpackage)
                name = self.Entropy.installed_repository().retrieveName(idpackage)
                ebuild_path = self.instPath+"/var/db/pkg/%s/%s-%s" % (category,name,version)
                if os.path.isdir(ebuild_path):
                    shutil.rmtree(ebuild_path,True)
                ### XXX

                self.removePackage(idpackage, match = (idpackage,0))
                self.progressTools.setPartialProgress(current_counter,total_counter,"Cleaning %s" % (atom,) )
                self.Entropy.oldcount = [current_counter,total_counter]

        while 1:
            change = False
            mydirs = set()
            mydirs = self.filesDb.retrieveContent(None, contentType = "dir")
            for mydir in mydirs:
                mytree = os.path.join(self.instPath,mydir)
                if os.path.isdir(mytree) and not self.Entropy.installed_repository().isFileAvailable(mydir):
                    try:
                        os.rmdir(mytree)
                        change = True
                    except OSError:
                        pass
            if not change:
                break

        # list installed packages and setup a package set
        inst_packages = ['%s:%s\n' % (entropy.tools.dep_getkey(atom),slot,) for \
            idpk,atom,slot,revision in self.Entropy.installed_repository().listAllPackages(get_scope = True, order_by = "atom")]
        # perfectly fine w/o instPath
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

        self.switchEntropyChroot()

        # remove files db if exists
        dbfile = self.filesDb.dbFile
        self.filesDb.closeDB()
        try:
            os.remove(dbfile)
        except OSError:
            pass

        self.installationWorkarounds()

        action = "System Installation completed"
        self.progressTools.setPartialProgress(100,100,action)
        self.syncDisks()

    def installationWorkarounds(self):
        pass

    # this function handles all the LiveDVD files and user selected categories
    # self.id.grpset is your friend
    def handleSelectedPackagesCategory(self):

        self.filesDb = self.Entropy.open_generic_repository(
            self.instPath+"/files.db", dbname = "filesdb",
            indexing_override = True)
        self.filesDb.initializeDatabase()
        self.id.handleLocalizedPackagesRemoval()

        if self.id.idpackagesToRemove:

            current_counter = 0
            self.progressTools.setPartialProgress(current_counter,len(self.id.idpackagesToRemove),"Collecting data")

            for pkg in self.id.idpackagesToRemove:
                current_counter += 1
                self.progressTools.setPartialProgress(current_counter,len(self.id.idpackagesToRemove),"Collecting data")
                # get its files
                mycontent = self.clientDbconn.retrieveContent(pkg, extended = True)
                mydirs = [x[0] for x in mycontent if x[1] == "dir"]
                for x in mydirs:
                    if x.find("/usr/lib64") != -1:
                        x = x.replace("/usr/lib64","/usr/lib")
                    elif x.find("/lib64") != -1:
                        x = x.replace("/lib64","/lib")
                    self.addFileToIgnore(x, "dir")
                mycontent = [x[0] for x in mycontent if x[1] == "obj"]
                for x in mycontent:
                    if x.find("/usr/lib64") != -1:
                        x = x.replace("/usr/lib64","/usr/lib")
                    elif x.find("/lib64") != -1:
                        x = x.replace("/lib64","/lib")
                    self.addFileToIgnore(x, "obj")
                del mycontent

            self.progressTools.setPartialProgress(100,100,"Collecting data")

        self.filesDb.commitChanges()
        self.filesDb.indexing = True
        self.filesDb.createAllIndexes()

    def addFileToIgnore(self, f_path, ctype):
        self.filesDb._cursor().execute(
            'INSERT into content VALUES (?,?,?)' , ( None, f_path, ctype, ))
