# Zero to Tech

一个使用 Next.js、FastAPI 和 SQLite 构建的中文文本分析小应用。前端展示个人主页和文字实验室；后端提供拼音、情感分析和最近分析记录查询。

## 技术栈

- Next.js 15、React 19、Anime.js
- FastAPI、SnowNLP、pypinyin
- SQLite（Python 标准库，无需单独安装数据库服务）

## 项目结构

```text
app/                 Next.js 页面
components/          React 组件
css/                 页面样式
data/                前端展示数据
backend/
  main.py            FastAPI 应用和接口
  database.py        SQLite 初始化与读写
  requirements.txt   后端直接依赖
deploy/              Nginx 和 systemd 部署模板
```

SQLite 默认创建在 `backend/data/app.db`。数据库和 WAL 临时文件属于运行数据，不会提交到 Git。

## 本地开发

环境要求：Node.js 20+、Python 3.11+。

1. 创建本地环境文件：

   ```powershell
   Copy-Item .env.example .env.local
   ```

2. 安装并启动后端（命令均在仓库根目录执行）：

   ```powershell
   python -m venv backend/.venv
   .\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
   .\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
   ```

3. 在另一个终端启动前端：

   ```powershell
   npm install
   npm run dev
   ```

4. 打开 <http://localhost:3000>。API 文档位于 <http://127.0.0.1:8000/docs>。

Linux/macOS 激活虚拟环境后，也可以使用：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

## 环境变量

复制 `.env.example` 为 `.env.local` 后按需修改：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | 浏览器访问后端的地址；生产环境同域反向代理时留空 | 空 |
| `CORS_ORIGINS` | 允许直接访问 API 的前端来源，多个值用逗号分隔 | 本地 3000 端口 |
| `DATABASE_PATH` | SQLite 文件路径；相对路径从仓库根目录解析 | `backend/data/app.db` |

`NEXT_PUBLIC_API_BASE_URL` 会在前端构建时写入产物，修改后必须重新执行 `npm run build`。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务健康检查 |
| GET | `/api/profile` | 获取主页内容 |
| POST | `/api/analyze` | 分析中文文本并写入 SQLite |
| GET | `/api/history?limit=10` | 查询最近的分析记录，最多 100 条 |

`analysis_history` 表会在后端启动时自动创建，包含 `id`、`text`、`score`、`label`、`pinyin` 和 `created_at` 字段。

## 生产构建

```bash
npm ci
NEXT_PUBLIC_API_BASE_URL= npm run build

python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt
```

构建完成后，可分别验证两个服务：

```bash
npm start
backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Linux 单机部署

仓库提供了 Nginx 和 systemd 模板，默认假设代码位于 `/srv/zero-to-tech`，服务用户为 `www-data`。

1. 克隆或更新代码并完成上面的生产构建。
2. 创建持久化数据库目录：

   ```bash
   sudo install -d -o www-data -g www-data /var/lib/zero-to-tech
   ```

3. 检查并修改 `deploy/` 中的域名、代码路径和服务用户，然后安装配置：

   ```bash
   sudo cp deploy/zero-to-tech-backend.service /etc/systemd/system/
   sudo cp deploy/zero-to-tech-frontend.service /etc/systemd/system/
   sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/zero-to-tech
   sudo ln -s /etc/nginx/sites-available/zero-to-tech /etc/nginx/sites-enabled/zero-to-tech
   sudo systemctl daemon-reload
   sudo systemctl enable --now zero-to-tech-backend zero-to-tech-frontend
   sudo nginx -t
   sudo systemctl reload nginx
   ```

4. 验证部署：

   ```bash
   curl http://127.0.0.1:8000/api/health
   curl -I http://127.0.0.1:3000
   curl https://example.com/api/health
   ```

以后更新版本：

```bash
cd /srv/zero-to-tech
git pull --ff-only
npm ci
NEXT_PUBLIC_API_BASE_URL= npm run build
backend/.venv/bin/pip install -r backend/requirements.txt
sudo systemctl restart zero-to-tech-backend zero-to-tech-frontend
```

生产环境应配置 HTTPS。SQLite 适合单机、小流量部署；扩展到多台后端服务器前，应迁移到 PostgreSQL 等独立数据库。

## 提交前检查

```bash
npm run build
git diff --check
git status --short
```

确认 `.env.local`、`backend/data/`、虚拟环境和构建产物没有出现在待提交列表中，再执行 `git add`、`git commit` 和 `git push`。
