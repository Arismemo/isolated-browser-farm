# 🌐 Isolated Browser Farm (云端物理隔离防关联浏览器集群)

> 🚀 **专为多账号运营、海外社媒矩阵、Google/AI 账户隔离打造的企业级防关联云端浏览器方案。**  
> 基于 Docker 容器化物理级隔离 + 独家 WebRTC 底层防火墙防泄露盾 + 独立静态住宅 IP + 可视化 Web 控制台。

---

## 🌟 为什么选择本方案？（与传统指纹浏览器的本质差异）

市面上的“指纹浏览器”多采用在本地修改 Chromium 参数或注入 JS 脚本的形式，在严苛的风控引擎（如 Google Risk Engine、Cloudflare Turnstile、Pixelscan）面前依然破绽百出。本系统基于**第一性原理**构建：

| 对比维度 | 市面普通指纹浏览器 / 插件 | 本项目 (Isolated Browser Farm) | 优势说明 |
| :--- | :--- | :--- | :--- |
| **隔离级别** | 逻辑进程隔离（易共用缓存/底层标识） | **Docker 物理容器隔离** | 每个账号完全独立文件系统、Cookie、内存与进程 |
| **本地硬件指纹** | 软件篡改 Canvas/WebGL（易产生特征矛盾） | **云端全真实物理环境** | 本地真实 Mac/Win 硬件参数、显卡、屏幕**完全不接触**目标网站 |
| **WebRTC 穿透** | 仅做 JS 伪装（极易被 STUN UDP 探测穿透） | **物理网络防火墙静默丢弃 (DROP)** | 独创底层防火墙，**100% 杜绝 VPS 机房原生 IP 泄露** |
| **静态住宅代理** | 需手动在客户端输入账号密码 | **服务端透明免密中继** | 自动完成认证转发，浏览器端开箱即用，零等待握手 |
| **字体指纹** | 容器环境字体贫瘠（易被识别为服务器） | **预置 Liberation 商业兼容字体库** | 完美匹配 Arial、Times New Roman 等常见系统字体 |
| **显卡指纹** | 暴露 `SwiftShader` 虚拟机 CPU 软解 | **内置 WebGL 真实独显掩码扩展** | 自动伪装为真实 `NVIDIA GeForce RTX 3060` 独立显卡 |
| **时区配置** | 需用户手动查询对应属地时区 | **GeoIP 智能探测与全自动对齐** | 输入代理秒读经纬度与时区，100% 自动匹配，告别风控 |
| **多账号管理**| 列表简陋，难以快速分类 | **标签分组 (Tags & Grouping) 动态筛选** | 支持按业务矩阵、账号用途快速分类，毫秒级即时过滤 |
| **健康度监控**| 无法直观获知代理质量 | **一键测速与 ISP 纯净度体检** | 实时探测网络延迟 RTT、国家国旗 🇺🇸、住宅 ISP 属性与状态 |
| **数据资产** | 账号数据难以备份迁移 | **Profile & Cookie 一键快照打包下载** | 一键导出 `.tar.gz` 备份，保障账号资产永不丢失 |
| **使用方式** | 本地安装臃肿客户端 | **任意设备浏览器即可远程操作** | 手机、平板、电脑打开网页即可像操作本机浏览器一样顺畅 |

---

## 🛡️ 权威防关联实测报告

在当前环境下打开业界主流防欺诈检测工具的实测成绩：

