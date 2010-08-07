#!/bin/sh
sh autogen.sh && ./configure --prefix=/usr --disable-selinux --enable-selinux=no && make -C po update-po && make distclean
