# SQLite 学习笔记：在 FastAPI 中保存文本分析记录

这篇笔记以当前项目为例，目标是把一次文本分析的结果保存到本地 SQLite 数据库，并提供查询最近记录的 API。

学完后应该能理解：

- SQLite 文件和数据表是怎样创建的；
- Python 如何安全地打开、提交并关闭数据库连接；
- 如何使用参数化 SQL 插入和查询数据；
- FastAPI 如何在启动时初始化数据库；
- 为什么数据库文件不应该提交到 Git。

## 1. 整体数据流

```text
用户点击“开始分析”
        ↓
POST /api/analyze
        ↓
SnowNLP 和 pypinyin 生成分析结果
        ↓
insert_analysis(result)
        ↓
写入 analysis_history 表
        ↓
返回包含数据库 id 的 JSON

GET /api/history?limit=10
        ↓
list_analyses(limit=10)
        ↓
从 SQLite 查询最近记录
```

本项目把数据库代码放在 `backend/database.py`，把 HTTP 接口放在 `backend/main.py`。这样数据库操作和业务接口不会全部堆在一个文件里。

## 2. 为什么选择 SQLite

SQLite 是一个嵌入式关系型数据库。它不需要单独启动数据库服务器，整个数据库可以保存在一个 `.db` 文件中。

它适合：

- 本地开发；
- 单机部署；
- 小型项目和学习项目；
- 数据量和并发量不大的应用。

Python 标准库已经提供 `sqlite3`，所以不需要额外安装 SQLite Python 包：

```python
import sqlite3
```

SQLite 不适合多个应用服务器同时写入同一个本地文件。如果以后部署多个后端实例，应考虑迁移到 PostgreSQL。

## 3. 数据库文件放在哪里

项目默认把数据库放在：

```text
backend/data/app.db
```

路径处理代码：

```python
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "data" / "app.db"


def get_database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH")
    if not configured_path:
        return DEFAULT_DATABASE_PATH

    database_path = Path(configured_path).expanduser()
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    return database_path.resolve()
```

这里做了三件事：

1. 没有配置 `DATABASE_PATH` 时，使用默认位置；
2. 配置绝对路径时，直接使用该路径；
3. 配置相对路径时，从项目根目录解析，不受启动命令所在目录影响。

本地 `.env.local` 可以这样配置：

```env
DATABASE_PATH=backend/data/app.db
```

生产服务器可以把数据库放到仓库之外的持久目录：

```env
DATABASE_PATH=/var/lib/zero-to-tech/app.db
```

这样重新拉取或替换代码时，不会覆盖生产数据。

## 4. 设计 analysis_history 表

建表 SQL：

```sql
CREATE TABLE IF NOT EXISTS analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
    label TEXT NOT NULL,
    pinyin TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

字段说明：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | INTEGER | 自增主键，每条记录的唯一编号 |
| `text` | TEXT | 用户提交的原文 |
| `score` | REAL | 0 到 1 的情感分数 |
| `label` | TEXT | 偏积极、偏消极或中性 |
| `pinyin` | TEXT | 原文对应的带声调拼音 |
| `created_at` | TEXT | UTC ISO 8601 创建时间 |

几个关键约束：

- `PRIMARY KEY`：保证每条记录有唯一标识；
- `AUTOINCREMENT`：插入时自动产生新的 `id`；
- `NOT NULL`：字段不能为空；
- `CHECK`：拒绝小于 0 或大于 1 的分数；
- `IF NOT EXISTS`：重复启动后端不会因为表已存在而报错。

项目还为时间字段创建了索引：

```sql
CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at
ON analysis_history(created_at DESC);
```

历史接口经常按时间倒序查询，索引可以降低数据量变大后的查询成本。

## 5. 正确管理数据库连接

连接管理是这一部分最值得理解的代码：

```python
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        with connection:
            yield connection
    finally:
        connection.close()
```

### `@contextmanager` 和 `yield`

加上 `@contextmanager` 后，函数可以这样使用：

```python
with get_connection() as connection:
    connection.execute(...)
```

执行顺序是：

1. `yield` 之前：创建并配置连接；
2. `yield connection`：把连接交给 `with` 代码块；
3. `yield` 之后：执行清理逻辑；
4. 无论成功还是异常，`finally` 都会关闭连接。

### 为什么里面还有一个 `with connection`

`with connection` 管理的是事务：

- 代码正常结束时自动 `commit`；
- 代码发生异常时自动 `rollback`。

它不会自动关闭数据库文件，所以外层仍然需要：

```python
finally:
    connection.close()
