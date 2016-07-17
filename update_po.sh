#!/bin/sh
sh autogen.sh && ./configure --prefix=/usr --disable-selinux --enable-selinux=no && make po-pull && make -C po update-po && make distclean
