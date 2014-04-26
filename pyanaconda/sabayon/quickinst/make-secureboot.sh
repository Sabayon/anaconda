#!/bin/bash
#
# As per specs available upstream and this blog post:
# http://blog.hansenpartnership.com/uefi-secure-boot/
#
# The private key is passwordless and NOT encrypted
#
# Call this script this way:
#
# $ make-secureboot.sh <private key> <public cert out> <public der cert out>
#
# <public der cert out> must end with .cer

PRIVATE_KEY="${1}"
PUBLIC_x509="${2}"
PUBLIC_DER="${3}"
shift 3

# We don't give a shit about SecureBoot, let's
# make our cert last forever
openssl req -batch \
	-new -x509 -newkey rsa:2048 -nodes \
	-keyout "${PRIVATE_KEY}" -out "${PUBLIC_x509}" \
	-days $((365 * 50)) \
	-subj "/CN=Sabayon User/" || exit 1

# now transform PUBLIC_x509 in binary DER format
openssl x509 -in "${PUBLIC_x509}" -out "${PUBLIC_DER}" -outform DER || exit 1
openssl rsa -in "${PRIVATE_KEY}" -out "${PRIVATE_KEY}".less || exit 1
mv "${PRIVATE_KEY}".less "${PRIVATE_KEY}" || exit 1

chmod 400 "${PRIVATE_KEY}" || exit 1

echo "The SecureBoot Sabayon User certificate is ${PUBLIC_DER}, enjoy"
