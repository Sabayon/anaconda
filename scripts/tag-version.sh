#!/bin/bash

set -e

# Check current dir
[[ ! -d ".git" ]] && echo "this script must be executed from git repo root" && exit 1

# Check target tag
[[ -z "$1" ]] && echo "usage: $0 <new-version>" && exit 1

# Validate new version
new_tag="$1"
for cur_tag in `git tag`; do
	[[ "$cur_tag" == "$new_tag" ]] && echo "$new_tag already tagged" && exit 1
done

git checkout future
git checkout -d archive-branch &> /dev/null || true

sed -i "s:^AC_INIT(\[anaconda.*:AC_INIT([anaconda], [$new_tag], [lxnay@sabayon.org]):g" configure.ac
git commit configure.ac -m "Version bump to $new_tag"
git push
git tag "anaconda-${new_tag}"
git push --tags

git checkout -b archive-branch "anaconda-${new_tag}"
./autogen.sh
./configure --prefix=/usr --mandir=/usr/share/man \
	--infodir=/usr/share/info --datadir=/usr/share --sysconfdir=/etc \
	--localstatedir=/var/lib --sbindir=/sbin --datarootdir=/usr/share \
	--disable-static --enable-introspection --enable-gtk-doc
make po-pull
make dist
git checkout po/anaconda.pot
git checkout future
git branch -d archive-branch

rsync -avP anaconda-${new_tag}.tar.bz2 fabio@pkg.sabayon.org:/sabayon/rsync/rsync.sabayon.org/distfiles/app-admin/
