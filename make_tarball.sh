#!/bin/bash

ver=$1

if [ -z "$ver" ]; then
	echo "$0 <ver>" >&2
	exit 1
fi

git checkout -d archive-branch &> /dev/null
git checkout -b archive-branch "anaconda-${ver}" || exit 1
./autogen.sh || exit 1
make -j4 || exit 1
make dist || exit 1