```

把“事务结束”和“连接关闭”当成两件不同的事，是使用 `sqlite3` 时很重要的细节。

### PRAGMA 配置

```python
connection.execute("PRAGMA foreign_keys = ON")
```

开启外键检查。当前表还没有外键，但以后增加用户表时可以直接使用。

```python
connection.execute("PRAGMA journal_mode = WAL")
```

启用 WAL 模式，让读取和写入更不容易互相阻塞。SQLite 可能同时生成 `.db-wal` 和 `.db-shm` 文件，这是正常现象。

```python
connection.execute("PRAGMA busy_timeout = 5000")
```

遇到数据库暂时被占用时等待最多 5 秒，而不是立刻报 `database is locked`。

## 6. 启动时自动建表

数据库初始化函数：

```python
def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
                label TEXT NOT NULL,
                pinyin TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at
            ON analysis_history(created_at DESC)
            """
        )
```

FastAPI 使用 `lifespan` 在应用启动时调用它：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="Zero to Tech API", lifespan=lifespan)
```

启动流程如下：

```text
Uvicorn 启动
    ↓
FastAPI 进入 lifespan
    ↓
init_database()
    ↓
创建目录、数据库、表和索引
    ↓
yield
    ↓
开始接收 HTTP 请求
```

这意味着第一次启动时不需要手动创建 `app.db`。

## 7. 插入一条分析记录

数据库函数：

```python
from typing import Any


def insert_analysis(record: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_history (
                text,
                score,
                label,
                pinyin,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record["text"],
                record["score"],
                record["label"],
                record["pinyin"],
                record["created_at"],
            ),
        )
        return int(cursor.lastrowid)
```

### 为什么 SQL 中使用问号

```sql
VALUES (?, ?, ?, ?, ?)
```

问号是参数占位符。真正的数据通过后面的元组传入，SQLite 会负责正确转义。

不要这样拼接用户输入：

```python
# 错误示范：可能造成 SQL 注入，也容易被引号破坏
connection.execute(f"INSERT INTO analysis_history (text) VALUES ('{text}')")
```

应该始终使用参数化 SQL：

```python
connection.execute(
    "INSERT INTO analysis_history (text) VALUES (?)",
    (text,),
)
```

注意 `(text,)` 中的逗号。Python 单元素元组必须有这个逗号。

### `lastrowid` 有什么用

插入完成后：

```python
cursor.lastrowid
```

可以得到 SQLite 自动生成的主键 `id`，接口随后把它返回给前端。

## 8. 查询最近的记录

```python
def list_analyses(limit: int = 10) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, text, score, label, pinyin, created_at
            FROM analysis_history
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

SQL 的含义：

- `SELECT`：指定需要返回的字段；
- `FROM`：指定查询的表；
- `ORDER BY created_at DESC`：最新时间排在前面；
- `id DESC`：创建时间相同时，较新的自增 ID 排在前面；
- `LIMIT ?`：只读取指定数量。

因为连接时设置了：

```python
connection.row_factory = sqlite3.Row
```

每一行都可以按字段名读取，并可以转换成字典：

```python
dict(row)
```

字典可以直接被 FastAPI 序列化为 JSON。

## 9. 接入文本分析接口

`POST /api/analyze` 先进行分析，再保存结果：

```python
from datetime import datetime, timezone


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    text = req.text
    score = round(SnowNLP(text).sentiments, 2)

    result = {
        "text": text,
        "score": score,
        "label": score_label(score),
        "pinyin": " ".join(lazy_pinyin(text, style=Style.TONE)),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    record_id = insert_analysis(result)
    return {"id": record_id, **result}
```

这里使用 UTC 时间：

```python
datetime.now(timezone.utc).isoformat(timespec="seconds")
```

示例值：

```text
2026-08-25T16:12:06+00:00
```

统一保存 UTC 时间可以避免服务器时区不同造成混乱。显示给用户时，再由前端转换成本地时间。

## 10. 接入历史记录接口

```python
from fastapi import Query


@app.get("/api/history")
def history(limit: int = Query(default=10, ge=1, le=100)):
    return list_analyses(limit=limit)
```

参数限制：

- 默认返回 10 条；
- 最少返回 1 条；
- 最多返回 100 条。

例如：

```text
GET /api/history?limit=5
```

FastAPI 会自动校验参数，`limit=0` 或 `limit=1000` 会得到 422 响应。

## 11. 完整的 database.py

当前项目的完整数据库模块如下：

```python
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "data" / "app.db"


def get_database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH")
    if not configured_path:
        return DEFAULT_DATABASE_PATH

    database_path = Path(configured_path).expanduser()
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    return database_path.resolve()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        with connection:
            yield connection
    finally:
        connection.close()


def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
                label TEXT NOT NULL,
                pinyin TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at
            ON analysis_history(created_at DESC)
            """
        )


