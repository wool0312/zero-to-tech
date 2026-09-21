# Zero to Tech 生产部署结构与请求流程笔记

这篇笔记以当前项目在 Linux 服务器上的实际部署方式为准，梳理代码目录、Nginx、systemd、Next.js、FastAPI 和 SQLite 之间的关系，并记录日常部署与故障排查命令。

## 1. 整体结构

生产环境建议只把 `/srv/zero-to-tech` 当作正式部署目录：

```text
GitHub
   │ git pull
   ▼
/srv/zero-to-tech                 生产代码与构建目录
   ├── .next/                     Next.js 生产构建结果
   ├── backend/.venv/             Python 虚拟环境
   ├── backend/.env               后端生产环境变量
   └── ...                        项目源码

/var/lib/zero-to-tech/app.db      生产 SQLite 数据库

/etc/systemd/system/
   ├── zero-to-tech-frontend.service
   └── zero-to-tech-backend.service

/etc/nginx/sites-enabled/         域名入口与反向代理配置
```

各目录的职责：

| 位置 | 职责 |
| --- | --- |
| `/srv/zero-to-tech` | 线上真正运行的项目，不是临时副本 |
| `/root/zero-to-tech` | 如果存在，只是另一份独立 Git 工作区；在这里构建不会更新线上服务 |
| `/var/lib/zero-to-tech/app.db` | 独立于源码保存生产历史数据，更新代码不会覆盖它 |
| `/etc/systemd/system` | 定义前后端以什么用户、目录和命令运行 |
| `/etc/nginx/sites-enabled` | 定义域名如何转发到前端和后端 |

`/srv` 是 Linux 中常用于存放服务器对外服务内容的目录。应用放在 `/srv` 后，可以让它以 `www-data` 这样的低权限用户运行，无需让应用进入 `/root` 或以 root 权限运行。

## 2. 每个组件负责什么

### 2.1 Next.js 前端

前端接收普通页面请求，监听服务器本机的 `127.0.0.1:3000`。

```bash
npm run build
npm start -- --hostname 127.0.0.1
```

`npm run build` 只生成 `.next/`，不会自动重启正在运行的前端。构建完成后必须让 systemd 重启前端进程，新构建才会上线。

### 2.2 FastAPI 后端

后端提供接口，监听服务器本机的 `127.0.0.1:8000`：

```text
POST /api/analyze
GET  /api/history
GET  /api/profile
GET  /api/health
```

只监听 `127.0.0.1` 表示 8000 端口不直接暴露到公网，外部请求必须经过 Nginx。

### 2.3 SQLite

后端通过环境变量指定生产数据库：

```ini
DATABASE_PATH=/var/lib/zero-to-tech/app.db
```

数据库放在项目目录外，可以避免重新拉取或替换源码时误删生产数据。数据库目录和文件需要允许运行后端的 `www-data` 用户读写。

### 2.4 Nginx

Nginx 是公网统一入口，通常监听 80/443：

```text
/api/*  → 127.0.0.1:8000 → FastAPI
其他路径 → 127.0.0.1:3000 → Next.js
```

### 2.5 systemd

systemd 是 Linux 的服务管理器，负责：

- 在后台运行前后端；
- 服务器开机时自动启动；
- 进程异常退出后按配置重启；
- 指定运行用户、工作目录和环境变量；
- 统一收集日志。

`.service` 文件只是配置。新建或修改 `.service` 后，需要执行 `systemctl daemon-reload`；修改源码或应用自己的 `.env` 时不需要。

## 3. 浏览器访问页面的完整流程

访问：

```text
https://wool0312.me/text-lab
```

流程如下：

```text
浏览器
  │ HTTPS GET /text-lab
  ▼
Nginx（域名、TLS、80/443）
  │ location / 命中
  ▼
127.0.0.1:3000
  │ Next.js 返回 HTML、JavaScript、CSS
  ▼
浏览器渲染文字实验室页面
```

对应 Nginx 配置的核心部分：

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## 4. 提交分析文本的完整流程

浏览器提交一句文字时：

