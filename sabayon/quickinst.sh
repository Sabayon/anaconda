#!/bin/sh
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
# Live Image default user name
LIVE_USER="${LIVE_USER:-sabayonuser}"
# NetworkManager networking? "1" for Yes, "0" for No
NM_NETWORK="${NM_NETWORK:-1}"
# Sabayon Media Center mode? "1" for Yes, "0" for No
SABAYON_MCE="${SABAYON_MCE:-0}"
# Firewall configuration, enable firewall? "1" for Yes, "0" for No
FIREWALL="${FIREWALL:-1}"
FIREWALL_PACKAGE="net-firewall/ufw"
FIREWALL_SERVICE="ufw"

# This function prints a separator line
separator() {
    echo "==============================================="
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
        "${user}" || exit 1
}

# Setup root user settings (password, etc)
# Signature: setup_root_user <chroot> <root pass>
setup_root_user() {
    local _chroot="${1}"
    local root_pass="${2}"
    echo "root:${root_pass}" | exec_chroot "${_chroot}" chpasswd \
        || return ${?}
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

    if [ ! -d "${_desktop_dir}" ]; then
        mkdir -p "${_desktop_dir}" || return ${?}
    fi
    if [ ! -d "${_autost_dir}" ]; then
        mkdir -p "${_autost_dir}" || return ${?}
    fi

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
    for cruft in ${cruft_desktops}; do
        rm -f "${_skel_dir}/Desktop/${cruft}.desktop"
    done

    # Install welcome loader
    local welcome_name="sabayon-welcome-loader.desktop"
    local welcome_desktop="${_chroot}/etc/sabayon/${welcome_name}"
    if [ -f "${wecome_desktop}" ]; then
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
    setup_root_user "${_chroot}" "${root_pass}" || return ${?}
}

# Setup language
# Signature: setup_language <chroot> <lang>
setup_language() {
    local _chroot="${1}"

    local _lang="en_US.UTF-8"  # default to en_US
    local lang_file="/etc/env.d/02locale"
    local chroot_lang_file="${_chroot}/${lang_file}"
    if [ -f "${lang_file}" ]; then
        _lang=$(. "${lang_file}" && echo "${LANG}")
        cat "${lang_file}" > "${chroot_lang_file}" || return ${?}
    fi

    # write locale.gen
    local sup_file="${_chroot}/usr/share/i18n/SUPPORTED"
    if [ -e "${sup_file}" ]; then
        local libc_locale="${_lang/.*}"
        libc_locale="${_lang/@*}"

        local valid_locales=()
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

    # copy consolefont over from live system as well
    local console_file="/etc/conf.d/consolefont"
    local chroot_console_file="${_chroot}/${console_file}"
    if [ -f "${console_file}" ]; then
        cat "${console_file}" > "${chroot_console_file}" || return ${?}
    fi

    # Setup LibreOffice (openoffice...) and other DEs languages
    for opt in kde openoffice mozilla; do
        exec_chroot "${_chroot}" /sbin/language-setup \
            "${_lang/.*}" "${opt}"  &> /dev/null  # ignore failure
    done
}


# Setup networking
# Signature: setup_network <chroot>
setup_network() {
    local _chroot="${1}"

    if [ "${NM_NETWORK}" = "1" ]; then
        exec_chroot "${_chroot}" rc-update del \
            netmount default &> /dev/null
        exec_chroot "${_chroot}" rc-update del \
            nfsmount default &> /dev/null
    else
        exec_chroot "${_chroot}" rc-update del \
            NetworkManager default &> /dev/null
        exec_chroot "${_chroot}" rc-update del \
            NetworkManager-setup default &> /dev/null
        exec_chroot "${_chroot}" rc-update del \
            avahi-daemon default &> /dev/null
        exec_chroot "${_chroot}" rc-update del \
            dhcdbd default &> /dev/null

        local _rc_conf="${_chroot}/etc/rc.conf"
        if [ -f "${_rc_conf}" ]; then
            sed -i 's/^#rc_hotplug=".*"/rc_hotplug="*"/g' \
                "${_rc_conf}" || return ${?}
            sed -i 's/^rc_hotplug=".*"/rc_hotplug="*"/g' \
                "${_rc_conf}" || return ${?}
        fi
    fi
}


