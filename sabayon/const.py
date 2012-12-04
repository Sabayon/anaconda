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

LANGUAGE_PACKS = """
kde-base/kde-l10n-bg
kde-base/kde-l10n-ca
kde-base/kde-l10n-cs
kde-base/kde-l10n-csb
kde-base/kde-l10n-da
kde-base/kde-l10n-de
kde-base/kde-l10n-el
kde-base/kde-l10n-en_GB
kde-base/kde-l10n-es
kde-base/kde-l10n-et
kde-base/kde-l10n-fi
kde-base/kde-l10n-fr
kde-base/kde-l10n-ga
kde-base/kde-l10n-gl
kde-base/kde-l10n-hi
kde-base/kde-l10n-hu
kde-base/kde-l10n-it
kde-base/kde-l10n-ja
kde-base/kde-l10n-kk
kde-base/kde-l10n-km
kde-base/kde-l10n-ko
kde-base/kde-l10n-lv
kde-base/kde-l10n-meta
kde-base/kde-l10n-mk
kde-base/kde-l10n-nb
kde-base/kde-l10n-nds
kde-base/kde-l10n-nl
kde-base/kde-l10n-nn
kde-base/kde-l10n-pa
kde-base/kde-l10n-pl
kde-base/kde-l10n-pt
kde-base/kde-l10n-pt_BR
kde-base/kde-l10n-ru
kde-base/kde-l10n-sl
kde-base/kde-l10n-sv
kde-base/kde-l10n-th
kde-base/kde-l10n-tr
kde-base/kde-l10n-uk
kde-base/kde-l10n-wa
kde-base/kde-l10n-zh_CN
kde-base/kde-l10n-zh_TW
kde-base/kde-l10n-meta

app-office/openoffice-l10n-af
app-office/openoffice-l10n-ar
app-office/openoffice-l10n-as_IN
app-office/openoffice-l10n-be_BY
app-office/openoffice-l10n-bg
app-office/openoffice-l10n-br
app-office/openoffice-l10n-bs
app-office/openoffice-l10n-ca
app-office/openoffice-l10n-cs
app-office/openoffice-l10n-da
app-office/openoffice-l10n-de
app-office/openoffice-l10n-dz
app-office/openoffice-l10n-el
app-office/openoffice-l10n-en_GB
app-office/openoffice-l10n-en_ZA
app-office/openoffice-l10n-es
app-office/openoffice-l10n-et
app-office/openoffice-l10n-fi
app-office/openoffice-l10n-fr
app-office/openoffice-l10n-ga
app-office/openoffice-l10n-gl
app-office/openoffice-l10n-gu
app-office/openoffice-l10n-he
app-office/openoffice-l10n-hi_IN
app-office/openoffice-l10n-hr
app-office/openoffice-l10n-hu
app-office/openoffice-l10n-it
app-office/openoffice-l10n-ja
app-office/openoffice-l10n-km
app-office/openoffice-l10n-ko
app-office/openoffice-l10n-ku
app-office/openoffice-l10n-lt
app-office/openoffice-l10n-meta
app-office/openoffice-l10n-mk
app-office/openoffice-l10n-ml_IN
app-office/openoffice-l10n-mr_IN
app-office/openoffice-l10n-nb
app-office/openoffice-l10n-ne
app-office/openoffice-l10n-nl
app-office/openoffice-l10n-nn
app-office/openoffice-l10n-nr
app-office/openoffice-l10n-ns
app-office/openoffice-l10n-or_IN
app-office/openoffice-l10n-pa_IN
app-office/openoffice-l10n-pl
app-office/openoffice-l10n-pt
app-office/openoffice-l10n-pt_BR
app-office/openoffice-l10n-ru
app-office/openoffice-l10n-rw
app-office/openoffice-l10n-sh
app-office/openoffice-l10n-sk
app-office/openoffice-l10n-sl
app-office/openoffice-l10n-sr
app-office/openoffice-l10n-ss
app-office/openoffice-l10n-st
app-office/openoffice-l10n-sv
app-office/openoffice-l10n-sw_TZ
app-office/openoffice-l10n-te_IN
app-office/openoffice-l10n-tg
app-office/openoffice-l10n-th
app-office/openoffice-l10n-ti_ER
app-office/openoffice-l10n-tr
app-office/openoffice-l10n-ts
app-office/openoffice-l10n-uk
app-office/openoffice-l10n-ur_IN
app-office/openoffice-l10n-ve
app-office/openoffice-l10n-vi
app-office/openoffice-l10n-xh
app-office/openoffice-l10n-zh_CN
app-office/openoffice-l10n-zh_TW
app-office/openoffice-l10n-zu

app-dicts/myspell-af
app-dicts/myspell-bg
app-dicts/myspell-ca
app-dicts/myspell-cs
app-dicts/myspell-cy
app-dicts/myspell-da
app-dicts/myspell-de
app-dicts/myspell-el
app-dicts/myspell-en
app-dicts/myspell-eo
app-dicts/myspell-es
app-dicts/myspell-et
app-dicts/myspell-fo
app-dicts/myspell-fr
app-dicts/myspell-ga
app-dicts/myspell-gl
app-dicts/myspell-he
app-dicts/myspell-hr
app-dicts/myspell-hu
app-dicts/myspell-ia
app-dicts/myspell-id
app-dicts/myspell-it
app-dicts/myspell-ku
app-dicts/myspell-lt
app-dicts/myspell-lv
app-dicts/myspell-mi
app-dicts/myspell-mk
app-dicts/myspell-ms
app-dicts/myspell-nb
app-dicts/myspell-nl
app-dicts/myspell-nn
app-dicts/myspell-pl
app-dicts/myspell-pt
app-dicts/myspell-ro
app-dicts/myspell-ru
app-dicts/myspell-sk
app-dicts/myspell-sl
app-dicts/myspell-sv
app-dicts/myspell-sw
app-dicts/myspell-tn
app-dicts/myspell-uk
app-dicts/myspell-zu

app-dicts/aspell-af
app-dicts/aspell-bg
app-dicts/aspell-br
app-dicts/aspell-ca
app-dicts/aspell-cs
app-dicts/aspell-cy
app-dicts/aspell-da
app-dicts/aspell-de
app-dicts/aspell-el
app-dicts/aspell-en
app-dicts/aspell-eo
app-dicts/aspell-es
app-dicts/aspell-et
app-dicts/aspell-fi
app-dicts/aspell-fr
app-dicts/aspell-ga
app-dicts/aspell-gl
app-dicts/aspell-he
app-dicts/aspell-hr
app-dicts/aspell-is
app-dicts/aspell-it
app-dicts/aspell-nl
app-dicts/aspell-pl
app-dicts/aspell-pt
app-dicts/aspell-ro
app-dicts/aspell-ru
app-dicts/aspell-sk
app-dicts/aspell-sl
app-dicts/aspell-sr
app-dicts/aspell-sv
app-dicts/aspell-uk
app-dicts/aspell-vi

app-i18n/man-pages-cs
app-i18n/man-pages-da
app-i18n/man-pages-de
app-i18n/man-pages-es
app-i18n/man-pages-fr
app-i18n/man-pages-it
app-i18n/man-pages-ja
app-i18n/man-pages-nl
app-i18n/man-pages-pl
app-i18n/man-pages-ro
app-i18n/man-pages-ru
app-i18n/man-pages-zh_CN
"""

# See Sabayon bug 2518
ASIAN_FONTS_PACKAGES = ["@ime-fonts-support", "@ime-fonts"]

# See Sabayon bug 2661
FIREWALL_PACKAGE = "net-firewall/ufw"
FIREWALL_SERVICE = "ufw"

LIVE_USER = "sabayonuser"
REPO_NAME = "sabayonlinux.org"

SB_PRIVATE_KEY = "/boot/SecureBoot/user-private.key"
SB_PUBLIC_X509 = "/boot/SecureBoot/user-public.crt"
# look for collisions
SB_PUBLIC_DER = "/boot/efi/EFI/sabayon/enroll-this.cer"
