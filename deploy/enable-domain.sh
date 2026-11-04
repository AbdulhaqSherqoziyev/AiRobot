#!/usr/bin/env bash
# Connects icash.uz, admin.icash.uz and api.icash.uz. Run on the server, after the DNS A records
# point here. Refuses to start otherwise, and restores Nginx if its config test fails, because
# this Nginx also serves other projects.
set -euo pipefail
cd "$(dirname "$0")"
DOMAINS=(icash.uz admin.icash.uz api.icash.uz)
SITE=/etc/nginx/sites-available/quantlab-icash
LINK=/etc/nginx/sites-enabled/quantlab-icash
IP="$(curl -s -m 8 https://api.ipify.org)"
for d in "${DOMAINS[@]}"; do
  got="$( (getent ahostsv4 "$d" || true) | awk '{print $1}' | sort -u | tr '\n' ' ')"
  [[ " $got" == *" $IP "* ]] || { echo "DNS not ready: $d -> '${got:-nothing}', expected $IP"; exit 1; }
done
C="docker compose -f docker-compose.yml -f docker-compose.tunnel.yml -f docker-compose.domain.yml"
$C up -d api
cp nginx-icash.conf "$SITE"
ln -sf "$SITE" "$LINK"
if ! nginx -t; then
  rm -f "$LINK" "$SITE"
  echo "Nginx config rejected; removed the new site, nothing was reloaded."
  exit 1
fi
systemctl reload nginx
if ! certbot --nginx --non-interactive --redirect -d icash.uz -d admin.icash.uz -d api.icash.uz; then
  # Never leave the login reachable without TLS.
  rm -f "$LINK" "$SITE"
  nginx -t && systemctl reload nginx
  echo "Certificate failed; removed the site. Nothing is public. Retry when DNS has settled."
  exit 1
fi
sed -i 's/^QL_SECURE_COOKIES=.*/QL_SECURE_COOKIES=true/' .env
$C up -d api
sleep 5
for u in https://admin.icash.uz/ https://api.icash.uz/health; do curl -s -o /dev/null -m 10 -w "$u %{http_code}\n" "$u" || true; done
echo "Done. Sign-in now needs HTTPS: https://admin.icash.uz"
