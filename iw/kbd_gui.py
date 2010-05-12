#
# keyboard_gui.py:  Shim around system-config-keyboard
# Brrrraaaaaiiiinnnns...
#
# Copyright (C) 2006, 2007  Red Hat, Inc.  All rights reserved.
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

from iw_gui import *
import sys

sys.path.append("/usr/share/system-config-keyboard")

from keyboard_gui import childWindow as installKeyboardWindow

import gtk
_ = lambda x: gettext.ldgettext("anaconda", x)

class KeyboardWindow(InstallWindow, installKeyboardWindow):
    def __init__(self, ics):
        InstallWindow.__init__(self, ics)
        installKeyboardWindow.__init__(self)

    def getNext(self):
        installKeyboardWindow.getNext(self)

    def _set_keyboard(self, widget):
        self.getNext()

    def getScreen(self, anaconda):
        default = anaconda.instLanguage.getDefaultKeyboard(anaconda.rootPath)
        anaconda.keyboard.set(default)
        gs_rc = installKeyboardWindow.getScreen(self, default, anaconda.keyboard)

        # add keyboard test widgets
        hbox = gtk.HBox()
        entry = gtk.Entry()
        button = gtk.Button(_("_Set keyboard"))
        button.connect("clicked", self._set_keyboard)
        tlabel = gtk.Label(_("Keyboard test:"))
        hbox.pack_start(tlabel, False, padding=5)
        hbox.pack_start(entry, True)
        hbox.pack_start(button, False)
        hbox.show_all()
        self.vbox.pack_start(hbox, False)
        hint_label = gtk.Label()
        hint_label.set_markup(_("<b>Note</b>: to switch layout (from Cyrillic to English, for instance) press <b>both</b> SHIFT keys"))
        self.vbox.pack_start(hint_label, False)

        return gs_rc
