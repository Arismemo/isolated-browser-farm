#!/bin/bash
set -euo pipefail

# ==============================================================================
# Isolated Browser Farm - Profile 自动化生成与配网脚本
# ==============================================================================

if [ $# -lt 2 ]; then
    echo "用法: ./add-profile.sh <账号ID, 如 acc2> <代理格式: IP:PORT:USER:PASS 或 direct> [时区, 默认 America/New_York]"
    exit 1
fi

ACC_ID="$1"
PROXY_STR="$2"
TZ_VAL="${3:-America/New_York}"

# 基础目录探测
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ACC_DIR="$BASE_DIR/profiles/$ACC_ID"

# 读取域名配置
DOMAIN="localhost"
if [ -f "$BASE_DIR/.env" ]; then
    DOMAIN=$(grep -E '^HUB_DOMAIN=' "$BASE_DIR/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "localhost")
fi
DOMAIN="${HUB_DOMAIN:-$DOMAIN}"

mkdir -p "$ACC_DIR/.config/labwc"

# 1. 自动分发持久化商业字体
if [ -d "$BASE_DIR/common_fonts" ]; then
    mkdir -p "$ACC_DIR/.fonts"
    cp -r "$BASE_DIR/common_fonts"/* "$ACC_DIR/.fonts/"
fi

# 2. 自动分发 WebGL 显卡指纹掩码扩展
if [ -d "$BASE_DIR/common_extensions/webgl-mask" ]; then
    mkdir -p "$ACC_DIR/extensions/webgl-mask"
    cp -r "$BASE_DIR/common_extensions/webgl-mask"/* "$ACC_DIR/extensions/webgl-mask/"
fi

# 3. 计算内部端口与外部端口
LAST_INTERNAL_PORT=$(grep -oE "127\.0\.0\.1:[0-9]+:3000" "$BASE_DIR/docker-compose.yml" 2>/dev/null | cut -d":" -f2 | sort -n | tail -n 1 || true)
NEW_INTERNAL_PORT=$(( ${LAST_INTERNAL_PORT:-3000} + 1 ))

LAST_EXTERNAL_PORT=$(grep -oE "listen [0-9]+ ssl" /etc/nginx/sites-available/browser-* 2>/dev/null | awk "{print \$2}" | sort -n | tail -n 1 || true)
NEW_EXTERNAL_PORT=$(( ${LAST_EXTERNAL_PORT:-28442} + 1 ))

# 4. 生成代理及本地免密 Relay
RELAY_PORT=$(( 18880 + (NEW_INTERNAL_PORT % 1000) ))
if [ "$PROXY_STR" = "direct" ]; then
    PROXY_PARAM=""
    cat > "$ACC_DIR/.config/labwc/autostart" << "AUTO_EOF"
#!/bin/bash
rm -f /config/.config/chromium/Singleton*
wrapped-chromium --enable-features=UseOzonePlatform --ozone-platform=wayland ${CHROME_CLI} &
AUTO_EOF
else
    IFS=":" read -r P_IP P_PORT P_USER P_PASS <<< "$PROXY_STR"
    if [ -n "${P_USER:-}" ] && [ -n "${P_PASS:-}" ]; then
        # 带账密的二级住宅代理 -> 写入专有 relay 脚本（本地 127.0.0.1 免密转发并自动注入认证头）
        cat > "$ACC_DIR/proxy_relay.py" << PY_EOF
import socket, select, base64, time

LOCAL_PORT = $RELAY_PORT
REMOTE_HOST = "$P_IP"
REMOTE_PORT = $P_PORT
AUTH_HEADER = b"Proxy-Authorization: Basic " + base64.b64encode(b"$P_USER:$P_PASS") + b"\r\n"

def log(msg):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)

def handle_client(client_sock):
    remote_sock = None
    try:
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_sock.settimeout(25)
        remote_sock.connect((REMOTE_HOST, REMOTE_PORT))

        req = client_sock.recv(8192)
        if not req: return

        first_line = req.split(b"\r\n")[0].decode("latin1", errors="ignore")
        log(f"REQ: {first_line}")

        headers_end = req.find(b"\r\n\r\n")
        if headers_end != -1:
            first_line_end = req.find(b"\r\n")
            new_req = req[:first_line_end+2] + AUTH_HEADER + req[first_line_end+2:]
        else:
            new_req = req

        remote_sock.sendall(new_req)

        sockets = [client_sock, remote_sock]
        while True:
            r, _, _ = select.select(sockets, [], [], 60)
            if not r: break
            for s in r:
                data = s.recv(65536)
                if not data: return
                if s is client_sock:
                    remote_sock.sendall(data)
                else:
                    client_sock.sendall(data)
    except Exception as e:
        log(f"ERR: {e}")
    finally:
        try: client_sock.close()
        except: pass
        if remote_sock:
            try: remote_sock.close()
            except: pass

def main():
    log(f"Starting relay on 127.0.0.1:{LOCAL_PORT} -> {REMOTE_HOST}:{REMOTE_PORT}")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", LOCAL_PORT))
    server.listen(128)
    import threading
    while True:
        client, _ = server.accept()
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()

if __name__ == "__main__":
    main()
PY_EOF
        chmod +x "$ACC_DIR/proxy_relay.py"
        cat > "$ACC_DIR/.config/labwc/autostart" << "AUTO_EOF"
#!/bin/bash
if [ -f /config/proxy_relay.py ]; then
    /lsiopy/bin/python3 /config/proxy_relay.py >/tmp/relay.log 2>&1 &
    sleep 1
fi
rm -f /config/.config/chromium/Singleton*
wrapped-chromium --enable-features=UseOzonePlatform --ozone-platform=wayland ${CHROME_CLI} &
AUTO_EOF
        PROXY_PARAM="--proxy-server=http://127.0.0.1:$RELAY_PORT"
    else
        PROXY_PARAM="--proxy-server=http://$P_IP:$P_PORT"
        cat > "$ACC_DIR/.config/labwc/autostart" << "AUTO_EOF"
#!/bin/bash
rm -f /config/.config/chromium/Singleton*
wrapped-chromium --enable-features=UseOzonePlatform --ozone-platform=wayland ${CHROME_CLI} &
AUTO_EOF
    fi
fi

chmod +x "$ACC_DIR/.config/labwc/autostart"
chown -R 1000:1000 "$ACC_DIR"

# 5. 追加容器到 docker-compose.yml (注入显卡掩码扩展与WebRTC防火墙盾参数)
cat >> "$BASE_DIR/docker-compose.yml" << ENTRY_EOF

  # 账号 $ACC_ID
  browser-$ACC_ID:
    image: lscr.io/linuxserver/chromium:latest
    container_name: browser-$ACC_ID
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=$TZ_VAL
      - TITLE=Google-Account-$ACC_ID
      - CHROME_CLI=https://accounts.google.com --no-first-run --lang=en-US $PROXY_PARAM --force-webrtc-ip-handling-policy=disable_non_proxied_udp --disable-blink-features=AutomationControlled --load-extension=/config/extensions/webgl-mask
    volumes:
      - ./profiles/$ACC_ID:/config
    ports:
      - "127.0.0.1:$NEW_INTERNAL_PORT:3000"
    shm_size: "1gb"
    restart: unless-stopped
ENTRY_EOF

# 6. 配置 Nginx SSL 反代与身份认证
CERT_PATH="/etc/letsencrypt/live/$DOMAIN"
SSL_CONF="/etc/nginx/sites-available/browser-$ACC_ID.$DOMAIN"

cat > "$SSL_CONF" << NGINX_EOF
server {
    listen $NEW_EXTERNAL_PORT ssl http2;
    server_name $DOMAIN;

    ssl_certificate $CERT_PATH/fullchain.pem;
    ssl_certificate_key $CERT_PATH/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    auth_basic "Restricted Remote Browser Access";
    auth_basic_user_file /etc/nginx/.browser_htpasswd;

    location / {
        proxy_pass http://127.0.0.1:$NEW_INTERNAL_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
    }
}
NGINX_EOF

ln -sf "$SSL_CONF" "/etc/nginx/sites-enabled/browser-$ACC_ID.$DOMAIN"
nginx -t >/dev/null
nginx -s reload

# 7. 防火墙与启动容器
if command -v ufw >/dev/null 2>&1; then
    ufw allow "$NEW_EXTERNAL_PORT/tcp" comment "Remote Browser $ACC_ID" >/dev/null 2>&1 || true
fi

cd "$BASE_DIR"
docker compose up -d "browser-$ACC_ID"

echo "✓ 账号 [$ACC_ID] 已成功部署！访问入口: https://$DOMAIN:$NEW_EXTERNAL_PORT"
