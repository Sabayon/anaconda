#
# account_gui.py: gui root password and crypt algorithm dialog
#
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2005,  Red Hat Inc.
#               2006, 2007, 2008
# All rights reserved.
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

import gtk
import string
import gui
from iw_gui import *
from flags import flags
from constants import *
import cracklib
import _isys
from sabayon.const import LIVE_USER
import grp

import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)

class AccountWindow (InstallWindow):
    def getScreen(self, anaconda):
        self.anaconda = anaconda
        self.intf = anaconda.intf

        (self.xml, self.align) = gui.getGladeWidget("user.glade",
                                                    "account_align")
        self.icon = self.xml.get_widget("icon")
        self.capslock = self.xml.get_widget("capslock")
        self.pwlabel = self.xml.get_widget("pwlabel")
        self.pw = self.xml.get_widget("pw")
        self.username = self.xml.get_widget("username")
        self.fullname = self.xml.get_widget("fullname")
        self.confirmlabel = self.xml.get_widget("confirmlabel")
        self.confirm = self.xml.get_widget("confirm")
        self.usernamelabel = self.xml.get_widget("usernamelabel")
        self.fullnamelabel = self.xml.get_widget("fullnamelabel")

        # load the icon
        gui.readImageFromFile("root-password.png", image=self.icon)

        # connect hotkeys
        self.pwlabel.set_text_with_mnemonic(_("_Password:"))
        self.pwlabel.set_mnemonic_widget(self.pw)
        self.confirmlabel.set_text_with_mnemonic(_("_Confirm:"))
        self.confirmlabel.set_mnemonic_widget(self.confirm)

        self.usernamelabel.set_text_with_mnemonic(_("_Username:"))
        self.usernamelabel.set_mnemonic_widget(self.username)
        self.fullnamelabel.set_text_with_mnemonic(_("_Full name:"))
        self.fullnamelabel.set_mnemonic_widget(self.fullname)

        # watch for Caps Lock so we can warn the user
        self.intf.icw.window.connect("key-release-event",
            lambda w, e: self.handleCapsLockRelease(w, e, self.capslock))

        # we might have a root password already
        live_user_data = self.anaconda.users.otherUsers.get(LIVE_USER, {})
        self.pw.set_text(live_user_data.get('password', ''))
        self.confirm.set_text(live_user_data.get('password', ''))
        self.username.set_text(live_user_data.get('username', ''))
        self.fullname.set_text(live_user_data.get('fullname', ''))

        # pressing Enter in confirm == clicking Next
        vbox = self.xml.get_widget("account_box")
        self.confirm.connect("activate", lambda widget,
                             vbox=vbox: self.ics.setGrabNext(1))

        # set initial caps lock label text
        self.setCapsLockLabel()

        return self.align

    def focus(self):
        self.username.grab_focus()

    def passwordError(self):
        self.pw.set_text("")
        self.confirm.set_text("")
        self.pw.grab_focus()
        raise gui.StayOnScreen

    def usernameError(self):
        self.username.set_text("")
        self.username.grab_focus()
        raise gui.StayOnScreen

    def fullnameError(self):
        self.fullname.set_text("")
        self.fullname.grab_focus()
        raise gui.StayOnScreen

    def handleCapsLockRelease(self, window, event, label):
        if event.keyval == gtk.keysyms.Caps_Lock and \
           event.state & gtk.gdk.LOCK_MASK:
            self.setCapsLockLabel()

    def setCapsLockLabel(self):
        if _isys.isCapsLockEnabled():
            self.capslock.set_text("<b>" + _("Caps Lock is on.") + "</b>")
            self.capslock.set_use_markup(True)
        else:
            self.capslock.set_text("")

    def isStringLegal(self, tstr, spaces = True):
        legal = string.digits + string.ascii_letters + string.punctuation
        if spaces:
            legal += " "
        for letter in tstr:
            if letter not in legal:
                return False
        return True

    def isUsernameAlreadyAvailable(self, username):
        import pwd
        return username in [x.pw_name for x in pwd.getpwall()]

    def getNext (self):
        pw = self.pw.get_text()
        confirm = self.confirm.get_text()
        username = self.username.get_text().lower()
        fullname = self.fullname.get_text()

        if not pw or not confirm:
            self.intf.messageWindow(_("Error with Password"),
                                    _("You must enter your user password "
                                      "and confirm it by typing it a second "
                                      "time to continue."),
                                    custom_icon="error")
            self.passwordError()

        if pw != confirm:
            self.intf.messageWindow(_("Error with Password"),
                                    _("The passwords you entered were "
                                      "different.  Please try again."),
                                    custom_icon="error")
            self.passwordError()

        if len(pw) < 6:
            self.intf.messageWindow(_("Error with Password"),
                                    _("User password must be at least "
                                      "six characters long."),
                                    custom_icon="error")
            self.passwordError()

        try:
            cracklib.FascistCheck(pw)
        except ValueError, e:
            msg = gettext.ldgettext("cracklib", e)
            ret = self.intf.messageWindow(_("Weak Password"),
                                          _("You have provided a weak password: %s") % msg,
                                          type="custom", custom_icon="error",
                                          custom_buttons=[_("Cancel"), _("Use Anyway")])
            if ret == 0:
                self.passwordError()

        if not self.isStringLegal(pw):
            self.intf.messageWindow(_("Error with Password"),
                                    _("Requested password contains "
                                      "non-ASCII characters, which are "
                                      "not allowed."),
                                    custom_icon="error")
            self.passwordError()

        if len(username) < 2:
            self.intf.messageWindow(_("Error with username"),
                                    _("Username too short"),
                                    custom_icon="error")
            self.usernameError()

        if not self.isStringLegal(username, spaces = False):
            self.intf.messageWindow(_("Error with username"),
                                    _("Requested username contains "
                                      "non-ASCII characters or spaces, which are "
                                      "not allowed."),
                                    custom_icon="error")
            self.usernameError()

        if self.isUsernameAlreadyAvailable(username):
            self.intf.messageWindow(_("Error with username"),
                                    _("Requested username is already taken."),
                                    custom_icon="error")
            self.usernameError()

        def get_all_groups(user):
            for group in grp.getgrall():
                if user in group.gr_mem:
                    yield group.gr_name

        user_data = {
            'fullname': fullname,
            'password': pw,
            'username': username,
            'groups': list(get_all_groups(LIVE_USER)),
        }
        self.anaconda.users.otherUsers[LIVE_USER] = user_data

        return None
