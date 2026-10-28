#!/usr/bin/env bash
# Baltu automatizācija — starpniekserveris (proxy) Latvijas valsts datu servisiem.
#
# VZD kadastra u.c. valsts datu servisi atbild tikai Latvijas IP adresēm, bet
# aplikācija (Streamlit Cloud) darbojas ASV. Šis skripts uz Latvijas VPS uzliek
# Squid starpniekserveri ar paroli, kas laiž cauri TIKAI HTTPS pieprasījumus uz
# Latvijas valsts / LVM domēniem (*.gov.lv, *.kadastrs.lv, *.geolatvija.lv, *.lvm.lv,
# *.lvmgeo.lv). Pārbaudīts AlmaLinux 10 / RHEL saimei; strādā arī Ubuntu/Debian.
#
# Palaišana serverī (kā root):
#   curl -fsSL https://raw.githubusercontent.com/duukqq-cmyk/baltu-automatizacija/main/scripts/proxy_uzstadit.sh | bash
#
# Beigās skripts izdrukā rindu VZD_PROXY = "...", ko ieliek Streamlit -> Settings -> Secrets.
# Atkārtota palaišana ģenerē jaunu paroli (vecā vairs nederēs).
set -euo pipefail

PORTS="${PORTS:-38129}"
LIETOTAJS="baltu"
PAROLE="$(openssl rand -hex 16)"
PAROLU_FAILS="/etc/squid/baltu_passwd"
TESTA_URL="https://geo-dpps.viss.gov.lv/api/DPPSPackage/client/Zemes_vien_423_0p2RBZ/5cc09e19-a238-4a2e-8eac-3a05cefa050e?service=WFS&version=2.0.0&request=GetFeature&typeNames=cp:CadastralParcel&outputFormat=application/json&featureID=CP64560020029"

zina() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Palaid kā root"; exit 1; }

zina "1/5 Instalē Squid un rīkus"
if command -v dnf >/dev/null; then
  dnf -y -q install squid httpd-tools openssl policycoreutils-python-utils >/dev/null
  AUTH_PROG="$(ls /usr/lib64/squid/basic_ncsa_auth 2>/dev/null || ls /usr/lib/squid/basic_ncsa_auth)"
  SQUID_LIETOTAJS="squid"
else
  export DEBIAN_FRONTEND=noninteractive
  apt-get -qq update && apt-get -qq -y install squid apache2-utils openssl >/dev/null
  AUTH_PROG="/usr/lib/squid/basic_ncsa_auth"
  SQUID_LIETOTAJS="proxy"
fi

zina "2/5 Lietotājs un parole"
htpasswd -b -c -m "$PAROLU_FAILS" "$LIETOTAJS" "$PAROLE" >/dev/null 2>&1
chown "root:$SQUID_LIETOTAJS" "$PAROLU_FAILS"
chmod 640 "$PAROLU_FAILS"

zina "3/5 Squid konfigurācija (tikai Latvijas valsts domēni, tikai HTTPS)"
[ -f /etc/squid/squid.conf.orig ] || cp /etc/squid/squid.conf /etc/squid/squid.conf.orig
cat > /etc/squid/squid.conf <<EOF
# Baltu automatizācija — proxy uz Latvijas valsts datu servisiem (scripts/proxy_uzstadit.sh)
http_port ${PORTS}
visible_hostname baltu-proxy

auth_param basic program ${AUTH_PROG} ${PAROLU_FAILS}
auth_param basic realm baltu-proxy
auth_param basic credentialsttl 2 hours

acl atlauti_domeni dstdomain .gov.lv .kadastrs.lv .geolatvija.lv .lvm.lv .lvmgeo.lv
acl SSL_ports port 443
acl CONNECT method CONNECT
acl lietotaji proxy_auth REQUIRED

http_access deny manager
http_access deny !atlauti_domeni
http_access deny CONNECT !SSL_ports
http_access deny !CONNECT
http_access allow lietotaji
http_access deny all

cache deny all
forwarded_for delete
access_log stdio:/var/log/squid/access.log
EOF

if command -v semanage >/dev/null && [ "$(getenforce 2>/dev/null || echo Disabled)" != "Disabled" ]; then
  semanage port -a -t squid_port_t -p tcp "$PORTS" 2>/dev/null || semanage port -m -t squid_port_t -p tcp "$PORTS"
fi
squid -k parse >/dev/null 2>&1 || { squid -k parse; exit 1; }

zina "4/5 Ugunsmūris un palaišana"
if systemctl is-active --quiet firewalld; then
  firewall-cmd -q --permanent --add-port="${PORTS}/tcp" && firewall-cmd -q --reload
elif command -v ufw >/dev/null && ufw status | grep -q active; then
  ufw allow "${PORTS}/tcp" >/dev/null
fi
systemctl enable -q squid
systemctl restart squid
sleep 2

# Aizsardzība pret SSH paroļu minēšanu (ja pieejams)
if command -v dnf >/dev/null; then
  (dnf -y -q install epel-release >/dev/null 2>&1 && dnf -y -q install fail2ban >/dev/null 2>&1) || true
else
  apt-get -qq -y install fail2ban >/dev/null 2>&1 || true
fi
if command -v fail2ban-client >/dev/null; then
  printf '[sshd]\nenabled = true\nmaxretry = 5\nbantime = 1h\n' > /etc/fail2ban/jail.d/baltu-sshd.local
  systemctl enable -q --now fail2ban 2>/dev/null || true
  systemctl restart fail2ban 2>/dev/null || true
fi

zina "5/5 Pārbaude"
REZ="$(curl -s -m 25 -x "http://${LIETOTAJS}:${PAROLE}@127.0.0.1:${PORTS}" "$TESTA_URL" | head -c 30 || true)"
BEZ_PAROLES="$(curl -s -o /dev/null -w '%{http_connect}' -m 10 -x "http://127.0.0.1:${PORTS}" "$TESTA_URL" || true)"
SVESS="$(curl -s -o /dev/null -w '%{http_connect}' -m 10 -x "http://${LIETOTAJS}:${PAROLE}@127.0.0.1:${PORTS}" https://example.com || true)"
IP="$(curl -s -m 10 https://api.ipify.org || hostname -I | awk '{print $1}')"

echo "VZD caur proxy:            $([[ "$REZ" == '{"type":"FeatureCollection"'* ]] && echo 'OK ✓' || echo "KĻŪDA ($REZ)")"
echo "Bez paroles (jābūt 407):   $BEZ_PAROLES"
echo "Svešs domēns (jābūt 403):  $SVESS"
echo "fail2ban:                  $(systemctl is-active fail2ban 2>/dev/null || echo 'nav')"

cat <<EOF

=====================================================================
 Gatavs. Iekopē šo rindu Streamlit -> aplikācija -> Settings -> Secrets
 (NESŪTI to čatā vai e-pastā — tajā ir parole):

VZD_PROXY = "http://${LIETOTAJS}:${PAROLE}@${IP}:${PORTS}"

=====================================================================
EOF
