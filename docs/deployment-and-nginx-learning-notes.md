# 部署与 Nginx 学习笔记：请求是怎样到达页面和 API 的

这篇笔记以 `zero-to-tech` 在 Linux 单机服务器上的部署为例，解释域名、HTTPS、Nginx、Next.js、FastAPI、systemd 和 SQLite 是怎样配合工作的。

学完后应该能理解：

- 浏览器输入域名后，请求经过了哪些环节；
- Nginx 如何决定把请求转发到 3000 还是 8000 端口；
- Next.js 如何选择要展示的页面；
- FastAPI 如何选择接口并读写 SQLite；
- systemd 为什么能让程序一直运行并在开机时自动启动；
- 常见的 301、404、502 和 500 分别可能发生在哪一层。

## 1. 当前生产部署的整体结构

```text
浏览器
  │
  │ https://wool0312.me/...
  ▼
DNS：把 wool0312.me 解析为阿里云服务器公网 IP
  │
  ▼
阿里云防火墙：允许 80、443 端口进入服务器
  │
  ▼
Nginx：监听 80、443，处理 HTTPS，并根据 URL 分流
  ├── /api/* ───────────────► FastAPI / Uvicorn（127.0.0.1:8000）
  │                              │
  │                              └── SQLite（/var/lib/zero-to-tech/app.db）
  │
  └── 其他路径 ─────────────► Next.js（127.0.0.1:3000）

systemd 在后台启动并监管 Next.js 和 FastAPI 两个进程
```

对公网真正开放的是 Nginx。3000 和 8000 只监听 `127.0.0.1`，外部用户不能绕过 Nginx 直接访问它们。

## 2. 从域名到服务器

用户访问：

```text
https://wool0312.me/text-lab
```

第一步是 DNS 查询。DNS 中的 A 记录把 `wool0312.me` 转换为服务器公网 IPv4 地址。

DNS 只负责回答“服务器在哪里”，并不决定展示哪个页面，也不运行应用代码。

浏览器获得 IP 后，会连接服务器的 443 端口。阿里云轻量服务器的防火墙必须允许 443 入站；访问 HTTP 时使用的是 80 端口。

生产部署通常只对公网开放：

| 端口 | 用途 | 是否应公开 |
| --- | --- | --- |
| 22 | SSH 管理服务器 | 是，但最好限制来源 IP |
| 80 | HTTP，并跳转到 HTTPS | 是 |
| 443 | HTTPS 网站 | 是 |
| 3000 | Next.js 内部服务 | 否 |
| 8000 | FastAPI 内部服务 | 否 |

## 3. HTTPS 在哪里处理

Nginx 的 HTTPS `server` 配置包含证书和私钥：

```nginx
listen 443 ssl default_server;
listen [::]:443 ssl default_server;

ssl_certificate     /etc/nginx/ssl/www.wool0312.me.pem;
ssl_certificate_key /etc/nginx/ssl/www.wool0312.me.key;
```

浏览器先与 Nginx 完成 TLS 握手。Nginx 使用证书证明服务器身份，并建立加密连接。

Nginx 到 Next.js 和 FastAPI 使用本机 HTTP：

```text
Nginx → http://127.0.0.1:3000
Nginx → http://127.0.0.1:8000
```

这段流量只在服务器内部回环网络传输，不经过公网，因此不需要再配置一套 HTTPS。

80 端口的配置只负责跳转：

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name wool0312.me www.wool0312.me;

    return 301 https://$host$request_uri;
}
```

`$host` 保留域名，`$request_uri` 保留路径和查询参数。例如：

```text
http://wool0312.me/text-lab?from=home
                     │
                     ▼ 301
https://wool0312.me/text-lab?from=home
```

## 4. Nginx 怎样选择 server

一台 Nginx 可以同时托管多个域名。收到请求后，它先选择 `server` 块，再选择其中的 `location`。

选择 `server` 时主要看两项：

1. 请求到达的 IP 和端口是否匹配 `listen`；
2. HTTP 请求中的 `Host` 是否匹配 `server_name`。

当前域名配置是：

```nginx
server_name wool0312.me www.wool0312.me;
```

因此这两个域名会进入这个 `server`。`default_server` 表示：如果同一端口没有找到更合适的域名配置，就使用这个默认服务器。

要点：`server_name` 选择的是网站配置，不是 React 页面。

## 5. Nginx 怎样根据 URL 分流

当前 HTTPS `server` 中最重要的是两个 `location`：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
}

location / {
    proxy_pass http://127.0.0.1:3000;
}
```

这里使用前缀匹配。多个普通前缀都能匹配时，Nginx 选择最长的前缀。

| 请求路径 | 可匹配的 location | 最终去向 |
| --- | --- | --- |
| `/` | `/` | Next.js：3000 |
| `/text-lab` | `/` | Next.js：3000 |
| `/_next/static/...` | `/` | Next.js：3000 |
| `/api/health` | `/api/`、`/` | FastAPI：8000 |
| `/api/analyze` | `/api/`、`/` | FastAPI：8000 |

`/api/health` 同时以 `/api/` 和 `/` 开头，但 `/api/` 更长，所以交给 FastAPI。

