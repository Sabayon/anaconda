#!/bin/bash
#
# quickinst.sh
# Sabayon non-interactive install-to-chroot script
#
# Copyright (C) 2012 Fabio Erculiani
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

## Global variables
# The path of this script
QUICKINST_PATH="${0}"
# User name on installed system
QUSER=${QUSER:-geek}
# User's password on installed system
QUSER_PASS=${QUSER_PASS:-geek}
# Root's password on installed system
QROOT_PASS=${QROOT_PASS:-keeg}
# NetworkManager networking? "1" for Yes, "0" for No
NM_NETWORK="${NM_NETWORK:-1}"
# Sabayon Media Center mode? "1" for Yes, "0" for No
SABAYON_MCE="${SABAYON_MCE:-0}"
# Firewall configuration, enable firewall? "1" for Yes, "0" for No
FIREWALL="${FIREWALL:-1}"

## Global variables that one wouldn't normally want to modify
# Live Image default user name
LIVE_USER="${LIVE_USER:-sabayonuser}"
# Source path - where to copy data from
SRCROOT=${SRCROOT:-/mnt/livecd}
# Name of the firewall service
FIREWALL_SERVICE="firewalld"
# If source is a running system (otherwise it can be for example a mounted
# squashfs image) - "1" for yes, "0" for no
SOURCE_IS_LIVE_SYSTEM="1"

# This function prints a separator line
separator() {
    echo "==============================================="
}

# Print message on standard error
# Signature: warn <message>
warn() {
    echo "$*" >&2
}

# Inform about a failure (for exit status taken as parameter) and optionally
# with -v about success, optionally with label; returns given status
# Signature: inform_status [-v] <exit status> [label]
inform_status() {
    local verbose=0
    local status=${1}
    if [[ ${status} = -v ]]; then
        verbose=1
        shift
        status=${1}
    fi
    local label=${2}
    [[ -n ${label} ]] && label="${label}: "

    if [[ ${status} -eq 0 ]]; then
        [[ ${verbose} = 1 ]] && echo "${label}OK"
    else
        echo "${label}FAIL; exit status is ${status}"
    fi

    return ${status}
}

