#!/bin/sh
# Publica aliases mDNS (pdv.local, financas.local etc.) apontando para os IPs atuais do dbserver (IPv4 + IPv6).
# O IPv6 é necessário: sem ele o macOS espera 5 s pela resposta AAAA a cada consulta e a página fica "só carregando".
# Se algum IP mudar (outra rede / novo prefixo IPv6), reanuncia sozinho em até 20 s.
#
# Instalação no dbserver (não vai pelo git push do PDV):
#   cp ~/bin/avahi-aliases.sh ~/bin/avahi-aliases.sh.bak
#   scp infra/dbserver/avahi-aliases.sh dbserver:bin/avahi-aliases.sh
#   ssh dbserver 'doas rc-service avahi-aliases restart'
NAMES="financas.local licitacoes.local financas.dbserver.local licitacoes.dbserver.local pdv.local pdv.dbserver.local"
last=""
pids=""

cleanup() { [ -n "$pids" ] && kill $pids 2>/dev/null; exit 0; }
trap cleanup TERM INT EXIT

while true; do
  ip4=$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
  ip6=$(ip -6 -o addr show scope global 2>/dev/null | grep -v -e temporary -e deprecated | awk '{print $4}' | cut -d/ -f1 | head -1)
  atual="$ip4 $ip6"
  if [ -n "$ip4" ] && [ "$atual" != "$last" ]; then
    [ -n "$pids" ] && kill $pids 2>/dev/null
    pids=""
    for n in $NAMES; do
      for a in $ip4 $ip6; do
        avahi-publish -a -R "$n" "$a" >/dev/null 2>&1 &
        pids="$pids $!"
      done
    done
    last=$atual
    logger -t avahi-aliases "publicando $NAMES -> $atual"
  fi
  sleep 20 & wait $!   # wait é interrompido pelo TERM na hora (sleep sozinho segura o stop por até 20 s)
done
