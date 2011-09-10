#!/bin/sh

PNG_DIR=../

# clean old pngs
git rm -f "${PNG_DIR}"*.png &> /dev/null

# convert svg to png
for file in *.svg; do
	fname="${file%/}"
	if [ "${fname}" = "rnote.svg" ]; then
		continue
	fi
	echo "doing ${fname}"
	out_file="${PNG_DIR}"/$(basename "${fname/svg/png}")
	inkscape --export-area-page --export-png="${out_file}" "${file}" \
		--without-gui || exit 1
	git add "${out_file}" || exit 1
done