```text
浏览器中的 React 组件
  │ POST https://wool0312.me/api/analyze
  │ JSON: {"text":"今天很开心"}
  ▼
Nginx
  │ location /api/ 命中
  ▼
127.0.0.1:8000
  │ FastAPI 校验输入、生成拼音和情感结果
  │ 向 SQLite 写入历史记录
  ▼
FastAPI 返回 JSON
  ▼
Nginx 原路转发响应
  ▼
React 更新结果卡片
```

对应 Nginx 配置：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

生产构建时使用同域 API：

```bash
NEXT_PUBLIC_API_BASE_URL= npm run build
```

变量留空后，前端请求地址是 `/api/analyze`，浏览器会自动请求当前域名，再由 Nginx 分流。这样不必把 8000 端口暴露给公网，也避免了许多跨域问题。

## 5. 历史记录的流程

分析接口会设置或读取浏览器的 `session_id` Cookie，并把会话标识随分析结果写入 SQLite。打开历史弹窗时：

```text
点击“历史记录”
  → GET /api/history
  → 浏览器携带 session_id Cookie
  → Nginx 转发到 FastAPI
  → FastAPI 按 session_id 查询 SQLite
  → 返回当前访客的记录
  → React 显示弹窗列表
```

普通窗口和无痕窗口可能看到不同历史，这是会话隔离的预期行为。

## 6. 关键配置文件

### 6.1 前端 systemd 服务

路径：`/etc/systemd/system/zero-to-tech-frontend.service`

```ini
[Unit]
Description=Zero to Tech Next.js frontend
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/srv/zero-to-tech
Environment=NODE_ENV=production
Environment=PORT=3000
ExecStart=/usr/bin/npm start -- --hostname 127.0.0.1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6.2 后端 systemd 服务

路径：`/etc/systemd/system/zero-to-tech-backend.service`

```ini
[Unit]
Description=Zero to Tech FastAPI backend
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/srv/zero-to-tech
Environment=DATABASE_PATH=/var/lib/zero-to-tech/app.db
ExecStart=/srv/zero-to-tech/backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6.3 后端环境变量

路径：`/srv/zero-to-tech/backend/.env`

```env
ALLOWED_ORIGINS=https://wool0312.me,https://www.wool0312.me
```

这个文件被 Git 忽略，因此不会随 `git pull` 自动创建。缺少该变量时，当前版本的后端会在启动阶段报错。

建议权限：

```bash
sudo chown www-data:www-data /srv/zero-to-tech/backend/.env
sudo chmod 640 /srv/zero-to-tech/backend/.env
```

## 7. 第一次注册 systemd 服务

把服务文件放到 `/etc/systemd/system/` 后：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zero-to-tech-backend
sudo systemctl enable --now zero-to-tech-frontend
```

含义：

| 命令 | 含义 |
| --- | --- |
| `daemon-reload` | 让 systemd 重新读取 `.service` 文件 |
| `enable` | 设置开机自动启动 |
| `start` | 立即启动 |
| `enable --now` | 同时设置开机启动并立即启动 |
| `restart` | 停止旧进程并重新启动 |

## 8. 标准更新部署流程

每次从 GitHub 更新生产环境：

```bash
cd /srv/zero-to-tech

git status
git pull --ff-only

npm ci --allow-remote=all
NEXT_PUBLIC_API_BASE_URL= npm run build

backend/.venv/bin/python -m pip install -r backend/requirements.txt

sudo systemctl restart zero-to-tech-backend zero-to-tech-frontend
```

随后验证：

```bash
sudo systemctl status zero-to-tech-backend --no-pager --full
sudo systemctl status zero-to-tech-frontend --no-pager --full