def insert_analysis(record: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_history (
                text,
                score,
                label,
                pinyin,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record["text"],
                record["score"],
                record["label"],
                record["pinyin"],
                record["created_at"],
            ),
        )
        return int(cursor.lastrowid)


def list_analyses(limit: int = 10) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, text, score, label, pinyin, created_at
            FROM analysis_history
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

## 12. 如何查看数据库内容

后端运行时，可以直接访问：

```text
http://127.0.0.1:8000/api/history?limit=10
```

也可以在项目根目录用 Python 查询：

```powershell
.\backend\.venv\Scripts\python.exe -c "import sqlite3; from backend.database import get_database_path; db=sqlite3.connect(get_database_path()); print(*db.execute('SELECT id, text, score, label, created_at FROM analysis_history ORDER BY id DESC').fetchall(), sep='\n'); db.close()"
```

查看当前数据库路径：

```powershell
.\backend\.venv\Scripts\python.exe -c "from backend.database import get_database_path; print(get_database_path())"
```

查看表结构：

```powershell
.\backend\.venv\Scripts\python.exe -c "import sqlite3; from backend.database import get_database_path; db=sqlite3.connect(get_database_path()); print(*db.execute('PRAGMA table_info(analysis_history)').fetchall(), sep='\n'); db.close()"
```

`app.db` 是二进制文件，不应该使用普通文本编辑器打开。

## 13. 为什么数据库文件要加入 .gitignore

本项目使用以下规则：

```gitignore
/backend/data/
*.db
*.db-shm
*.db-wal
*.sqlite
*.sqlite3
```

原因包括：

- 数据库保存的是运行数据，不是源代码；
- 用户输入可能包含隐私信息；
- Git 无法有效比较二进制数据库；
- 多个人提交不同数据库文件容易产生冲突；
- WAL 模式会生成额外临时文件。

数据库结构应该通过 `CREATE TABLE` 或迁移脚本提交，数据库内容则应该通过备份系统保存。

## 14. 常见错误

### 错误一：使用相对当前目录的路径

```python
sqlite3.connect("app.db")
```

从不同目录启动应用时，可能产生多个 `app.db`。应该基于 `__file__` 或明确的环境变量计算路径。

### 错误二：只管理事务，不关闭连接

```python
with sqlite3.connect("app.db") as connection:
    connection.execute(...)
```

这个 `with` 会提交或回滚事务，但不保证立刻关闭连接。长期运行时应该明确调用 `close()`，或使用本项目的连接上下文管理器。

### 错误三：拼接 SQL

```python
connection.execute(f"SELECT * FROM analysis_history WHERE text = '{text}'")
```

应该改成：

```python
connection.execute(
    "SELECT * FROM analysis_history WHERE text = ?",
    (text,),
)
```

### 错误四：把数据库提交到 Git

数据库可能包含真实用户数据。提交前应执行：

```bash
git status --short
```

确认 `app.db`、`.db-wal` 和 `.db-shm` 没有出现在列表中。

### 错误五：把 SQLite 当成多机数据库

SQLite 文件只能位于单台机器可访问的本地磁盘上。不要让多个容器或服务器通过共享网络磁盘高并发写入同一个 SQLite 文件。

## 15. 下一步练习

可以按以下顺序继续练习：

1. 增加 `get_analysis(id)`，通过 ID 查询单条记录；
2. 增加删除接口，并观察事务提交；
3. 给历史接口增加 `offset`，练习分页；
4. 增加关键词搜索，练习带 `WHERE` 的参数化 SQL；
5. 增加 `users` 表和 `user_id` 外键；
6. 学习数据库迁移，避免修改表结构时删除已有数据；
7. 定期备份生产环境的 `app.db`。

一个分页查询示例：

```sql
SELECT id, text, score, label, pinyin, created_at
FROM analysis_history
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;
```

对应的参数仍然要通过元组传入：

```python
connection.execute(sql, (limit, offset))
```

## 16. 核心知识总结

这套实现最核心的原则是：

- 数据库路径必须稳定且可配置；
- 应用启动时自动初始化表结构；
- 每次数据库操作使用独立连接；
- 正常结束提交，异常时回滚，最后一定关闭连接；
- 用户输入只能通过参数化 SQL 传入；
- 数据库文件属于运行数据，不能提交到 Git；
- 单机小项目使用 SQLite，多机部署再迁移到独立数据库。

掌握这些原则后，即使以后换成 SQLAlchemy、SQLModel 或 PostgreSQL，数据库层的基本思路仍然相通。
