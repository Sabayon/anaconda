#!/bin/bash

# iso-installer.sh
# Sabayon non-interactive install-to-chroot script, using ISO as source
#
# Copyright (C) 2012 Sławomir Nizio
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

if ! . "${0%/*}/quickinst.sh"; then
	echo "Couldn't source script!" >&2
	exit 2
fi

# Start the installation procedure!
# Signature: start_installation <source directory> <target directory>
start_installation() {
	local src=$1
	local chroot=$2

	SRCROOT="${src}" \
	SOURCE_IS_LIVE_SYSTEM="0" \
		installer_main "${chroot}"
}

# Print path where .iso has to be mounted (from where .squashfs will
# be read)
_get_ISO_mtp() {
	echo "/run/iso-installer-target"
}

# Mount ISO file; mount point defaults to $(_get_ISO_mtp) and is created
# when needed; mount point is intermediate, to get .squashfs image
# Signature: mount_iso <iso file> [mount point]
mount_iso() {
	local iso=$1
	local mntp_st1=$2
	[[ -z ${mntp_st1} ]] && mntp_st1=$(_get_ISO_mtp)

	if [[ ! -r ${iso} ]]; then
		warn "mount_iso: ${iso} doesn't exist or is not readable"
		return 1
	fi
	if [[ ${iso} != *.iso ]]; then
		warn "mount_iso: ${iso} name must end with .iso"
		return 1
	fi

	check_valid_mountpoint "${mntp_st1}" || return 1

	if ! mkdir -p "${mntp_st1}"; then
		warn "mkdir -p ${mntp_st1} failed"
		return 1
	fi

	# fixme: does it work for DVD too?
	mount -t iso9660 -o loop --source "${iso}" --target "${mntp_st1}"
	local ret=$?
	if [[ ${ret} -ne 0 ]]; then
		warn "mount_iso: error: mount exited with ${ret}"
		rmdir -- "${mntp_st1}"
		return 1
	fi
	return 0
}

# Mount ISO and squashfs, check SHA sum for squashfs image
# Signature: mount_media <iso> <mount point> <skip SHA check>
# When this function returns with error, make sure to call unmount_iso
# because mount_media may have mounted the .ISO before it failed
# (but not squashfs file).
# If <skip SHA check> is non empty, the check is skipped.
mount_media() {
	local iso=$1
	local target=$2
	local skip_sha_check=$3
	local ret

	check_valid_mountpoint "${target}" || return 1

	# ${target} is used as the final destination
	# we need to mount ISO first
	local mntp_st1=$(_get_ISO_mtp)

	if ! mount_iso "${iso}"; then
		return 1
	fi

	separator

	local sqfs=${mntp_st1}/livecd.squashfs
	local sqfs_sha256sum=${mntp_st1}/livecd.squashfs.sha256

	local x
	for x in "${sqfs}" "${sqfs_sha256sum}"; do
		if [[ ! -r "${x}" ]]; then
			warn "mount_media: cannot find or read '${x}'"
			return 1
		fi
	done

	if [[ -z ${skip_sha_check} ]]; then
		echo "Checking if .squashfs image has correct checksum..."
		cd "${mntp_st1}" || { warn "cd ${mntp_st1} failed :O"; return 1; }
		sha256sum -c -- "${sqfs_sha256sum}"
		ret=$?
		cd - > /dev/null || { warn "cd - failed :O"; return 1; }

		if [[ ${ret} -ne 0 ]]; then
			warn "ATTENTION!"
			warn "Checksum for ${sqfs} failed: sha256sum returned ${ret}."
			warn "Your ISO may be corrupted - aborting!"
			return 1
		else
			echo "OK."
		fi
	else
		warn "Warning: checking of SHA sum skipped."
	fi

	separator

	echo "Mounting .squashfs image (source=${sqfs}, target=${target})..."
	mount -t squashfs -o loop --source "${sqfs}" --target "${target}"
	ret=$?
	if [[ ${ret} -ne 0 ]]; then
		warn "mount_media: error: mount exited with ${ret} while trying"
		warn "to mount .squashfs file '${sqfs}'"
		return 1
	else
		echo "OK."
	fi

	return 0
}

