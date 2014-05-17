#!/bin/bash

ver=$1

if [ -z "$ver" ]; then
	echo "$0 <ver>" >&2
	exit 1
fi

# sed -i "s:^AC_INIT(\[anaconda.*:AC_INIT([anaconda], [$ver], [lxnay@sabayon.org]):g" configure.ac || exit 1
# git commit configure.ac -m "Version bump to $ver" || exit 1
# git push || exit 1

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

rsync -avP anaconda-${ver}.tar.bz2 fabio@pkg.sabayon.org:/sabayon/rsync/rsync.sabayon.org/distfiles/app-admin/
