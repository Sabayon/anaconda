#
# userauth_text.py: text mode authentication setup dialogs
#
# Copyright (C) 2000, 2001, 2002, 2008  Red Hat, Inc.  All rights reserved.
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

from snack import *
from constants_text import *
import cracklib

from constants import *
import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)

class RootPasswordWindow:
    def __call__ (self, screen, anaconda):
        toplevel = GridFormHelp(screen, _("Root Password"), "rootpw", 1, 3)

        toplevel.add(TextboxReflowed(37,
                                     _("Pick a root password. You must "
                                       "type it twice to ensure you know "
                                       "it and do not make a typing "
                                       "mistake. ")),
                     0, 0, (0, 0, 0, 1))

        if anaconda.users.rootPassword["isCrypted"]:
            anaconda.users.rootPassword["password"] = ""

        entry1 = Entry(24, password=1,
                       text=anaconda.users.rootPassword["password"])
        entry2 = Entry(24, password=1,
                       text=anaconda.users.rootPassword["password"])
        passgrid = Grid(2, 2)
        passgrid.setField(Label(_("Password:")), 0, 0, (0, 0, 1, 0),
                          anchorLeft=1)
        passgrid.setField(Label(_("Password (confirm):")), 0, 1, (0, 0, 1, 0),
                          anchorLeft=1)
        passgrid.setField(entry1, 1, 0)
        passgrid.setField(entry2, 1, 1)
        toplevel.add(passgrid, 0, 1, (0, 0, 0, 1))

        bb = ButtonBar(screen, (TEXT_OK_BUTTON, TEXT_BACK_BUTTON))
        toplevel.add(bb, 0, 2, growx = 1)

        while 1:
            toplevel.setCurrent(entry1)
            result = toplevel.run()
            rc = bb.buttonPressed(result)
            if rc == TEXT_BACK_CHECK:
                screen.popWindow()
                return INSTALL_BACK
            if len(entry1.value()) < 6:
                ButtonChoiceWindow(screen, _("Password Length"),
                    _("The root password must be at least 6 characters long."),
                    buttons = [ TEXT_OK_BUTTON ], width = 50)
            elif entry1.value() != entry2.value():
                ButtonChoiceWindow(screen, _("Password Mismatch"),
                    _("The passwords you entered were different. Please "
                      "try again."), buttons = [ TEXT_OK_BUTTON ], width = 50)
            elif self.hasBadChars(entry1.value()):
                ButtonChoiceWindow(screen, _("Error with Password"),
                    _("Requested password contains non-ASCII characters, "
                      "which are not allowed."),
                    buttons = [ TEXT_OK_BUTTON ], width = 50)
            else:
                try:
                    cracklib.FascistCheck(entry1.value())
                except ValueError, e:
                    msg = gettext.ldgettext("cracklib", e)
                    ret = anaconda.intf.messageWindow(_("Weak Password"),
                             _("You have provided a weak password: %s\n\n"
                               "Would you like to continue with this password?"
                               % (msg, )),
                             type = "yesno", default="no")
                    if ret == 1:
                        break
                else:
                    break

            entry1.set("")
            entry2.set("")

        screen.popWindow()
        anaconda.users.rootPassword["password"] = entry1.value()
        anaconda.users.rootPassword["isCrypted"] = False
        return INSTALL_OK

    def hasBadChars(self, pw):
        allowed = string.digits + string.ascii_letters + \
                  string.punctuation + " "
        for letter in pw:
            if letter not in allowed:
                return True
        return False