1. **[BrowserLeaks WebRTC 泄漏测试](https://browserleaks.com/webrtc)**：
   - 传统方案：`WebRTC IP doesn't match your Remote IP`（暴露机房真实公网 IP）
   - **本方案**：`Public IP Address` **彻底无泄漏**，mDNS 匿名混淆，STUN 探测物理超时阻断。
2. **[Whoer.net 纯净度检测](https://whoer.net)**：
   - 伪装度高达 **100%**，时区（EDT/EST）、DNS 与住宅 ISP（Comcast）完全统一。
3. **[IPinfo.io 运营商验证](https://ipinfo.io)**：
   - 识别为真正的家庭宽带 `AS7922 Comcast Cable Communications`（住宅 ISP 属性）。

---

## 🚀 极简部署指南 (3 步上手)

### 1. 准备条件
- 一台全新海外 Linux VPS（推荐 Ubuntu 22.04 / 24.04）
- 一个已解析到该 VPS 公网 IP 的域名（如 `browser.yourdomain.com`）

### 2. 一键自动化安装
SSH 登录你的 VPS 服务器，执行以下一键部署向导：

```bash
git clone https://github.com/Arismemo/isolated-browser-farm.git /root/j/browsers
cd /root/j/browsers
sudo bash install.sh
```

根据屏幕提示输入你的解析域名，脚本将全自动：
- 安装 Docker 与 Nginx
- 自动申请 Let's Encrypt 免费 SSL 泛域名/单域名证书
- 配置 Web 管理后台与安全 HTTP Basic Auth 认证密码
- 注入底层 WebRTC 物理防火墙服务（开机常驻自启）
- 启动 **Browser Hub 可视化控制台**

### 3. 访问并使用控制台
部署完成后，直接在电脑浏览器中打开：
👉 **`https://你的域名:28000`**

输入安装时设置的账号密码，即可进入现代化的极简控制台：
- **「＋ 新增 Profile」**：输入账号 ID、住宅代理字符串（如 `IP:PORT:USER:PASS`）与时区，3 秒即可拉起一个全新的隔离浏览器。
- **「一键打开」**：点击列表右侧的「打开」，在新标签页中即可无缝沉浸式操作云端浏览器！
- **「管理操作」**：支持一键重启、停止与彻底销毁容器及相关网络映射。

---

## 💻 命令行进阶运维

除 Web 控制台外，系统也提供了高效的 CLI 自动化工具：

### 快速新增账号环境
```bash
# 语法: ./scripts/add-profile.sh <账号ID> <代理字符串> [时区]

# 示例 1: 绑定带账密的静态住宅代理 (推荐)
sudo ./scripts/add-profile.sh acc2 48.46.113.162:47940:myuser:mypass America/New_York

# 示例 2: 直连环境 (使用 VPS 原生 IP)
sudo ./scripts/add-profile.sh acc3 direct America/Los_Angeles
```

### 查看容器与服务状态
```bash
# 查看所有已创建的浏览器容器
docker compose ps

# 查看 Web 控制台日志
journalctl -u browser-hub.service -f

# 查看底层 WebRTC 防泄漏防火墙盾状态
systemctl status docker-webrtc-shield.service
```

---

## 🏗️ 项目架构图

```mermaid
flowchart TD
    User["用户电脑 / 手机浏览器"] -->|HTTPS (SSL)| Nginx["Nginx SSL 443/自定义端口反向代理 (带 Basic Auth 认证)"]
    
    subgraph Host ["云服务器宿主机 (Linux VPS)"]
        Nginx -->|WebSockets 画面流| Kasm["Selkies / WebRTC 图形渲染传输器"]
        Nginx -->|HTTP 38080| Hub["Browser Hub 控制台后端 (Python)"]
        
        subgraph Shield ["底层网络安全防线"]
            FW["Iptables DOCKER-USER 链防火墙盾 (物理丢弃非 53 端口外发 UDP)"]
        end
        
        subgraph Docker ["Docker 容器 (物理隔离)"]
            Kasm --> Wayland["Wayland / labwc 合成器"]
            Wayland --> Chromium["Chromium 浏览器 (注入 Liberation 商业字体)"]
            Chromium -->|本地回环 127.0.0.1| Relay["本地 Python 免密中继器"]
        end
    end
    
    Relay -->|TCP 代理握手| ISP["海外原生静态住宅代理 (Comcast/AT&T)"]
    ISP --> Target["目标网站 (Google / YouTube / Twitter / Claude)"]
    Chromium -.->|STUN UDP 探测试图泄露真实IP| FW
    FW -.->|物理拦截 DROP| Blocked["❌ 无法穿透！真实 IP 0 泄露"]
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源发布，欢迎提交 PR 与 Issue。
