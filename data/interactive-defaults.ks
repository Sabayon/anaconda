# Kickstart defaults file for an interactive install.
# This is not loaded if a kickstart file is provided on the command line.
auth --enableshadow --passalgo=sha512
bootloader --location=mbr
firstboot --enable