# Returns 0 if directory is empty, otherwise (non empty, not a directory,
# permission error) returns non-true value
# Signature: is_empty_dir <directory>
is_empty_dir() {
    local dir=${1}
    [[ -d ${1} ]] || return 1
    (
        shopt -s dotglob nullglob
        a=( "${dir}"/* )
        (( ${#a[@]} == 0 ))
    )
}

# Enables the given systemd service.
# Signature: sd_enable <chroot> <service name, without .service>
sd_enable() {
    local _chroot="${1}"
    local srv="${2}"
    [[ -x "${_chroot}/usr/bin/systemctl" ]] && \
        chroot "${_chroot}" /usr/bin/systemctl \
            --no-reload enable "${srv}.service"
}

# Disables the given systemd service.
# Signature: sd_disable <chroot> <service name, without .service>
sd_disable() {
    local _chroot="${1}"
    local srv="${2}"
    [[ -x "${_chroot}/usr/bin/systemctl" ]] && \
        chroot "${_chroot}" /usr/bin/systemctl \
            --no-reload disable "${srv}.service"
}

# Returns 0 if package is installed on system, 1 otherwise, 2 on error
# <package name> can be any value accepted by equo match (it can contain
# version string for example)
# Signature: is_package_installed <chroot path> <package name>
is_package_installed() {
    local _chroot=${1}
    local pkg=${2}

    if [[ $# -ne 2 ]]; then
        warn "ERROR: is_package_installed required 2 arguments - $# given"
        return 2
    fi

    local output
    output=$( exec_chroot "${_chroot}" \
        equo match --installed --quiet -- "${pkg}" )

    if [[ -n ${output} ]]; then
        return 0
    else
        return 1
    fi
}

# Execute a command inside chroot
# Signature: exec_chroot <chroot path> <command ...>
exec_chroot() {
    local _chroot="${1}"
    shift
    chroot "${_chroot}" "${@}"
}

# Copy source directory to destination
# Signature: live_install <source> <dest>
live_install() {
    local src="${1}"
    local dst="${2}"
    rsync -a --delete-during -H -A -X -x "${src}/" "${dst}/"
    return ${?}
}

# Get live user groups
# Signature: live_user_groups
live_user_groups() {
    # TODO(lxnay): uncomment this before release
    # groups "${LIVE_USER}"
    echo "users wheel"
}

# Create user in chroot
# Signature: create_user <chroot> <user>
create_user() {
    local _chroot="${1}"
    local user="${2}"

    exec_chroot "${_chroot}" useradd \
        -d "/home/${user}" \
        -k /etc/skel \
        -g users \
        -G "$(live_user_groups | sed "s: :,:g")" \
        -m \
        "${user}" || return 1
}

# Setup user's password in chroot
# Signature: set_user_password <chroot> <login> <password>
set_user_password() {
    local _chroot="${1}"
    local login="${2}"
    local password="${3}"
    # TODO: some validation
    echo "${login}:${password}" | exec_chroot "${_chroot}" chpasswd
}

# Delete live image user from chroot if exists
# Signature: delete_live_user <chroot>
delete_live_user() {
    local _chroot="${1}"

    exec_chroot "${_chroot}" groups "${LIVE_USER}" &>/dev/null
    if [ "${?}" = "0" ]; then
        # Assume user exists
        exec_chroot "${_chroot}" userdel -f -r "${LIVE_USER}" \
            || return ${?}
    fi
}

# Configure skel dir in chroot
# Signature: configure_skel <chroot>
configure_skel() {
    local _chroot="${1}"
    local _skel_dir="${_chroot}/etc/skel"
    local _desktop_dir="${_skel_dir}/Desktop"
    local _autost_dir="${_desktop_dir}/.config/autostart"

    mkdir -p "${_desktop_dir}" || return ${?}
    mkdir -p "${_autost_dir}" || return ${?}

    # Setup Rigo
    local rigo_name="rigo.desktop"
    local rigo_desktop="${_chroot}/usr/share/applications/${rigo_name}"
    local skel_rigo_desktop="${_desktop_dir}/${rigo_name}"
    if [ -f "${rigo_desktop}" ]; then
        cp "${rigo_desktop}" "${skel_rigo_desktop}" || return ${?}
        chmod 0775 "${skel_rigo_desktop}" || return ${?}
        chown root:root "${skel_rigo_desktop}" || return ${?}
    fi

    # Cleanup cruft
    local cruft_desktops="gparted liveinst"
    local cruft
    for cruft in ${cruft_desktops}; do
        rm -f "${_skel_dir}/Desktop/${cruft}.desktop"
    done

    # Install welcome loader
    local welcome_name="sabayon-welcome-loader.desktop"
    local welcome_desktop="${_chroot}/etc/sabayon/${welcome_name}"
    if [ -f "${welcome_desktop}" ]; then
        cp -p "${welcome_desktop}" "${_autost_dir}/${welcome_name}" \
            || return ${?}
    fi
}

# Setup users (root and default user)
# Signature: setup_users <chroot> <root pass> <user> <user pass>
setup_users() {
    local _chroot="${1}"
    local root_pass="${2}"
    local user="${3}"
    local user_pass="${4}"

    # delete LIVE_USER first
    delete_live_user "${_chroot}" || return ${?}

    # configure skel for ${user}
    configure_skel "${_chroot}" || return ${?}
    create_user "${_chroot}" "${user}" || return ${?}

    # setup passwords
    set_user_password "${_chroot}" "${user}" "${user_pass}" || return ${?}
    set_user_password "${_chroot}" "root" "${root_pass}" || return ${?}
}

# Setup language
# Signature: setup_language <chroot> <lang>
setup_language() {
    local _chroot="${1}"

    local _lang="en_US.UTF-8"  # default to en_US
    local lang_file="/etc/env.d/02locale"
    local locale_conf_file="/etc/locale.conf"
    local chroot_lang_file="${_chroot}/${lang_file}"
    local chroot_locale_conf_file="${_chroot}/${locale_conf_file}"
    if [ -f "${lang_file}" ]; then
        _lang=$(. "${lang_file}" && echo "${LANG}")
        cat "${lang_file}" > "${chroot_lang_file}" || return ${?}
        cat "${locale_conf_file}" > "${chroot_locale_conf_file}" || return ${?}
    fi

    # write locale.gen
    local sup_file="${_chroot}/usr/share/i18n/SUPPORTED"
    if [ -e "${sup_file}" ]; then
        local libc_locale="${_lang/.*}"
        libc_locale="${_lang/@*}"

        local valid_locales=()
        local loc
        while read loc; do
            if [[ "${loc}" == ${libc_locale}* ]]; then
                valid_locales+=( "${loc}" )
            fi
        done < "${sup_file}"

        local loc_gen="${_chroot}/etc/locale.gen"
        echo "en_US.UTF-8 UTF-8" > "${loc_gen}" || return ${?}
        for loc in "${valid_locales[@]}"; do
            echo "${loc}" >> "${loc_gen}" || return ${?}
        done
    fi

    return 0 # ignore failures in the loop above
}


# Setup networking
# Signature: setup_network <chroot>
setup_network() {
    local _chroot="${1}"

    if [ "${NM_NETWORK}" = "1" ]; then
        sd_enable "${_chroot}" NetworkManager
    else
        sd_disable "${_chroot}" NetworkManager
        sd_disable "${_chroot}" NetworkManager-wait-online

        sd_disable "${_chroot}" NetworkManager
        sd_disable "${_chroot}" NetworkManager-wait-online

        local _rc_conf="${_chroot}/etc/rc.conf"
        if [ -f "${_rc_conf}" ]; then
            sed -i 's/^#rc_hotplug=".*"/rc_hotplug="*"/g' \
                "${_rc_conf}" || return ${?}
            sed -i 's/^rc_hotplug=".*"/rc_hotplug="*"/g' \
                "${_rc_conf}" || return ${?}
        fi
    fi

    # ignore failures
    return 0
}


# Configure keyboard mappings
# Signature: setup_keyboard <chroot>
setup_keyboard() {
    local _chroot="${1}"

    local _key_map="us"  # default to US keymap

    # run keyboard-setup directly inside chroot
    local opt
    for opt in e17 gnome kde lxde system xfce xorg; do
        exec_chroot "${_chroot}" /sbin/keyboard-setup-2 \
            "${_key_map}" "${opt}" &>/dev/null
    done
    return 0 # ignore failure in the loop above
}


# Configure sudo
# Signature: setup_sudo <chroot>
setup_sudo() {
    local _chroot="${1}"

    local _sudo_file="/etc/sudoers"
    local chroot_sudo_file="${_chroot}/${_sudo_file}"
    if [ -f "${chroot_sudo_file}" ]; then
        sed -i "/NOPASSWD/ s/^#//" "${chroot_sudo_file}" || return ${?}
        echo >> "${chroot_sudo_file}" || return ${?}
        echo "# Added by Sabayon Alt Installer" \
            >> "${chroot_sudo_file}" || return ${?}
        echo "%wheel  ALL=ALL" \
            >> "${chroot_sudo_file}" || return ${?}
    fi
}


# Remove proprietary drivers if not needed
# Signature: _remove_proprietary_drivers <chroot>
_remove_proprietary_drivers() {
    local _chroot="${1}"

    local gl_profile=$(eselect opengl show)
    local bb_enabled=0
    [[ -e "/tmp/.bumblebee.enabled" ]] && bb_enabled=1

    if [ "${gl_profile}" = "xorg-x11" ] && [ "${bb_enabled}" = "0" ]; then
        local gl_paths=(
            "/etc/env.d/09ati"
            "/usr/lib/opengl/ati"
            "/usr/lib/opengl/nvidia"
        )
        local prop_packages=(
            "media-video/nvidia-settings"
            "x11-drivers/ati-drivers"
            "x11-drivers/ati-userspace"
            "x11-drivers/nvidia-drivers"
            "x11-drivers/nvidia-userspace"
        )

        local gl_path
        for gl_path in "${gl_paths[@]}"; do
            rm -rf "${_chroot}/${gl_path}"
        done

        local prop_packages_to_remove=()
        local pkg
        for pkg in "${prop_packages[@]}"; do
            if is_package_installed "${_chroot}" "${pkg}"; then
                prop_packages_to_remove+=( "${pkg}" )
            else
                echo "${pkg} already not installed"
            fi
        done

        if [[ ${#prop_packages_to_remove[@]} -eq 0 ]]; then
            echo "No packages to remove."
            return 0
        fi

        local ret
        exec_chroot "${_chroot}" \
            equo remove "${prop_packages_to_remove[@]}"
        ret=${?}
        if [[ ${ret} -ne 0 ]]; then
            warn "error: command 'equo remove ${prop_packages_to_remove[*]}'"
            warn "failed with exit status ${ret}"
            return ${ret}
        fi
    fi

    if [ "${bb_enabled}" = "1" ]; then
        sd_enable "${_chroot}" bumblebeed
    fi
}

# Setup NVIDIA legacy drivers
# Signature: _setup_nvidia_legacy <chroot>
_setup_nvidia_legacy() {
    local _chroot="${1}"

    local running_file="/lib/nvidia/legacy/running"
    local drivers_dir="/install-data/drivers"
    if [ ! -f "${running_file}" ]; then
        return 0
    fi
    if [ ! -f "${drivers_dir}" ]; then
        return 0
    fi

    # remove current
    local packages_to_remove=()
    local pkg_to_remove
    for pkg_to_remove in nvidia-drivers nvidia-userspace; do
        if is_package_installed "${_chroot}" "${pkg_to_remove}"; then
            packages_to_remove+=( "${pkg_to_remove}" )
        else
            echo "${pkg_to_remove} already not installed"
        fi
    done

    local ret
    if [[ ${#packages_to_remove[@]} -eq 0 ]]; then
        echo "No packages to remove."
    else
        exec_chroot "${_chroot}" equo remove "${packages_to_remove[@]}"
        ret=${?}
        if [[ ${ret} -ne 0 ]]; then
            warn "error: command 'equo remove ${packages_to_remove[*]}'"
            warn "failed with exit status ${ret}"
            return ${ret}
        fi
    fi

    local nv_ver=$(cat "${running_file}")
    local ver=
    if [[ "${nv_ver}" == 17* ]]; then
        ver="17*"
    elif [[ "${nv_ver}" == 9* ]]; then
        ver="9*"
    else
        ver="7*"
    fi

    local nvidia_pkgs=(
        "x11-drivers:nvidia-drivers-${ver}"
        "x11-drivers:nvidia-userspace-${ver}"
    )
    local nvidia_pkg_files=()
    local drv_file_name=

    local drv_file pkg_file
    for drv_file in "${drivers_dir}"/*; do
        drv_file_name=$(basename "${drv_file}")

        for pkg_file in "${nvidia_pkgs[@]}"; do
            if [[ "${drv_file_name}" == "${pkg_file}"* ]]; then
                nvidia_pkg_files+=( "${drv_file}" )
            fi
        done
    done

    local nvidia_file_name=
    local tmp_pkg_file=

    local nvidia_pkg_file
    for nvidia_pkg_file in "${nvidia_pkg_files[@]}"; do
        nvidia_file_name=$(basename "${nvidia_pkg_file}")
        tmp_pkg_file="/tmp/${nvidia_file_name}"

        cp "${nvidia_file_name}" "${_chroot}/${tmp_pkg_file}" \
            || return ${?}
        exec_chroot "${_chroot}" equo install "${tmp_pkg_file}" \
            || return ${?}

        rm -f "${_chroot}/${tmp_pkg_file}"
    done

    # first mask all the pkgs
    exec_chroot "${_chroot}" equo mask \
        x11-drivers/nvidia-drivers \
        x11-drivers/nvidia-userspace || return ${?}
    # then unmask
    exec_chroot "${_chroot}" equo unmask \
        "=x11-drivers/nvidia-drivers-${ver}*" \
        "=x11-drivers/nvidia-userspace-${ver}*" \
        || return ${?}

    # fixup opengl
    exec_chroot "${_chroot}" eselect opengl set xorg-x11 &>/dev/null
    exec_chroot "${_chroot}" eselect opengl set nvidia &>/dev/null

    return 0
}


# Return 0 if system is running inside VirtualBox
_is_virtualbox() {
    lspci -n | grep " 80ee:" &> /dev/null
    return ${?}
}


# We're done installing!
_emit_install_done() {
    python -c "
from entropy.client.interfaces import Client
client = Client()
factory = client.WebServices()
webserv = factory.new('sabayonlinux.org')
webserv.add_downloads(['installer'])
client.shutdown()
"
}


# Configure X.Org
# Signature: setup_xorg <chroot>
setup_xorg() {
    local _chroot="${1}"

    local _xorg_file="/etc/X11/xorg.conf"
    local chroot_xorg_file="${_chroot}/${_xorg_file}"
    local chroot_xorg_file_dir="$(dirname "${chroot_xorg_file}")"

    if [ -f "${_xorg_file}" ]; then
        mkdir -p "${chroot_xorg_file_dir}" || return ${?}
        cat "${_xorg_file}" > "${chroot_xorg_file}" || return ${?}
        cp -p "${chroot_xorg_file}" "${chroot_xorg_file}.original" \
            || return ${?}
    fi

    _remove_proprietary_drivers "${_chroot}"
    inform_status ${?} "_remove_proprietary_drivers" || return ${?}

    _setup_nvidia_legacy "${_chroot}"
    inform_status ${?} "_setup_nvidia_legacy" || return ${?}
}


# Configure audio
# Signature: setup_audio <chroot>
setup_audio() {
    local _chroot="${1}"

    local _asound_state="/etc/asound.state"
    local _asound_state2="/var/lib/alsa/asound.state"

    local state_file= chroot_state_file= chroot_state_dir=
    for state_file in "${_asound_state}" "${_asound_state2}"; do
        if [ ! -f "${state_file}" ]; then
            continue  # file not found, deny deny deny
        fi

        chroot_state_file="${_chroot}/${state_file}"
        chroot_state_dir=$(dirname "${chroot_state_file}")
        mkdir -p "${chroot_state_dir}" || return ${?}
        cat "${state_file}" > "${chroot_state_file}" || return ${?}
    done
}

# Configure services
# Signature: setup_services <chroot>
setup_services() {
    local _chroot="${1}"

    local srvs=(
        "installer-gui"
        "installer-text"
        "music"
        "sabayonlive"
    )
    local srv=
    for srv in "${srvs[@]}"; do
        sd_disable "${_chroot}" ${srv}
    done

    sd_enable "${_chroot}" vixie-cron

    sd_disable "${_chroot}" cdeject &> /dev/null # may not be avail.

    sd_enable "${_chroot}" oemsystem &> /dev/null # may not be avail.

    if [ "${SABAYON_MCE}" = "0" ]; then
        sd_disable "${_chroot}" sabayon-mce
    fi

    if _is_virtualbox; then
        sd_enable "${_chroot}" virtualbox-guest-additions
    else
        sd_disable "${_chroot}" virtualbox-guest-additions
    fi

    if [ "${FIREWALL}" = "1" ]; then
        sd_enable "${_chroot}" "${FIREWALL_SERVICE}"
    else
        sd_disable "${_chroot}" "${FIREWALL_SERVICE}"
    fi

    # XXX: hack
    # For GDM, set DefaultSession= to /etc/skel/.dmrc value
    # This forces GDM to respect the default session and load Cinnamon
    # as default xsession. (This is equivalent of using:
    # /usr/libexec/gdm-set-default-session
    local custom_gdm="${_chroot}/etc/gdm/custom.conf"
    local skel_dmrc="${_chroot}/etc/skel/.dmrc"
    local current_session=

    if [ -f "${custom_gdm}" ] && [ -f "${skel_dmrc}" ]; then
        current_session=$(cat "${skel_dmrc}" | grep "^Session" \
            | cut -d= -f2)
    fi

    if [ -n "${current_session}" ]; then
        # ConfigParser is much more reliable
        python -c "
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser

gdm_config = ConfigParser.ConfigParser()
gdm_config.optionxform = str
custom_gdm = '"${custom_gdm}"'
if custom_gdm in gdm_config.read(custom_gdm):
    gdm_config.set('daemon', 'DefaultSession', '"${current_session}"')
    with open(custom_gdm, 'w') as gdm_f:
        gdm_config.write(gdm_f)
"
    fi

    # drop /install-data now, bug 4019
    local install_data_dir="${_chroot}/install-data"
    rm -rf "${install_data_dir}"
}


# Configure udev
# Signature: setup_udev <chroot>
setup_udev() {
    local _chroot="${1}"

    local tmp_dir=$(mktemp -d --suffix="quickinst_udev")
    if [ -z "${tmp_dir}" ]; then
        return 1
    fi

    if [[ ${SOURCE_IS_LIVE_SYSTEM} = 1 ]]; then
        # Installing from a running system (such like a Live CD)
        mount --move "${_chroot}/dev" "${tmp_dir}" || return ${?}
    fi

    cp -Rp /dev/* "${_chroot}/dev/" || return ${?}

    if [[ ${SOURCE_IS_LIVE_SYSTEM} = 1 ]]; then
        mount --move "${tmp_dir}" "${_chroot}/dev" || return ${?}
    fi
    rm -rf "${tmp_dir}"
}


# Configure SecureBoot
# Signature: setup_secureboot <chroot>
setup_secureboot() {
    local _chroot="${1}"

    modprobe efivars 2> /dev/null
    if [ ! -d "/sys/firmware/efi" ]; then
        # Nothing to do
        return 0
    fi

    # TODO(lxnay): this expects to find /boot/efi/
    # directory mounted inside the chroot
    efi_dir="${_chroot}/boot/efi"

    local _private="${_chroot}/boot/SecureBoot/user-private.key"
    local _public="${_chroot}/boot/SecureBoot/user-public.crt"
    # TODO(lxnay): assume that collisions do not happen
    local _der="${efi_dir}/EFI/sabayon/enroll-this.cer"

    local _dir=
    for path in "${_private}" "${_public}" "${_der}"; do
        _dir=$(dirname "${path}")
        if [ ! -d "${_dir}" ]; then
            mkdir -p "${_dir}" || return ${?}
        fi
    done

    make_script=$(dirname "${QUICKINST_PATH}")/make-secureboot.sh
    "${make_script}" "${_private}" "${_public}" "${_der}" || return ${?}
}


# Setup misc stuff, feel free to add here your crap
# Signature: setup_misc <chroot>
setup_misc() {
    local _chroot="${1}"

    exec_chroot "${_chroot}" /usr/sbin/env-update
    exec_chroot "${_chroot}" /usr/sbin/locale-gen
    exec_chroot "${_chroot}" /sbin/ldconfig

    # Fix a possible /tmp problem
    chmod a+w,o+t "${_chroot}/tmp"
    # make sure we have .keep files around
    # this was an old Entropy bug.
    mkdir -p "${_chroot}/var/tmp"
    touch "${_chroot}/var/tmp/.keep"
}


# Setup Entropy stuff
# Signature: setup_entropy <chroot>
setup_entropy() {
    local _chroot="${1}"

    # this is Entropy 151, remove 2>/dev/null in future
    local repo_list=$(equo repo list --quiet 2>/dev/null)
    local _repo=
    for _repo in ${repo_list}; do
        exec_chroot "${_chroot}" equo repo mirrorsort "${_repo}"
    done

    return 0
}


# This is the installer_main() function
installer_main() {

    if [ "$(whoami)" != "root" ]; then
        warn "Y U NO root"
        return 1
    fi
    if [ ${#} -lt 1 ]; then
        warn "Y U NO correct args"
        warn "${0} <chroot path>"
        return 1
    fi

    # NOTE: this implicitly sets language parameters
    /usr/sbin/env-update
    . /etc/profile

    local _chroot="${1}"
    # Overridable env vars
    # TODO(lxnay): input validation
    local _srcroot="${SRCROOT}"
    local _user="${QUSER}"
    local _user_pass="${QUSER_PASS}"
    local _root_pass="${QROOT_PASS}"

    # Input validation
    local _dir
    for _dir in "${_chroot}" "${_srcroot}"; do
        if [ ! -d "${_dir}" ]; then
            warn "${_dir} is not a directory"
            return 1
        # TODO(lxnay): uncomment this before release; use is_empty_dir
        #elif [ -n "$(ls -1 "${_dir}")" ] && \
        #    [ "${_dir}" = "${_chroot}" ]; then
        #    warn "${_dir} is not empty"
        #    return 1
        fi
    done

    echo "Y U WANT quickinst.sh, welcome"
    separator

    echo "System settings:"
    echo "Default user: ${_user} (override via: QUSER)"
    echo "Default user password: ${_user_pass} (override via: QUSER_PASS)"
    echo "Default root password: ${_root_pass} (override via: QROOT_PASS)"
    separator

    echo "Copying system:  ${_srcroot} -> ${_chroot}"
    echo "Please wait, this will take 10-15 minutes"
    live_install "${_srcroot}" "${_chroot}"
    inform_status ${?} || return ${?}

    echo "System copy complete, configuring users"
    setup_users "${_chroot}" "${_root_pass}" "${_user}" "${_user_pass}"
    inform_status ${?} || return ${?}

    echo "Configuring language..."
    setup_language "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring networking..."
    setup_network "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring keyboard mappings..."
    setup_keyboard "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring X.Org..."
    setup_xorg "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring audio..."
    setup_audio "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring sudo..."
    setup_sudo "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring services..."
    setup_services "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring udev..."
    setup_udev "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring SecureBoot..."
    setup_secureboot "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring misc stuff..."
    setup_misc "${_chroot}"
    inform_status ${?} || return ${?}

    echo "Configuring Entropy..."
    setup_entropy "${_chroot}"
    inform_status ${?} || return ${?}

    _emit_install_done
    inform_status ${?} "_emit_install_done" || return ${?}

    # TODO: missing routines
    # - /etc/fstab configuration
    # - bootloader grub2 configuration (and mbr install?)
    # - language packs configuration

}

# vim: expandtab
