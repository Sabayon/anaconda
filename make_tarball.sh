#!/bin/bash

ver=$1

if [ -z "$ver" ]; then
	echo "$0 <ver>" >&2
	exit 1
fi

git checkout -d archive-branch &> /dev/null
git checkout -b archive-branch "anaconda-${ver}" || exit 1
./autogen.sh || exit 1
./configure --prefix=/usr --mandir=/usr/share/man \
	--infodir=/usr/share/info --datadir=/usr/share --sysconfdir=/etc \
	--localstatedir=/var/lib --sbindir=/sbin --datarootdir=/usr/share \
	--disable-static --enable-introspection --enable-gtk-doc || exit 1
make po-pull || exit 1
make dist || exit 1
git checkout po/anaconda.pot || exit 1
git checkout future || exit 1
git branch -d archive-branch || exit 1
