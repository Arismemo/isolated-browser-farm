import http.server
import socketserver
import json
import subprocess
import os
import re
import urllib.parse

PORT = 38080
BASE_DIR = os.environ.get("BROWSER_FARM_DIR", "/root/j/browsers")

def load_domain():
    # 优先从环境变量读取，其次从 .env 文件读取
    domain = os.environ.get("HUB_DOMAIN")
    if domain:
        return domain.strip()
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("HUB_DOMAIN="):
                        return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return "localhost"

DOMAIN = load_domain()

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=60)
        return res.returncode == 0, res.stdout, res.stderr
    except Exception as e:
        return False, "", str(e)

def get_profiles():
    profiles = []
    compose_file = os.path.join(BASE_DIR, "docker-compose.yml")
    if not os.path.exists(compose_file):
        return profiles
    
    with open(compose_file, "r") as f:
        content = f.read()

    # 获取容器实时运行状态
    ok, ps_out, _ = run_cmd("docker ps -a --format '{{.Names}}|{{.Status}}|{{.State}}'")
    status_map = {}
    if ok:
        for line in ps_out.strip().split("\n"):
            if "|" in line:
                parts = line.split("|")
                status_map[parts[0]] = {"status": parts[1], "state": parts[2]}

    # 获取外部端口映射 (Nginx)
    ok, nginx_files, _ = run_cmd("ls /etc/nginx/sites-available/browser-* 2>/dev/null")
    nginx_port_map = {}
    if ok and nginx_files.strip():
        for nfile in nginx_files.strip().split("\n"):
            match_acc = re.search(r'browser-(acc[0-9a-zA-Z_-]+)', os.path.basename(nfile))
            if match_acc:
                acc_name = match_acc.group(1)
                try:
                    with open(nfile, "r") as nf:
                        text = nf.read()
                        port_match = re.search(r'listen\s+([0-9]+)\s+ssl', text)
                        if port_match:
                            nginx_port_map[acc_name] = int(port_match.group(1))
                except Exception:
                    pass

    # 解析 Compose 中的各个 Service
    blocks = content.split("\n  browser-")
    for block in blocks[1:]:
        header = block.split(":")[0].strip()
        acc_id = header

        # 匹配代理 (支持无引号与有引号两种模式)
        proxy_match = re.search(r'--proxy-server=["\']?([^"\'\s\n]+)["\']?', block)
        proxy_val = proxy_match.group(1) if proxy_match else "直连 (无二级代理)"

        # 匹配时区
        tz_match = re.search(r'TZ=([^\s\n]+)', block)
        tz_val = tz_match.group(1) if tz_match else "America/New_York"

        # 匹配内部端口
        port_match = re.search(r'127\.0\.0\.1:([0-9]+):3000', block)
        internal_port = int(port_match.group(1)) if port_match else 0

        container_name = f"browser-{acc_id}"
        c_info = status_map.get(container_name, {"status": "未运行", "state": "exited"})

        external_port = nginx_port_map.get(acc_id, 0)
        current_domain = load_domain()

        profiles.append({
            "id": acc_id,
            "container_name": container_name,
            "proxy": proxy_val,
            "timezone": tz_val,
            "internal_port": internal_port,
            "external_port": external_port,
            "external_url": f"https://{current_domain}:{external_port}" if external_port > 0 else None,
            "status": c_info["status"],
            "state": c_info["state"],
            "profile_dir": f"{BASE_DIR}/profiles/{acc_id}"
        })

    return profiles

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/profiles":
            profiles = get_profiles()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "profiles": profiles}).encode())
        elif parsed.path == "/" or parsed.path == "/index.html":
            html_path = os.path.join(os.path.dirname(__file__), "index.html")
            if os.path.exists(html_path):
                with open(html_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "File not found")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        if parsed.path == "/api/profiles/add":
            acc_id = data.get("id", "").strip()
            proxy = data.get("proxy", "").strip() or "direct"
            tz = data.get("timezone", "America/New_York").strip()

            if not acc_id or not re.match(r'^[a-zA-Z0-9_-]+$', acc_id):
                self.send_json_res(400, {"success": False, "error": "账号标识只能包含字母、数字、下划线和中划线"})
                return

            add_script = os.path.join(BASE_DIR, "scripts", "add-profile.sh")
            if not os.path.exists(add_script):
                # 兼容平铺目录结构
                add_script = os.path.join(BASE_DIR, "add-profile.sh")

            cmd = f"{add_script} {acc_id} '{proxy}' '{tz}'"
            ok, stdout, stderr = run_cmd(cmd)
            if ok:
                self.send_json_res(200, {"success": True, "message": f"账号 {acc_id} 创建成功！", "output": stdout})
            else:
                self.send_json_res(500, {"success": False, "error": f"创建失败: {stderr or stdout}"})

        elif parsed.path == "/api/profiles/action":
            acc_id = data.get("id", "").strip()
            action = data.get("action", "").strip()
            if not acc_id:
                self.send_json_res(400, {"success": False, "error": "缺少账号 ID"})
                return

            container = f"browser-{acc_id}"
            if action == "restart":
                ok, out, err = run_cmd(f"docker restart {container}")
                self.send_json_res(200 if ok else 500, {"success": ok, "message": "重启成功" if ok else err})
            elif action == "stop":
                ok, out, err = run_cmd(f"docker stop {container}")
                self.send_json_res(200 if ok else 500, {"success": ok, "message": "已停止" if ok else err})
            elif action == "start":
                ok, out, err = run_cmd(f"docker start {container}")
                self.send_json_res(200 if ok else 500, {"success": ok, "message": "已启动" if ok else err})
            elif action == "delete":
                cmd = f"""
                docker stop {container} 2>/dev/null || true
                docker rm -f {container} 2>/dev/null || true
                rm -f /etc/nginx/sites-enabled/browser-{acc_id}* /etc/nginx/sites-available/browser-{acc_id}*
                nginx -s reload 2>/dev/null || true
                # 从 docker-compose.yml 移除该 service
                python3 -c '
import re
path = "{BASE_DIR}/docker-compose.yml"
if os.path.exists(path):
    with open(path, "r") as f:
        text = f.read()
    pattern = r"\\n  # 账号 {acc_id}\\n  browser-{acc_id}:[\\s\\S]*?(?=\\n  # 账号 |\\n\\Z)"
    new_text = re.sub(pattern, "", text)
    with open(path, "w") as f:
        f.write(new_text)
'
                rm -rf {BASE_DIR}/profiles/{acc_id}
                """
                ok, out, err = run_cmd(cmd)
                self.send_json_res(200 if ok else 500, {"success": ok, "message": "环境已彻底清除" if ok else err})
            else:
                self.send_json_res(400, {"success": False, "error": "不支持的操作指令"})
        else:
            self.send_error(404, "Not Found")

    def send_json_res(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Browser Hub backend listening on 127.0.0.1:{PORT} (Domain: {DOMAIN})")
        httpd.serve_forever()
