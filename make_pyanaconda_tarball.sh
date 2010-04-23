#!/bin/sh
rm -rf tmp
mkdir tmp
sh autogen.sh
./configure --prefix=/usr --disable-selinux --enable-selinux=no
make
make DESTDIR=$PWD/tmp install
find $PWD/tmp -name "*.py[co]" | xargs rm
find $PWD/tmp -name "*.*a" | xargs rm
find $PWD/tmp -name "*.so" | xargs rm
pyanaconda_dir=$(find tmp -name "pyanaconda" -type d)
[[ -d "${pyanaconda_dir}" ]] || (echo "ouch" && exit 1)
cd $(dirname ${pyanaconda_dir})
tar cjvf pyanaconda.tar.bz2 "$(basename ${pyanaconda_dir})"
mv pyanaconda.tar.bz2 $OLDPWD/
cd $OLDPWD
make distclean
rm -rf tmp
echo
echo "Done cooking pyanaconda.tar.bz2"