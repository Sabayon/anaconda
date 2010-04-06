#
# sabayon.py: Sabayon Linux Anaconda install method backend
#
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

import os

# Entropy Interface
from entropy.client.interfaces import Client
from entropy.output import nocolor

class Entropy(Client):

    def init_singleton(self):
        self._progress = None
        self.oldcount = []
        Client.init_singleton(self, indexing = False, xcache = False)
        nocolor()
        self.indexing = False

    def connect_progress(self, progress):
        self._progress = progress

    def output(self, text, header = "", footer = "", back = False,
        importance = 0, type = "info", count = None, percent = False):

        if not self._progress:
            return

        if not self.oldcount:
            self.oldcount = [0,100]

        progress_text = text
        if count:
            try:
                self.oldcount = int(count[0]),int(count[1])
            except:
                self.oldcount = [0,100]
            if not percent:
                count_str = "(%s/%s) " % (str(count[0]),str(count[1]),)
                progress_text = count_str+progress_text

        percentage = float(self.oldcount[0])/self.oldcount[1] * 100
        percentage = round(percentage, 2)
        self._progress.set_fraction(percentage)
        self._progress.set_text(progress_text)

    def is_installed(self, package_name):
        match = self.installed_repository().atomMatch(package_name)
        if match[0] != -1:
            return True
        return False

    @staticmethod
    def is_corecd():
        if os.path.isfile("/etc/sabayon-edition"):
            f = open("/etc/sabayon-edition","r")
            cnt = f.readline().strip()
            f.close()
            if cnt.lower().find("core") != -1:
                return True
        return False

    @staticmethod
    def is_sabayon_mce():
        with open("/proc/cmdline", "r") as cmd_f:
            args = cmd_f.readline().strip().split()
            for tstr in ("mceinstall", "sabayonmce"):
                if tstr in args:
                    return True
            return False