注意 `/api` 和 `/api/` 不完全相同。当前规则 `location /api/` 不匹配没有末尾斜杠的 `/api`，因此 `/api` 会落入 `location /` 并交给 Next.js。项目实际接口都有更完整的路径，例如 `/api/health`，所以不受影响。

## 6. proxy_pass 做了什么

反向代理的含义是：浏览器只与 Nginx 通信，Nginx 代表浏览器向内部应用发起请求，再把应用响应转交给浏览器。

以健康检查为例：

```text
浏览器 GET /api/health
        ↓
Nginx 匹配 location /api/
        ↓
Nginx 请求 http://127.0.0.1:8000/api/health
        ↓
FastAPI 返回 {"status":"ok"}
        ↓
Nginx 把 JSON 返回给浏览器
```

配置中的请求头用于把原始请求信息传给后端：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

含义分别是：

- `Host`：用户访问的原始域名；
- `X-Real-IP`：直接连接 Nginx 的客户端 IP；
- `X-Forwarded-For`：请求经过的代理 IP 链；
- `X-Forwarded-Proto`：用户原始使用的是 HTTP 还是 HTTPS。

当前 `proxy_pass` 地址后面没有额外的 `/`：

```nginx
proxy_pass http://127.0.0.1:8000;
```

因此原始路径 `/api/health` 会原样传给 FastAPI。修改 `proxy_pass` 是否带尾部斜杠可能改变转发后的路径，这是配置反向代理时常见的错误来源。

## 7. 到底是谁选择要展示的页面

Nginx 只决定把前端请求交给 Next.js，并不知道 `page.jsx` 的具体结构。

Next.js App Router 根据 `app/` 目录选择页面：

```text
URL /          → app/page.jsx
URL /text-lab  → app/text-lab/page.jsx
未知 URL       → Next.js 的 404 页面
```

例如用户访问：

```text
https://wool0312.me/text-lab
```

完整过程是：

```text
Nginx 发现路径不是 /api/*
        ↓
转发给 127.0.0.1:3000
        ↓
Next.js 读取 URL /text-lab
        ↓
App Router 匹配 app/text-lab/page.jsx
        ↓
渲染并返回页面
```

所以“选择页面”分为两层：

1. Nginx 选择前端服务还是后端服务；
2. Next.js 在前端服务中选择具体页面。

## 8. FastAPI 怎样选择接口

当 Nginx 把 `/api/*` 请求交给 8000 端口后，FastAPI 根据 HTTP 方法和路径匹配 Python 函数。

当前项目中的例子：

```python
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    ...


@app.get("/api/history")
def history(limit: int = Query(default=10, ge=1, le=100)):
    ...
```

这意味着：

| 方法和路径 | Python 处理函数 |
| --- | --- |
| `GET /api/health` | `health()` |
| `POST /api/analyze` | `analyze()` |
| `GET /api/history?limit=10` | `history()` |

同一个路径使用不同 HTTP 方法，可以匹配不同接口。路径不存在时，FastAPI 返回 404；方法不允许时，通常返回 405。

## 9. 一次文本分析怎样写入数据库

用户提交分析时的数据流：

```text
浏览器 POST /api/analyze
        ↓
Nginx 转发到 127.0.0.1:8000
        ↓
FastAPI 校验请求文本
        ↓
SnowNLP 计算情感分数，pypinyin 生成拼音
        ↓
insert_analysis(result)
        ↓
写入 /var/lib/zero-to-tech/app.db
        ↓
FastAPI → Nginx → 浏览器返回 JSON
```

生产数据库放在代码仓库之外：

```text
/var/lib/zero-to-tech/app.db
```

这样更新 `/srv/zero-to-tech` 中的代码或重新执行 `npm ci` 时，不会覆盖历史记录。

查询最近记录：

```bash
curl -sS "http://127.0.0.1:8000/api/history?limit=10" \
  | python3 -m json.tool
```

## 10. systemd 为什么必不可少

在 SSH 中手动运行：

```bash
npm start
```

进程会依赖当前终端，终端断开后可能停止。systemd 把应用作为系统服务管理：

- 在后台运行；
- 开机自动启动；
- 进程异常退出后自动重启；
- 统一查看状态和日志；
- 用 `www-data` 而不是 root 运行应用。

前端服务的核心配置类似：

```ini
[Service]
User=www-data
Group=www-data
WorkingDirectory=/srv/zero-to-tech
Environment=NODE_ENV=production
Environment=PORT=3000
ExecStart=/usr/bin/npm start -- --hostname 127.0.0.1
Restart=on-failure
```

后端服务的核心配置类似：

```ini
[Service]
User=www-data
Group=www-data
WorkingDirectory=/srv/zero-to-tech
Environment=DATABASE_PATH=/var/lib/zero-to-tech/app.db
ExecStart=/srv/zero-to-tech/backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
```

常用命令：

```bash
systemctl status zero-to-tech-frontend --no-pager --full
systemctl status zero-to-tech-backend --no-pager --full

systemctl restart zero-to-tech-frontend
systemctl restart zero-to-tech-backend

journalctl -u zero-to-tech-frontend -n 50 --no-pager
journalctl -u zero-to-tech-backend -n 50 --no-pager
```

