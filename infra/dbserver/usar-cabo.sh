#!/bin/sh
# Passa o dbserver a usar o cabo de rede (eth0) como conexão principal; o Wi-Fi fica de reserva.
# O Wi-Fi 2,4 GHz derrubava o túnel da Cloudflare (QUIC "no recent network activity") e deixava o site lento.
#
# Rodar no dbserver como root:  doas sh ~/usar-cabo.sh
# Desfazer:  doas cp /etc/network/interfaces.bak-<data> /etc/network/interfaces && doas ifdown eth0
set -e

ip link set eth0 up
sleep 4
if [ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" != 1 ]; then
  echo "eth0 sem sinal: confira o cabo (nos dois lados) e se a luz da porta acende. Nada foi alterado."
  ip link set eth0 down
  exit 1
fi
echo "eth0 com sinal: $(cat /sys/class/net/eth0/speed 2>/dev/null) Mbit/s"

if ! grep -q 'iface eth0' /etc/network/interfaces; then
  cp /etc/network/interfaces "/etc/network/interfaces.bak-$(date +%Y%m%d%H%M)"
  cat > /etc/network/interfaces <<'EOF'
auto lo
iface lo inet loopback
iface lo inet6 loopback

# cabo: conexão principal (métrica menor ganha)
auto eth0
iface eth0 inet dhcp
	metric 100

# Wi-Fi: reserva, se o cabo cair
auto wlan0
iface wlan0 inet dhcp
iface wlan0 inet6 dhcp
EOF
  echo "/etc/network/interfaces atualizado (backup em /etc/network/interfaces.bak-*)"
fi

ip link set eth0 down
ifup eth0
sleep 3
echo "--- rotas padrão:"; ip route | grep '^default'
echo "--- IP do cabo:"; ip -4 -o addr show dev eth0 | awk '{print $4}'

rc-service avahi-aliases restart     # pdv.local etc. passam a apontar para o IP do cabo
docker restart cloudflared >/dev/null && echo "túnel da Cloudflare reconectado"
echo "pronto"
