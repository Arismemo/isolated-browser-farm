import http.server
import socketserver
import json
import subprocess
import os
import re
import urllib.parse
import time
import io
import tarfile
import shutil

PORT = 38080
BASE_DIR = os.environ.get("BROWSER_FARM_DIR", "/root/j/browsers")

def run_cmd(cmd, timeout=60):
    try:
        res = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout)
        return res.returncode == 0, res.stdout, res.stderr
    except Exception as e:
        return False, "", str(e)

def load_domain():
    domain = os.environ.get("HUB_DOMAIN")
    if domain:
        return domain.strip()
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("HUB_DOMAIN="):
                        val = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass

    # 自动从现有的 Nginx 反代配置中智能提取域名
    ok, out, _ = run_cmd("grep -rhoE 'server_name [^;]+' /etc/nginx/sites-available/browser-* 2>/dev/null | head -n 1")
    if ok and out.strip():
        parts = out.strip().split()
        if len(parts) >= 2 and parts[1] != "localhost":
            return parts[1]

    return "localhost"

DOMAIN = load_domain()

def country_to_flag(code):
    if not code or len(code) != 2:
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def get_profile_meta(acc_id):
    meta_path = os.path.join(BASE_DIR, "profiles", acc_id, "meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "group": "默认分组",
        "tags": [],
        "notes": "",
        "last_check": None
    }

