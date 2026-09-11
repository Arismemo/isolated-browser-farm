#!/bin/bash
set -euo pipefail

# ==============================================================================
# Isolated Browser Farm - 一键工程化安装与部署脚本
# ==============================================================================

echo "================================================================"
echo "    🚀 云端多账号物理隔离防关联浏览器集群 (Browser Farm) 安装向导"
echo "================================================================"

if [ "$EUID" -ne 0 ]; then
    echo "❌ 错误: 请使用 root 权限执行此脚本 (sudo bash install.sh)"
    exit 1
fi

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

# 1. 检查并安装基础依赖
echo "📦 [1/6] 正在检查并补齐系统基础依赖..."
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 nginx apache2-utils python3 curl iptables fontconfig

systemctl enable --now docker
systemctl enable --now nginx

# 2. 配置域名与 SSL 证书
echo ""
echo "🌐 [2/6] 域名与 SSL 证书配置"
read -rp "请输入已解析到当前服务器的域名 (例如: browser.example.com): " HUB_DOMAIN
if [ -z "$HUB_DOMAIN" ]; then
    echo "❌ 域名不能为空！"
    exit 1
fi

# 检查证书是否存在
CERT_DIR="/etc/letsencrypt/live/$HUB_DOMAIN"
if [ ! -f "$CERT_DIR/fullchain.pem" ]; then
    echo "⚠️ 未在 $CERT_DIR 检测到 Let's Encrypt 证书。"
    read -rp "是否立即通过 Certbot 申请证书？(y/n, 默认 y): " DO_CERT
    DO_CERT="${DO_CERT:-y}"
    if [[ "$DO_CERT" =~ ^[Yy]$ ]]; then
        apt-get install -y -qq certbot python3-certbot-nginx
        systemctl stop nginx || true
        certbot certonly --standalone -d "$HUB_DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || {
            echo "❌ 证书申请失败，请确认域名 DNS 解析已指向本机公网 IP！"
            systemctl start nginx || true
            exit 1
        }
        systemctl start nginx
    else
        echo "⚠️ 请确保后续将证书放置于: $CERT_DIR/fullchain.pem 及 privkey.pem"
    fi
fi

# 3. 设置 Web 控制台管理密码
echo ""
echo "🔐 [3/6] 设置 Web 管理控制台与远程桌面的访问账密"
read -rp "请输入登录用户名 (默认: admin): " ADMIN_USER
ADMIN_USER="${ADMIN_USER:-admin}"
read -rp "请输入登录密码 (默认随机生成): " ADMIN_PASS
if [ -z "$ADMIN_PASS" ]; then
    ADMIN_PASS=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 12)
    echo "🔑 已生成随机密码: $ADMIN_PASS"
fi

htpasswd -bc /etc/nginx/.browser_htpasswd "$ADMIN_USER" "$ADMIN_PASS"
chmod 600 /etc/nginx/.browser_htpasswd

# 4. 写入环境变量与基础模板
echo ""
echo "⚙️ [4/6] 初始化工程配置与持久化字体库..."
cat > "$BASE_DIR/.env" << EOF
HUB_DOMAIN="$HUB_DOMAIN"
BROWSER_FARM_DIR="$BASE_DIR"
HUB_PORT=28000
EOF

if [ ! -f "$BASE_DIR/docker-compose.yml" ]; then
    cat > "$BASE_DIR/docker-compose.yml" << EOF
services:
  # 账号服务将由 add-profile.sh 自动追加至此
EOF
fi

# 5. 部署 WebRTC 底层防火墙防泄露盾
echo ""
echo "🛡️ [5/6] 部署底层物理防 WebRTC 泄露盾 (Systemd)..."
cp "$BASE_DIR/scripts/docker-webrtc-shield.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now docker-webrtc-shield.service

# 6. 配置并启动 Browser Hub 控制台
echo ""
echo "🖥️ [6/6] 启动 Browser Hub Web 后端服务与 Nginx 反向代理..."
cat > /etc/systemd/system/browser-hub.service << EOF
[Unit]
Description=Isolated Browser Hub Web Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BASE_DIR/hub
Environment=HUB_DOMAIN=$HUB_DOMAIN
Environment=BROWSER_FARM_DIR=$BASE_DIR
ExecStart=/usr/bin/python3 $BASE_DIR/hub/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now browser-hub.service

# 配置 Hub 的 Nginx 入口
HUB_NGINX="/etc/nginx/sites-available/browser-hub.$HUB_DOMAIN"
cat > "$HUB_NGINX" << NGINX_EOF
server {
    listen 28000 ssl http2;
    server_name $HUB_DOMAIN;

    ssl_certificate $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;

    auth_basic "Restricted Browser Hub Console";
    auth_basic_user_file /etc/nginx/.browser_htpasswd;

    location / {
        proxy_pass http://127.0.0.1:38080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }
}
NGINX_EOF

ln -sf "$HUB_NGINX" "/etc/nginx/sites-enabled/browser-hub.$HUB_DOMAIN"
nginx -t
nginx -s reload

# 开放防火墙端口
if command -v ufw >/dev/null 2>&1; then
    ufw allow 28000/tcp comment "Browser Hub Web Console" >/dev/null 2>&1 || true
fi

echo ""
echo "================================================================"
echo "    🎉 部署完成！浏览器集群控制台已就绪！"
echo "================================================================"
echo "👉 控制台网址: https://$HUB_DOMAIN:28000"
echo "👤 登录账号:   $ADMIN_USER"
echo "🔑 登录密码:   $ADMIN_PASS"
echo ""
echo "💡 提示: 进入控制台后，点击「＋ 新增 Profile」即可一键生成隔离浏览器环境！"
echo "================================================================"