# Configure keyboard mappings
# Signature: setup_keyboard <chroot>
setup_keyboard() {
    local _chroot="${1}"

    local _key_map="us"  # default to US keymap
    local key_file="/etc/conf.d/keymaps"
    local chroot_key_file="${_chroot}/${key_file}"
    if [ -f "${key_file}" ]; then
        _key_map=$(. "${key_file}" && echo "${keymap}")
        cat "${key_file}" > "${chroot_key_file}" || return ${?}
    fi

    # run keyboard-setup directly inside chroot
    for opt in e17 gnome kde lxde system xfce xorg; do
        exec_chroot "${_chroot}" /sbin/keyboard-setup-2 \
            "${_key_map}" "${opt}"  &>/dev/null  # ignore failure
    done
}


# Configure sudo
# Signature: setup_sudo <chroot>
setup_sudo() {
    local _chroot="${1}"

    local _sudo_file="/etc/sudoers"
    local chroot_sudo_file="${_chroot}/${_sudo_file}"
    if [ -f "${chroot_sudo_file}" ]; then
        sed -i "/NOPASSWD/ s/^#/" "${chroot_sudo_file}" || return ${?}
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
    if [ "${gl_profile}" = "xorg-x11" ]; then
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

        for gl_path in "${gl_paths[@]}"; do
            rm -rf "${_chroot}/${gl_path}"
        done
        exec_chroot equo remove "${prop_packages[@]}" || return ${?}
    fi

    local _mod_conf="/etc/conf.d/modules"
    local chroot_mod_conf="${_chroot}/${_mod_conf}"
    # created by gpu-detector
    if [ -f "/tmp/.radeon.kms" ]; then
        # (<3.6.0 kernel) since CONFIG_DRM_RADEON_KMS=n on our kernel
        # we need to force radeon to load at boot
        echo >> "${chroot_mod_conf}" || return ${?}
        echo "# Added by the Sabayon Installer to force radeon.ko load" \
            >> "${chroot_mod_conf}" || return ${?}
        echo "# since CONFIG_DRM_RADEON_KMS is not enabled by default at" \
            >> "${chroot_mod_conf}" || return ${?}
        echo "# this time" >> "${chroot_mod_conf}" || return ${?}
        echo "modules=\"radeon\"" >> "${chroot_mod_conf}" || return ${?}
        echo "module_radeon_args=\"modeset=1\"" \
            >> "${chroot_mod_conf}" || return ${?}
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
    exec_chroot "${_chroot}" equo remove \
        nvidia-drivers nvidia-userspace  || return ${?}

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
        if [ ! -d "${chroot_xorg_file_dir}" ]; then
            mkdir -p "${chroot_xorg_file_dir}" || return ${?}
        fi
        cat "${_xorg_file}" > "${chroot_xorg_file}" || return ${?}
        cp -p "${chroot_xorg_file}" "${chroot_xorg_file}.original" \
            || return ${?}
    fi
    _remove_proprietary_drivers "${_chroot}" || return ${?}
    _setup_nvidia_legacy "${_chroot}" || return ${?}
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
        if [ ! -d "${chroot_state_dir}" ]; then
            mkdir -p "${chroot_state_dir}" || return ${?}
        fi
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
        exec_chroot "${_chroot}" \
            rc-update del ${srv} boot default &>/dev/null
    done

    exec_chroot "${_chroot}" \
        rc-update add vixie-cron default &> /dev/null

    if [ ! -e "${_chroot}/etc/init.d/net.eth0" ]; then
        ln -sf net.lo "${_chroot}/etc/init.d/net.eth0" || return ${?}
    fi

    if [ -e "${_chroot}/etc/init.d/nfsmount" ]; then
        exec_chroot "${_chroot}" \
            rc-update add nfsmount default
    fi
    if [ -e "${_chroot}/etc/init.d/cdeject" ]; then
        exec_chroot "${_chroot}" \
            rc-update del cdeject shutdown
    fi
    if [ -e "${_chroot}/etc/init.d/oemsystem-boot" ]; then
        exec_chroot "${_chroot}" \
            rc-update add oemsystem-boot boot
    fi
    if [ -e "${_chroot}/etc/init.d/oemsystem-default" ]; then
        exec_chroot "${_chroot}" \
            rc-update add oemsystem-default default
    fi
    if [ "${SABAYON_MCE}" = "0" ]; then
        exec_chroot "${_chroot}" \
            rc-update del sabayon-mce boot default &>/dev/null
    fi
    if [ -e "${_chroot}/etc/init.d/dmcrypt" ]; then
        exec_chroot "${_chroot}" \
            rc-update add dmcrypt boot
    fi

    if _is_virtualbox; then
        exec_chroot "${_chroot}" \
            rc-update add virtualbox-guest-additions boot &>/dev/null
    else
        exec_chroot "${_chroot}" \
            rc-update del virtualbox-guest-additions boot &>/dev/null
    fi

    if [ "${FIREWALL}" = "1" ]; then
        exec_chroot "${_chroot}" \
            rc-update add "${FIREWALL_SERVICE}" default
    else
        exec_chroot "${_chroot}" \
            rc-update del "${FIREWALL_SERVICE}" boot default &>/dev/null
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
}