# Unmount ISO file; mount point defaults to $(_get_ISO_mtp) and is removed
# with rmdir
# Signature: unmount_iso [mount point]
unmount_iso() {
	local mtp_st1=$1
	[[ -z ${mntp_st1} ]] && mntp_st1=$(_get_ISO_mtp)

	umount -- "${mntp_st1}" || return 1
	rmdir -- "${mntp_st1}"
	return 0 # exit status from rmdir is not important
}

# Unmount .squashfs and ISO filesystems
# Signature: unmount_media <mount point for .iso>
unmount_media() {
	local target=$1
	local mtp_st1=$(_get_ISO_mtp)
	local ret

	# unmount squashfs image
	umount -- "${target}"
	ret=$?
	if [[ ${ret} -ne 0 ]]; then
		warn "unmount_media: error: umount -- ${target} exited with ${ret}"
		return 1
	fi

	# unmount ISO
	unmount_iso
	ret=$?
	if [[ ${ret} -ne 0 ]]; then
		warn "unmount_media: error: umount_iso exited with ${ret}"
		return 1
	fi

	return 0
}

# Check if mount point is safe
# Signature: check_valid_mountpoint <dir>
check_valid_mountpoint() {
	local mountpoint=$1
	# simple anti-shoot-in-da-footer (might as well require empty dir.)
	local mtp_realpath=$(realpath "${mountpoint}")
	local mtp_invalid=( "" "/" "/tmp" "/usr" "/var" "/bin" "/lib"
		"/usr/bin" "/usr/lib" "/usr/share" "/home" "/run" "/var/run" )
	local x
	for x in "${mtp_invalid[@]}"; do
		if [[ ${x} = "${mtp_realpath}" ]]; then
			warn "Huh, mount point cannot be '${x}'!"
			return 1
		fi
	done
	return 0
}

main() {
	local ret
	local iso_source
	local mountpoint=/mnt/livecd # default argument
	local target_dir
	local skip_sha_check

	while (( $# )); do
		case $1 in
		--iso)
			shift
			iso_source=$1
			;;
		--mountpoint)
			shift
			mountpoint=$1
			;;
		--target)
			shift
			target_dir=$1
			;;
		--nocheck)
			skip_sha_check=1
			;;
		*)
			echo "options:"
			echo "--iso <iso> - .iso file to use"
			echo "--mountpoint <dir> - where to mount an .iso"
			echo "--target <dir> - target directory/chroot"
			echo "--nocheck - don't check SHA sum of .squashfs file"
			exit
		esac
		shift
	done

	if [[ -z ${iso_source} ]]; then
		warn "iso_source not defined; use --iso"
		exit 1
	elif [[ -z ${mountpoint} ]]; then
		warn "mount point not defined; use --mountpoint"
		exit 1
	elif [[ -z ${target_dir} ]]; then
		warn "target directory not defined; use --taret"
		exit 1
	fi

	if [[ ! -f ${iso_source} ]]; then
		warn "File '${iso_source}' does not exist."
		exit 1
	fi

	if [[ ! -d ${target_dir} ]]; then
		warn "Target '${target_dir}' does not exist or is not a directory."
		exit 1
	fi

	echo "calling mount_media"
	mount_media "${iso_source}" "${mountpoint}" "${skip_sha_check}"
	ret=$?
	if [[ ${ret} -ne 0 ]]; then
		warn "error: mount_media returned ${ret}"
		# It may have failed before mounting .ISO, so this may fail;
		# trying just in case.
		unmount_iso
		return 1
	fi

	separator

	echo "Starting installation..."
	start_installation "${mountpoint}" "${target_dir}"
	local inst_ret=$?
	if [[ ${inst_ret} -ne 0 ]]; then
		warn "error: installation procedure returned ${inst_ret}"
		# don't return here; let it unmount stuff below
	fi

	separator

	echo "calling unmount_media"
	unmount_media "${mountpoint}"
	ret=$?
	return $(( $? | ${inst_ret} ))
}

main "$@"
ret=$?
echo exit status: ${ret}