curl -i http://127.0.0.1:8000/api/health
curl -I http://127.0.0.1:3000/text-lab
curl -I https://wool0312.me/text-lab
```

`npm ci` 会删除旧 `node_modules`，严格按照 `package-lock.json` 安装依赖。当前锁文件含有远程镜像 tarball，所以新版 npm 需要 `--allow-remote=all`。长期应重新生成使用标准 npm registry 的锁文件，从而恢复为普通的 `npm ci`。

## 9. 手工测试接口

测试服务器内部健康接口：

```bash
curl -i http://127.0.0.1:8000/api/health
```

绕过 Nginx，直接测试后端：

```bash
curl -i -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"今天很开心"}'
```

测试经过域名和 Nginx 的完整链路：

```bash
curl -i -X POST https://wool0312.me/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"今天很开心"}'
```

## 10. 日志与状态命令

```bash
# 服务是否运行
sudo systemctl status zero-to-tech-backend --no-pager --full
sudo systemctl status zero-to-tech-frontend --no-pager --full

# 最近日志
sudo journalctl -u zero-to-tech-backend -n 100 --no-pager -l
sudo journalctl -u zero-to-tech-frontend -n 100 --no-pager -l

# 实时日志；Ctrl+C 只退出查看，不会停止服务
sudo journalctl -u zero-to-tech-backend -f

# 端口监听
sudo ss -lntp | grep -E ':3000|:8000'

# Nginx 配置和错误日志
sudo nginx -t
sudo nginx -T
sudo tail -n 100 /var/log/nginx/error.log
```

## 11. 常见故障与本次案例

### 11.1 Git 已更新，但页面仍是旧版本

检查 systemd 的真实工作目录：

```bash
sudo systemctl show zero-to-tech-frontend -p WorkingDirectory -p ExecStart
```

如果服务运行 `/srv/zero-to-tech`，在 `/root/zero-to-tech` 中执行构建不会影响线上。即使源码目录正确，`npm run build` 后也必须重启前端：

```bash
sudo systemctl restart zero-to-tech-frontend
```

### 11.2 `git status` 显示已是最新，实际远程还有提交

本地的 `origin/main` 只是上一次 fetch 时保存的远程快照。刷新它：

```bash
git fetch origin
git log --oneline --decorate -5 origin/main
git pull --ff-only
```

### 11.3 浏览器收到 502 Bad Gateway

502 通常表示 Nginx 存活，但它连接不上上游服务。按由内到外的顺序检查：

```bash
curl -i http://127.0.0.1:8000/api/health
sudo ss -lntp | grep ':8000'
sudo systemctl status zero-to-tech-backend --no-pager --full
sudo journalctl -u zero-to-tech-backend -n 100 --no-pager -l
```

本次实际故障是后端缺少 `ALLOWED_ORIGINS`，进程在导入应用时执行 `None.split()` 并退出。`Restart=on-failure` 又每隔 5 秒启动一次，所以 `status` 偶尔会短暂显示 `active (running)`。判断服务是否真正稳定，需要同时查看重启计数、日志和端口监听。

### 11.4 浏览器显示 `Remote Address: 127.0.0.1:7890`

这通常是用户电脑上的代理软件端口，不是服务器的 FastAPI 端口。判断服务器问题应以 HTTP 状态码、Nginx 日志和服务器内部的 `curl` 为准。

## 12. 更新什么后需要重启什么

| 修改内容 | 所需操作 |
| --- | --- |
| React/Next.js 源码 | `npm run build`，再重启前端 |
| Python/FastAPI 源码 | 重启后端 |
| 前端依赖 | `npm ci`、重新构建、重启前端 |
| Python 依赖 | `pip install -r ...`、重启后端 |
| `backend/.env` | 重启后端，不需要 `daemon-reload` |
| `.service` 文件 | `daemon-reload`，再重启对应服务 |
| Nginx 配置 | `nginx -t`，再 `systemctl reload nginx` |

## 13. 最重要的部署原则

1. `/srv/zero-to-tech` 是唯一生产工作区。
2. 应用使用 `www-data` 等低权限用户运行，不以 root 运行。
3. 数据库和生产配置不依赖 Git，也不能在更新源码时被覆盖。
4. 构建和启动是两件事：构建后必须重启对应服务。
5. 排障时从内到外检查：进程 → 本机端口 → Nginx → 域名 → 浏览器。
6. `active` 只是一个瞬时状态；还要结合端口、日志和重启次数判断服务是否稳定。

