#!/bin/sh
SABAYON_VER=${SABAYON_VER:-6}
rm -rf tmp
mkdir tmp
sh autogen.sh && \
	./configure --prefix=/usr --disable-selinux --enable-selinux=no && \
	make && make DESTDIR="${PWD}"/tmp install && \
	( find "${PWD}"/tmp -name "*.py[co]" | xargs rm ) && \
	( find "${PWD}"/tmp -name "*.*a" | xargs rm ) && \
	( find "${PWD}"/tmp -name "*.so" | xargs rm )
[[ "${?}" != "0" ]] && exit 1

pyanaconda_dir=$(find tmp -name "pyanaconda" -type d)
if [[ ! -d "${pyanaconda_dir}" ]]; then
	echo "ouch"
	exit 1
fi
cd $(dirname "${pyanaconda_dir}")
tar cjvf pyanaconda-${SABAYON_VER}.tar.bz2 "$(basename ${pyanaconda_dir})"
md5sum pyanaconda-${SABAYON_VER}.tar.bz2 > pyanaconda-${SABAYON_VER}.tar.bz2.md5
mv pyanaconda-${SABAYON_VER}.tar.bz2{,.md5} "${OLDPWD}"/
cd "${OLDPWD}"
make distclean
rm -rf tmp
echo
echo "Done cooking pyanaconda-${SABAYON_VER}.tar.bz2"
