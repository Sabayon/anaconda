#
# livecd.py
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

LIVE_USER = "sabayonuser"
REPO_NAME = "sabayonlinux.org"

SB_PRIVATE_KEY = "/boot/SecureBoot/user-private.key"
SB_PUBLIC_X509 = "/boot/SecureBoot/user-public.crt"
# look for collisions
SB_PUBLIC_DER = "/boot/efi/EFI/sabayon/enroll-this.cer"
