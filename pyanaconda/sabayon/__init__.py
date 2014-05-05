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
import sys
import logging

# add Entropy module path to PYTHONPATH
sys.path.insert(0, '/usr/lib/entropy/libraries')
sys.path.insert(0, '/usr/lib/entropy/lib')

# Entropy Interface
from entropy.client.interfaces import Client
from entropy.output import nocolor
from entropy.fetchers import UrlFetcher
import entropy.tools

log = logging.getLogger("packaging")

class Entropy(Client):

    _oldcount = None

    def init_singleton(self):
        Client.init_singleton(self, xcache = False,
            url_fetcher = InstallerUrlFetcher)
        nocolor()

    @classmethod
    def output(cls, text, header = "", footer = "", back = False,
        importance = 0, level = "info", count = None, percent = False):

        if not Entropy._oldcount:
            Entropy._oldcount = (0, 100)

        progress_text = text

        if count:
            try:
                Entropy._oldcount = (int(count[0]), int(count[1]))
            except:
                Entropy._oldcount = (0, 100)

            if not percent:
                count_str = "(%s/%s) " % (str(count[0]),str(count[1]),)
                progress_text = count_str + progress_text

        log.info(progress_text)

    def is_installed(self, package_name):
        match = self.installed_repository().atomMatch(package_name)
        if match[0] != -1:
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

    @staticmethod
    def is_sabayon_steambox():
        with open("/proc/cmdline", "r") as cmd_f:
            args = cmd_f.readline().strip().split()
            for tstr in ("steaminstall", "steambox"):
                if tstr in args:
                    return True
            return False

# in this way, any singleton class that tries to directly load Client
# gets Entropy in change
Client.__singleton_class__ = Entropy

class InstallerUrlFetcher(UrlFetcher):

    gui_last_avg = 0

    def __init__(self, *args, **kwargs):
        UrlFetcher.__init__(self, *args, **kwargs)
        self.__average = 0
        self.__downloadedsize = 0
        self.__remotesize = 0
        self.__datatransfer = 0

    def handle_statistics(self, th_id, downloaded_size, total_size,
            average, old_average, update_step, show_speed, data_transfer,
            time_remaining, time_remaining_secs):
        self.__average = average
        self.__downloadedsize = downloaded_size
        self.__remotesize = total_size
        self.__datatransfer = data_transfer

    def output(self):
        """ backward compatibility """
        return self.update()

    def update(self):

        myavg = abs(int(round(float(self.__average), 1)))
        if abs((myavg - InstallerUrlFetcher.gui_last_avg)) < 1:
            return

        if (myavg > InstallerUrlFetcher.gui_last_avg) or (myavg < 2) or \
            (myavg > 97):

            cur_prog = float(self.__average)/100
            cur_prog_str = str(int(self.__average))

            human_dt = entropy.tools.bytes_into_human(self.__datatransfer)
            prog_str = "%s/%s kB @ %s" % (
                    str(round(float(self.__downloadedsize)/1024, 1)),
                    str(round(self.__remotesize, 1)),
                    str(human_dt) + "/sec",
                )
            Entropy().output(prog_str)
            InstallerUrlFetcher.gui_last_avg = myavg