def save_profile_meta(acc_id, meta):
    profile_dir = os.path.join(BASE_DIR, "profiles", acc_id)
    os.makedirs(profile_dir, exist_ok=True)
    meta_path = os.path.join(profile_dir, "meta.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def remove_profile_from_compose(acc_id):
    compose_file = os.path.join(BASE_DIR, "docker-compose.yml")
    if not os.path.exists(compose_file):
        return
    with open(compose_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    target_service = f"browser-{acc_id}:"
    new_lines = []
    skip = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 检查是否为该服务块的注释头（如 # 账号 xxx）
        if not skip and acc_id in line and stripped.startswith("#"):
            is_header = False
            for forward_line in lines[i+1:i+4]:
                if target_service in forward_line:
                    is_header = True
                    break
            if is_header:
                continue

        if target_service in stripped and not stripped.startswith("#"):
            skip = True
            continue

        if skip:
            # 遇到下一个同级服务或顶级服务定义时退出跳过
            if re.match(r'^\s{2}[a-zA-Z0-9_-]+:', line) or (not line.startswith(" ") and stripped):
                skip = False
            else:
                continue

        new_lines.append(line)

    with open(compose_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def delete_profile_full(acc_id):
    container = f"browser-{acc_id}"
    run_cmd(f"docker stop {container} 2>/dev/null; docker rm -f {container} 2>/dev/null")
    run_cmd(f"rm -f /etc/nginx/sites-enabled/browser-{acc_id}* /etc/nginx/sites-available/browser-{acc_id}* && nginx -s reload 2>/dev/null || true")
    remove_profile_from_compose(acc_id)
    profile_dir = os.path.join(BASE_DIR, "profiles", acc_id)
    if os.path.exists(profile_dir):
        shutil.rmtree(profile_dir, ignore_errors=True)
    return True

def probe_proxy_network(proxy_str="", acc_id=""):
    start_t = time.time()
    
    if acc_id:
        cmd = f"docker exec browser-{acc_id} curl -s --max-time 8 -x {proxy_str or 'http://127.0.0.1:18888'} https://ipinfo.io/json"
    else:
        curl_proxy = ""
        if proxy_str and proxy_str != "direct":
            parts = proxy_str.split(":")
            if len(parts) == 4:
                curl_proxy = f"-x http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            elif len(parts) == 2:
                curl_proxy = f"-x http://{parts[0]}:{parts[1]}"
            elif "@" in proxy_str:
                curl_proxy = f"-x http://{proxy_str}"
            elif proxy_str.startswith("http://127.0.0.1"):
                curl_proxy = f"-x {proxy_str}"
        cmd = f"curl -s --max-time 8 {curl_proxy} https://ipinfo.io/json"

    ok, out, err = run_cmd(cmd, timeout=10)
    latency_ms = int((time.time() - start_t) * 1000)

    if ok and out.strip().startswith("{"):
        try:
            data = json.loads(out)
            country = data.get("country", "")
            org = data.get("org", "")
            dc_keywords = ["cloud", "hosting", "server", "data center", "ovh", "hetzner", "digitalocean", "linode", "aws", "amazon"]
            is_dc = any(kw in org.lower() for kw in dc_keywords)
            ip_type = "DataCenter / Hosting (数据中心机房)" if is_dc else "Residential / ISP (真实住宅宽带)"

            return {
                "success": True,
                "ip": data.get("ip", ""),
                "city": data.get("city", ""),
                "region": data.get("region", ""),
                "country": country,
                "flag": country_to_flag(country),
                "timezone": data.get("timezone", "America/New_York"),
                "isp": org,
                "type": ip_type,
                "latency_ms": latency_ms,
                "check_time": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            return {"success": False, "error": f"解析失败: {e}", "latency_ms": latency_ms}
    return {"success": False, "error": err or "请求超时", "latency_ms": latency_ms}

def get_profiles():
    profiles = []
    compose_file = os.path.join(BASE_DIR, "docker-compose.yml")
    if not os.path.exists(compose_file):
        return profiles, ["全部", "默认分组"]
    
    with open(compose_file, "r") as f:
        content = f.read()

    ok, ps_out, _ = run_cmd("docker ps -a --format '{{.Names}}|{{.Status}}|{{.State}}'")
    status_map = {}
    if ok:
        for line in ps_out.strip().split("\n"):
            if "|" in line:
                parts = line.split("|")
                status_map[parts[0]] = {"status": parts[1], "state": parts[2]}

    ok, nginx_files, _ = run_cmd("ls /etc/nginx/sites-available/browser-* 2>/dev/null")
    nginx_port_map = {}
    nginx_internal_port_map = {}
    if ok and nginx_files.strip():
        for nfile in nginx_files.strip().split("\n"):
            fname = os.path.basename(nfile)
            if "browser-hub" in fname:
                continue
            # 提取账号 ID（去除 browser- 前缀以及后续域名后缀）
            m = re.search(r'browser-([^.]+)', fname)
            acc_name = m.group(1) if m else None

            try:
                with open(nfile, "r") as nf:
                    text = nf.read()
                    port_match = re.search(r'listen\s+([0-9]+)\s+ssl', text)
                    internal_match = re.search(r'proxy_pass\s+http://127\.0\.0\.1:([0-9]+)', text)
                    if port_match:
                        ext_p = int(port_match.group(1))
                        if acc_name:
                            nginx_port_map[acc_name] = ext_p
                        if internal_match:
                            nginx_internal_port_map[int(internal_match.group(1))] = ext_p
            except Exception:
                pass

    all_groups = set(["全部", "默认分组"])
    blocks = content.split("\n  browser-")
    for block in blocks[1:]:
        header = block.split(":")[0].strip()
        acc_id = header

        proxy_match = re.search(r'--proxy-server=["\']?([^"\'\s\n]+)["\']?', block)
        proxy_val = proxy_match.group(1) if proxy_match else "直连 (无二级代理)"

        tz_match = re.search(r'TZ=([^\s\n]+)', block)
        tz_val = tz_match.group(1) if tz_match else "America/New_York"

        port_match = re.search(r'127\.0\.0\.1:([0-9]+):3000', block)
        internal_port = int(port_match.group(1)) if port_match else 0

        container_name = f"browser-{acc_id}"
        c_info = status_map.get(container_name, {"status": "未运行", "state": "exited"})
        external_port = nginx_port_map.get(acc_id) or nginx_internal_port_map.get(internal_port, 0)
        current_domain = load_domain()

        meta = get_profile_meta(acc_id)
        if meta.get("group"):
            all_groups.add(meta["group"])

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
            "profile_dir": f"{BASE_DIR}/profiles/{acc_id}",
            "group": meta.get("group", "默认分组"),
            "tags": meta.get("tags", []),
            "notes": meta.get("notes", ""),
            "last_check": meta.get("last_check")
        })

    return profiles, sorted(list(all_groups))

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/profiles":
            profiles, groups = get_profiles()
            self.send_json_res(200, {"success": True, "profiles": profiles, "groups": groups})

        elif parsed.path == "/api/clipboard/get":
            acc_id = qs.get("id", [""])[0]
            if not acc_id:
                self.send_json_res(400, {"success": False, "error": "缺少 ID"})
                return
            container = f"browser-{acc_id}"
            ok, out, err = run_cmd(f"docker exec -u abc {container} wl-paste 2>/dev/null || docker exec -u abc {container} xclip -o 2>/dev/null")
            self.send_json_res(200, {"success": True, "text": out})

        elif parsed.path == "/api/profiles/backup":
            acc_id = qs.get("id", [""])[0]
            profile_dir = os.path.join(BASE_DIR, "profiles", acc_id)
            if not acc_id or not os.path.exists(profile_dir):
                self.send_error(404, "Profile not found")
                return

            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w:gz") as tar:
                tar.add(profile_dir, arcname=acc_id)
            tar_data = tar_stream.getvalue()

            self.send_response(200)
            self.send_header("Content-Type", "application/gzip")
            self.send_header("Content-Disposition", f'attachment; filename="profile_{acc_id}_backup.tar.gz"')
            self.send_header("Content-Length", str(len(tar_data)))
            self.end_headers()
            self.wfile.write(tar_data)

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

        if parsed.path == "/api/proxy/probe":
            proxy_str = data.get("proxy", "").strip()
            acc_id = data.get("id", "").strip()
            if not proxy_str and acc_id:
                profiles, _ = get_profiles()
                for p in profiles:
                    if p["id"] == acc_id:
                        proxy_str = p["proxy"]
                        break

            res = probe_proxy_network(proxy_str=proxy_str, acc_id=acc_id)
            if acc_id and res.get("success"):
                meta = get_profile_meta(acc_id)
                meta["last_check"] = res
                save_profile_meta(acc_id, meta)

            self.send_json_res(200, res)

        elif parsed.path == "/api/profiles/update-meta":
            acc_id = data.get("id", "").strip()
            if not acc_id:
                self.send_json_res(400, {"success": False, "error": "缺少账号 ID"})
                return
            meta = get_profile_meta(acc_id)
            if "group" in data: meta["group"] = data["group"].strip() or "默认分组"
            if "tags" in data: meta["tags"] = data["tags"]
            if "notes" in data: meta["notes"] = data["notes"].strip()
            save_profile_meta(acc_id, meta)
            self.send_json_res(200, {"success": True, "message": "元数据已更新"})

        elif parsed.path == "/api/clipboard/send":
            acc_id = data.get("id", "").strip()
            text = data.get("text", "")
            if not acc_id:
                self.send_json_res(400, {"success": False, "error": "缺少账号 ID"})
                return
            container = f"browser-{acc_id}"
            proc = subprocess.Popen(
                ["docker", "exec", "-i", "-u", "abc", container, "wl-copy"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = proc.communicate(input=text)
            self.send_json_res(200, {"success": proc.returncode == 0, "message": "已同步到云端剪贴板"})

        elif parsed.path == "/api/profiles/add":
            acc_id = data.get("id", "").strip()
            proxy = data.get("proxy", "").strip() or "direct"
            tz = data.get("timezone", "America/New_York").strip()
            group = data.get("group", "默认分组").strip()
            tags = data.get("tags", [])
            notes = data.get("notes", "").strip()

            if not acc_id or not re.match(r'^[a-zA-Z0-9_-]+$', acc_id):
                self.send_json_res(400, {"success": False, "error": "账号标识只能包含字母、数字、下划线和中划线"})
                return

            add_script = os.path.join(BASE_DIR, "scripts", "add-profile.sh")
            if not os.path.exists(add_script):
                add_script = os.path.join(BASE_DIR, "add-profile.sh")

            cmd = f"HUB_DOMAIN='{DOMAIN}' {add_script} {acc_id} '{proxy}' '{tz}'"
            ok, stdout, stderr = run_cmd(cmd)
            if ok:
                save_profile_meta(acc_id, {
                    "group": group,
                    "tags": tags,
                    "notes": notes,
                    "last_check": None
                })
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
            elif action == "start" or action == "activate":
                # 针对 1C2G 极限制环境：保证同时只运行当前 1 个活动浏览器，自动暂停其他浏览器以保护宿主机
                profiles, _ = get_profiles()
                for p in profiles:
                    if p["id"] != acc_id and p["state"] == "running":
                        run_cmd(f"docker stop {p['container_name']}")
                ok, out, err = run_cmd(f"docker start {container}")
                self.send_json_res(200 if ok else 500, {"success": ok, "message": "已激活当前环境" if ok else err})
            elif action == "delete":
                ok = delete_profile_full(acc_id)
                self.send_json_res(200, {"success": True, "message": "环境已彻底清除"})
            else:
                self.send_json_res(400, {"success": False, "error": "不支持的操作指令"})
        else:
            self.send_error(404, "Not Found")

    def send_json_res(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Browser Hub Enhanced Backend listening on 127.0.0.1:{PORT} (Domain: {DOMAIN})")
        httpd.serve_forever()