# Configure udev
# Signature: setup_udev <chroot>
setup_udev() {
    local _chroot="${1}"

    local tmp_dir=$(mktemp -d --suffix="quickinst_udev")
    if [ -z "${tmp_dir}" ]; then
        return 1
    fi

    mount --move "${_chroot}/dev" "${tmp_dir}" || return ${?}
    cp -Rp /dev/* "${_chroot}/dev/" || return ${?}
    mount --move "${tmp_dir}" "${_chroot}/dev" || return ${?}
    rm -rf "${tmp_dir}"
}


# Setup misc stuff, feel free to add here your crap
# Signature: setup_misc <chroot>
setup_misc() {
    local _chroot="${1}"

    exec_chroot "${_chroot}" /usr/sbin/env-update
    exec_chroot "${_chroot}" /usr/sbin/locale-gen
    exec_chroot "${_chroot}" /sbin/ldconfig

    # Fix a possible /tmp problem
    chmod a+w "${_chroot}/tmp"
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


# This is the main() function
main() {

    if [ "$(whoami)" != "root" ]; then
        echo "Y U NO root" >&2
        return 1
    fi
    if [ ${#} -lt 1 ]; then
        echo "Y U NO correct args" >&2
        echo "${0} <chroot path>" >&2
        return 1
    fi

    # NOTE: this implicitly sets language parameters
    /usr/sbin/env-update
    . /etc/profile

    local _chroot="${1}"
    # Overridable env vars
    # TODO(lxnay): input validation
    local _srcroot="${SRCROOT:-/mnt/livecd}"
    local _user="${QUSER:-geek}"
    local _user_pass="${QUSER_PASS:-geek}"
    local _root_pass="${QROOT_PASS:-keeg}"

    # Input validation
    for _dir in "${_chroot}" "${_srcroot}"; do
        if [ ! -d "${_dir}" ]; then
            echo "${_dir} is not a directory" >&2
            exit 1
        # TODO(lxnay): uncomment this before release
        #elif [ -n "$(ls -1 "${_dir}")" ] && \
        #    [ "${_dir}" = "${_chroot}" ]; then
        #    echo "${_dir} is not empty" >&2
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
    live_install "${_srcroot}" "${_chroot}" || return ${?}

    echo "System copy complete, configuring users"
    setup_users "${_chroot}" "${_root_pass}" "${_user}" "${_user_pass}" \
        || return ${?}

    echo "Configuring language..."
    setup_language "${_chroot}" || return ${?}

    echo "Configuring networking..."
    setup_network "${_chroot}" || return ${?}

    echo "Configuring keyboard mappings..."
    setup_keyboard "${_chroot}" || return ${?}

    echo "Configuring X.Org..."
    setup_xorg "${_chroot}" || return ${?}

    echo "Configuring audio..."
    setup_audio "${_chroot}" || return ${?}

    echo "Configuring sudo..."
    setup_sudo "${_chroot}" || return ${?}

    echo "Configuring services..."
    setup_services "${_chroot}" || return ${?}

    echo "Configuring udev..."
    setup_udev "${_chroot}" || return ${?}

    echo "Configuring misc stuff..."
    setup_misc "${_chroot}" || return ${?}

    echo "Configuring Entropy..."
    setup_entropy "${_chroot}" || return ${?}

    _emit_install_done || return ${?}

    # TODO: missing routines
    # - /etc/fstab configuration
    # - bootloader grub2 configuration (and mbr install?)
    # - language packs configuration

}

main "${@}" || exit ${?}