## 11. 旧静态部署与当前部署的区别

旧配置直接让 Nginx 读取构建目录：

```nginx
root /root/zero-to-tech/out;

location / {
    try_files $uri $uri.html $uri/ =404;
}
```

这种方式中，Nginx 自己查找 `index.html`、`text-lab.html` 等文件。它适合纯静态网站，不需要一直运行 Node.js。

当前版本增加了 FastAPI、分析接口和 SQLite 历史记录，部署改为反向代理：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
}

location / {
    proxy_pass http://127.0.0.1:3000;
}
```

现在页面由 Next.js 服务响应，API 由 FastAPI 响应。Nginx 不再直接从 `/root/zero-to-tech/out` 读取页面。

## 12. build、start 和 reload 的区别

### `npm ci`

严格按照 `package-lock.json` 安装依赖，适合部署和持续集成环境。

### `npm run build`

把 React 和 Next.js 源码编译为优化后的生产构建，结果主要放在 `.next/`。

构建时使用：

```bash
NEXT_PUBLIC_API_BASE_URL= npm run build
```

API 地址留空后，浏览器使用同域路径 `/api/...`，再由 Nginx 分流。这样不需要在浏览器中直接暴露 8000 端口，也更容易避免跨域问题。

### `npm start`

启动 Next.js 生产服务器，读取已经生成的 `.next/`。修改前端源码后，只重启服务不够，必须先重新 build。

### `nginx -t`

只检查配置语法，不切换线上配置。

### `systemctl reload nginx`

让 Nginx 平滑加载新配置。已有连接通常可以继续处理，比直接停止再启动更适合生产环境。

## 13. 常见状态码和排查方向

| 现象 | 常见含义 | 首先检查 |
| --- | --- | --- |
| `301` | HTTP 正在跳转到 HTTPS | `curl -I http://域名/` |
| `404` | 路径没有对应页面或接口 | URL、Next.js 路由、FastAPI 路由 |
| `405` | 路径存在，但 HTTP 方法错误 | GET/POST 是否正确 |
| `500` | 应用内部异常 | 对应 systemd 日志 |
| `502 Bad Gateway` | Nginx 无法连接内部服务 | 3000/8000 是否监听、服务状态 |
| 浏览器超时 | 请求可能没有到达 Nginx | DNS、阿里云防火墙、80/443 |
| 证书警告 | 域名与证书不匹配或证书过期 | 证书 SAN、有效期、系统时间 |

从外到内的排查顺序：

```bash
# 1. 内部应用是否正常
curl -I http://127.0.0.1:3000/
curl -i http://127.0.0.1:8000/api/health

# 2. 端口是否监听
ss -lntp | grep -E ':3000|:8000'

# 3. systemd 是否正常
systemctl status zero-to-tech-frontend --no-pager --full
systemctl status zero-to-tech-backend --no-pager --full

# 4. Nginx 配置是否有效
nginx -t
systemctl status nginx --no-pager --full

# 5. 域名入口是否正常
curl -I https://wool0312.me/
curl -i https://wool0312.me/api/health
```

## 14. 更新代码时发生了什么

一次常规更新可以理解为：

```text
拉取源码
  ↓
按锁文件安装前端依赖
  ↓
重新构建 Next.js
  ↓
安装或更新 Python 依赖
  ↓
重启前后端进程
  ↓
验证内部服务和公网入口
```

对应命令示例：

```bash
cd /srv/zero-to-tech
git pull --ff-only
npm ci --allow-remote=all
NEXT_PUBLIC_API_BASE_URL= npm run build
backend/.venv/bin/python -m pip install -r backend/requirements.txt
systemctl restart zero-to-tech-backend zero-to-tech-frontend

curl -i http://127.0.0.1:8000/api/health
curl -I http://127.0.0.1:3000/
curl -I https://wool0312.me/
```

`--allow-remote=all` 是当前锁文件包含远程镜像 tarball 地址时使用的一次性 npm 授权。它不应被无条件复制到不需要该选项的其他项目。

更新代码通常不需要修改 Nginx，因为域名、证书、3000 和 8000 的分流关系没有改变。只有域名、端口或服务结构变化时才需要调整 Nginx。

## 15. 一句话记住每个组件

| 组件 | 核心职责 |
| --- | --- |
| DNS | 把域名翻译成服务器 IP |
| 阿里云防火墙 | 决定哪些公网端口允许进入 |
| Nginx | HTTPS 入口、域名匹配、URL 分流和反向代理 |
| Next.js | 根据前端 URL 选择页面并返回页面内容 |
| FastAPI | 根据方法和 API 路径选择 Python 处理函数 |
| SQLite | 持久保存文本分析历史 |
| systemd | 启动、监管和自动重启前后端进程 |
| Git | 管理源码版本，不管理生产数据库 |

最核心的认识是：Nginx 不是在 React 页面之间做选择。它先把请求送到正确的应用，之后才由 Next.js 或 FastAPI 在应用内部完成更细的路由匹配。