class UserPasswordWindow:
    def __call__ (self, screen, anaconda):
        toplevel = GridFormHelp(screen, _("User configuration"), "rootpw", 1, 3)

        toplevel.add(TextboxReflowed(37,
                                     _("Setup a username for regular "
                                       "(non-administrative) use.")),
                     0, 0, (0, 0, 0, 1))

        from sabayon.const import LIVE_USER
        live_user_data = anaconda.users.otherUsers.get(LIVE_USER, {})

        entry_username = Entry(24, text=live_user_data.get("username", ''))
        entry_fullname = Entry(24, text=live_user_data.get("fullname", ''))

        entry1 = Entry(24, password=1,
                       text=live_user_data.get("password", ''))
        entry2 = Entry(24, password=1,
                       text=live_user_data.get("password", ''))
        passgrid = Grid(2, 4)

        passgrid.setField(Label(_("Username:")), 0, 0, (0, 0, 1, 0),
                          anchorLeft=1)
        passgrid.setField(Label(_("Full name:")), 0, 1, (0, 0, 1, 0),
                          anchorLeft=1)
        passgrid.setField(Label(_("Password:")), 0, 2, (0, 0, 1, 0),
                          anchorLeft=1)
        passgrid.setField(Label(_("Password (confirm):")), 0, 3, (0, 0, 1, 0),
                          anchorLeft=1)

        passgrid.setField(entry_username, 1, 0)
        passgrid.setField(entry_fullname, 1, 1)
        passgrid.setField(entry1, 1, 2)
        passgrid.setField(entry2, 1, 3)

        toplevel.add(passgrid, 0, 1, (0, 0, 0, 1))

        bb = ButtonBar(screen, (TEXT_OK_BUTTON, TEXT_BACK_BUTTON))
        toplevel.add(bb, 0, 2, growx = 1)

        while 1:
            clean_pass = True
            toplevel.setCurrent(entry1)
            result = toplevel.run()
            rc = bb.buttonPressed(result)
            if rc == TEXT_BACK_CHECK:
                screen.popWindow()
                return INSTALL_BACK
            if len(entry1.value()) < 6:
                ButtonChoiceWindow(screen, _("Password Length"),
                    _("User password must be at least 6 characters long."),
                    buttons = [ TEXT_OK_BUTTON ], width = 50)
            elif entry1.value() != entry2.value():
                ButtonChoiceWindow(screen, _("Password Mismatch"),
                    _("The passwords you entered were different. Please "
                      "try again."), buttons = [ TEXT_OK_BUTTON ], width = 50)
            elif self.hasBadChars(entry1.value()):
                ButtonChoiceWindow(screen, _("Error with Password"),
                    _("Requested password contains non-ASCII characters, "
                      "which are not allowed."),
                    buttons = [ TEXT_OK_BUTTON ], width = 50)

            elif len(entry_username.value()) < 2:
                anaconda.intf.messageWindow(_("Error with username"),
                                        _("Username too short"),
                                        custom_icon="error")
                clean_pass = False
            elif self.isUsernameAlreadyAvailable(entry_username.value()):
                self.intf.messageWindow(_("Error with username"),
                                    _("Requested username is already taken."),
                                    custom_icon="error")
                self.usernameError()

            if self.hasBadChars(entry_username.value(), spaces = False):
                anaconda.intf.messageWindow(_("Error with username"),
                                        _("Requested username contains "
                                          "non-ASCII characters or spaces, which are "
                                          "not allowed."),
                                        custom_icon="error")
                clean_pass = False
            else:
                try:
                    cracklib.FascistCheck(entry1.value())
                except ValueError, e:
                    msg = gettext.ldgettext("cracklib", e)
                    ret = anaconda.intf.messageWindow(_("Weak Password"),
                             _("You have provided a weak password: %s\n\n"
                               "Would you like to continue with this password?"
                               % (msg, )),
                             type = "yesno", default="no")
                    if ret == 1:
                        break
                else:
                    break

            if clean_pass:
                entry1.set("")
                entry2.set("")

        screen.popWindow()

        import grp
        def get_all_groups(user):
            for group in grp.getgrall():
                if user in group.gr_mem:
                    yield group.gr_name

        user_data = {
            'fullname': entry_fullname.value(),
            'password': entry1.value(),
            'username': entry_username.value(),
            'groups': list(get_all_groups(LIVE_USER)),
        }
        anaconda.users.otherUsers[LIVE_USER] = user_data

        return INSTALL_OK

    def hasBadChars(self, pw, spaces = True):
        allowed = string.digits + string.ascii_letters + \
                  string.punctuation
        if spaces:
            allowed += " "
        for letter in pw:
            if letter not in allowed:
                return True
        return False

    def isUsernameAlreadyAvailable(self, username):
        import pwd
        return username in [x.pw_name for x in pwd.getpwall()]
