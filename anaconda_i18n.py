#
# i18n.py - _() provider
#
# Copyright 2010 - Fabio Erculiani
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
import gettext

def _(x):
    tr_x = gettext.dgettext("anaconda", x)
    if os.getenv("ANACONDA_UNICODE"):
        return tr_x.decode("raw_unicode_escape")
    return tr_x
