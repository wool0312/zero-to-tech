# 历史记录不显示：修复与学习笔记

这份文档记录本次针对“运行前后端、分析文字后，查看历史记录却没有记录”的排查与修改。内容以本次实际修改为准，并不是整个项目的完整 Bug 审计。

## 1. 先理解：历史记录怎样找到你

当前项目用浏览器 Cookie 中的 `session_id` 区分访客，没有使用登录账号来关联历史。

正常流程如下：

```text
点击“开始分析”
  → InputCard 发 POST /api/analyze
  → 后端读取 Cookie 中的 session_id
  → 如果没有，生成一个，并通过 Set-Cookie 响应头发给浏览器
  → 把 session_id 和分析结果一起写进 SQLite
  → 浏览器保存 Cookie，页面显示分析结果

点击“历史记录”
  → TextLabView 发 GET /api/history，携带同一个 Cookie
  → 后端读取同一个 session_id
  → 查询 WHERE session_id = 当前访客的 ID
  → HistoryModal 显示返回的记录数组
```

因此，“分析结果能显示”只能说明分析接口返回了结果，并不能证明浏览器已经保存了会话 Cookie。数据库里有记录，也不代表当前访客一定能查到它。

## 2. 修改文件总览

| 文件 | 本次修改 | 作用 |
| --- | --- | --- |
| [InputCard.jsx](../components/InputCard.jsx) | 修正 fetch 的 Cookie 参数 | 分析和查历史使用同一个会话 |
| [TextLabView.jsx](../components/TextLabView.jsx) | API 地址兜底、响应检查、加载和错误状态 | 避免请求地址错误，以及把失败伪装成空记录 |
| [HistoryModal.jsx](../components/HistoryModal.jsx) | 接收并展示 loading、error | 区分加载中、失败、空记录和有记录 |
| [database.py](../backend/database.py) | 检查旧表并补充 session_id 字段 | 兼容升级前的数据库 |
| [main.py](../backend/main.py) | 限制历史查询 limit 在 1～100 | 拒绝无效或过大的查询数量 |
| [.env.example](../.env.example) | 后端示例地址改为 localhost | 与 README 中的前端访问地址保持一致 |
| [test_history.py](../backend/test_history.py) | 新增两个后端回归测试 | 检查保存、隔离、查询参数和迁移 |

注意：开始排查时，工作区已经有未提交的修改，例如会话隔离逻辑和历史弹窗。本次是在这些代码上修复问题，不是重新实现全部历史功能。`.env.local` 原本就是 `http://localhost:8000`，本次只修改了示例文件。

## 3. 直接原因：fetch 参数拼写错误

文件：`components/InputCard.jsx`。

修改前：

```js
const res = await fetch(`${API}/api/analyze`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  include: "include",
  body: JSON.stringify({ text }),
});
```

修改后：

```js
const res = await fetch(`${API}/api/analyze`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ text }),
});
```

`include` 是这里需要的参数值，参数名应该是 `credentials`。原来写成 `include: "include"`，不会启用预期的凭据行为。

本地前端是 `http://localhost:3000`，后端是 `http://localhost:8000`。端口不同，属于不同的源。此时，分析请求需要明确配置 `credentials: "include"`，才能按预期处理会话 Cookie；历史请求原本已经配置了这一项。

错误链路可以理解为：

```text
分析请求 → 后端创建会话 A → 数据写在 A 名下
浏览器没有按预期保存这次返回的会话 Cookie
历史请求 → 没有 A 的 Cookie → 后端使用另一个会话 B
查询 B 的记录 → 返回 []
```

如果浏览器原本有其他会话 Cookie，表现也可能是分析记录与查询会话不一致，而不是每次都创建全新的 B。

学习重点：JavaScript 对象中的属性名写错，不一定导致编译报错。代码能构建成功，不等于请求行为正确。

## 4. API 地址为空时，需要兜底

文件：`components/TextLabView.jsx`。

修改前：

```js
const API = process.env.NEXT_PUBLIC_API_BASE_URL;
```

修改后：

```js
const API = process.env.NEXT_PUBLIC_API_BASE_URL || "";
```

变量未配置时，原代码可能把 `undefined` 拼进请求地址。加上空字符串兜底后，请求地址是 `/api/history`，与输入组件的处理保持一致。

这里的同域请求仍然需要部署环境提供 `/api` 转发。空字符串不会自动启动后端，也不会自动配置 Next.js 代理。当前本地开发仍应配置完整的后端地址。

## 5. “请求失败”和“没有记录”必须分开

文件：`components/TextLabView.jsx`、`components/HistoryModal.jsx`。

原来的历史加载逻辑：

```js
try {
  const res = await fetch(`${API}/api/history`, { credentials: "include" });
  setHistory(await res.json());
} catch {
  // 不显示错误
}
```

它有两个问题：

- 后端没启动、网络失败或 JSON 解析失败时，异常被忽略，初始空数组会让界面显示“还没有记录”。
- HTTP 错误响应没有检查。如果返回一个错误对象，把它当成记录数组使用，可能在渲染时出错。

修改后新增两个状态：

```js
const [historyLoading, setHistoryLoading] = useState(false);
const [historyError, setHistoryError] = useState("");
```

请求逻辑变成：

```js
async function openHistory() {
  setHistoryOpen(true);
  setHistoryLoading(true);
  setHistoryError("");
  try {
    const res = await fetch(`${API}/api/history`, { credentials: "include" });
    if (!res.ok) throw new Error(`历史记录加载失败：${res.status}`);
    const items = await res.json();
    if (!Array.isArray(items)) throw new Error("历史记录返回格式不正确");
    setHistory(items);
  } catch (error) {
    setHistoryError(error.message || "历史记录加载失败，请稍后重试");
  } finally {
    setHistoryLoading(false);
  }
}
```

逐步理解：

1. 开始请求时打开弹窗、设置加载中，并清除上一次错误。
2. 用 `res.ok` 检查 HTTP 状态。`fetch` 收到 404、500 等响应时，并不会仅因为状态码就自动抛出异常。
3. 解析 JSON 后检查它是否为数组，避免把错误对象传给列表。
4. `catch` 把异常放入状态，交给页面显示。
5. `finally` 无论成功还是失败都结束加载状态。

父组件把状态传给弹窗：

```jsx
<HistoryModal
  open={historyOpen}
  items={history}
  loading={historyLoading}
  error={historyError}
  onClose={() => setHistoryOpen(false)}
/>
```

弹窗按下面的优先级显示：

| 条件 | 显示内容 |
| --- | --- |
| 正在加载 | 正在加载历史记录… |
| 加载失败 | 错误提示 |
| 加载成功，数组为空 | 还没有记录，先分析一句试试。 |
| 加载成功，数组非空 | 历史记录列表 |

这也体现了组件分工：父组件管理请求和状态，弹窗负责展示。

## 6. 修改建表代码，不会自动修改已有数据库

文件：`backend/database.py`。

原来使用了：

```sql
CREATE TABLE IF NOT EXISTS analysis_history (...)
```

它的含义是“表不存在时才创建”。如果磁盘上已有旧表，即使 Python 中的建表语句新增了 `session_id`，旧表也不会自动增加字段。后续创建依赖这个字段的索引或执行查询，就可能失败。

本次在建表之后、创建索引之前加入：

```python
columns = {row["name"] for row in connection.execute("PRAGMA table_info(analysis_history)")}
if "session_id" not in columns:
    # 保留旧记录，但不能把归属未知的记录分配给新访客。
    connection.execute("ALTER TABLE analysis_history ADD COLUMN session_id TEXT")
```

`PRAGMA table_info` 读取真实数据库的字段列表；只有缺少字段时才执行 `ALTER TABLE`。这样重复启动后端也不会重复加字段。

为什么迁移时不直接写 `TEXT NOT NULL`？旧表可能已有数据，而这些记录没有已知会话归属。本次允许旧记录的新增字段为 `NULL`，保留原数据；新分析仍然由接口写入实际会话 ID。

结果是：旧记录保留在数据库里，但不会分配给当前访客。清空数据库并不是本次修复方法，本次测试也只使用临时数据库。

学习重点：新库的表结构和已有数据库的升级步骤，是两件需要分别处理的事。本次只处理缺少 `session_id` 的旧表，不是通用数据库迁移系统。

## 7. 给历史查询数量加边界

文件：`backend/main.py`。

修改前：

```python
def history(request: Request, response: Response, limit: int = 10):
```

修改后：

```python
def history(request: Request, response: Response, limit: int = Query(default=10, ge=1, le=100)):
```

- `default=10`：没传参数时返回最多 10 条。
- `ge=1`：参数必须大于等于 1。
- `le=100`：参数必须小于等于 100。

例如 `/api/history?limit=20` 合法，`limit=0`、`limit=-1` 和 `limit=101` 返回 422。限制负数也避免了 SQLite 负数 LIMIT 不限制返回数量的行为。

这是额外修复的输入校验问题，不是默认点击历史为空的直接原因。

## 8. 本地地址统一使用 localhost

文件：`.env.example`。

```dotenv
# 修改前
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000

# 修改后
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

README 引导访问 `http://localhost:3000`，因此后端示例也统一使用 `localhost`。

需要区分两个概念：

- `localhost:3000` 和 `localhost:8000` 端口不同，是跨源请求，需要配合 CORS 和请求凭据配置。
- `localhost` 和 `127.0.0.1` 虽然都能指向本机，但浏览器不会把这两个主机名视为同一个站点。混用时，后端当前的 `SameSite=Lax` Cookie 可能无法用于跨站 fetch。

后端原本已有 `allow_credentials=True` 和明确的本地 CORS 来源列表，本次没有修改这些设置。`credentials: "include"` 也不能绕过浏览器的 SameSite 或 Cookie 限制。

## 9. 新增测试做了什么

文件：`backend/test_history.py`，使用 `unittest` 和 FastAPI 的 `TestClient`。

### 测试一：保存、会话隔离和查询校验

`test_history_persists_and_isolates_visitors` 验证：

1. 分析请求成功，响应给客户端设置 `session_id`。
2. 同一客户端能查询到刚才的分析文字。
3. `limit` 为 0、-1、101 时返回 422。
4. 另一个客户端查询不到前一个访客的记录。
5. 新客户端带回原来的会话 ID 后，仍能查到记录。

### 测试二：旧表迁移和数据保留

`test_old_schema_is_migrated_without_exposing_records` 验证：

1. 人工建立一张没有 `session_id` 的旧表，并插入旧记录。
2. 连续执行两次初始化，确认迁移可重复运行。
3. 新访客查不到归属未知的旧记录。
4. 迁移后可以正常分析并查询新记录。
5. 数据库最终同时保留旧记录和新记录。

测试通过临时目录和临时 `DATABASE_PATH` 隔离数据，不会把测试记录写进项目实际使用的 `backend/data/app.db`。

编写测试时还遇到一个 Windows 文件占用问题：`with sqlite3.connect(...)` 管理事务，但不会在退出时自动关闭连接。测试改用 `closing(sqlite3.connect(...))`，并在写入后显式提交，确保临时数据库能正常清理。业务代码中的 `get_connection()` 原本就有 `finally: connection.close()`。

## 10. 验证结果与复现方法

本次已经执行：

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.test_history -v
npm run build
git diff --check
```

结果：两个后端测试通过，Next.js 生产构建通过，差异检查没有空白错误。测试输出有 TestClient 的依赖弃用提示，Git 输出有换行符提示，均未造成检查失败。

验证范围：这些结果验证了后端逻辑和前端构建，尚未在真实浏览器里实际点击验证。TestClient 不会完整模拟浏览器的 CORS、SameSite 和跨源 Cookie 策略，因此浏览器中的参数修复还应按下面步骤确认。

### 手动验证

1. 确认 `.env.local` 中为 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`。
2. 在项目根目录启动或重启后端：

   ```powershell
   .\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
   ```

3. 在另一个终端启动前端：

   ```powershell
   npm run dev
   ```

4. 打开 `http://localhost:3000/text-lab`，输入一句新文字，点击“开始分析”。
5. 等待结果显示后点击“历史记录”，应看到刚刚的分析。
6. 刷新页面后再次查看历史，应仍能看到同一会话的记录。
7. 在独立的无痕会话中查看，应看不到普通窗口的历史；这是当前访客隔离设计的预期行为。

如果修改了前端环境变量，需要重启开发服务；生产环境需要重新构建。

### 如果仍然没有记录，按请求链路排查

打开浏览器开发者工具的 Network 面板，先检查 `/api/analyze`，再检查 `/api/history`。

| 检查项 | 预期 | 不符合时优先检查 |
| --- | --- | --- |
| 分析响应状态 | 200 | 后端日志、数据库写入错误 |
| 首次会话的分析响应 | 包含设置 session_id 的 Set-Cookie | 后端是否运行当前代码、浏览器是否阻止 Cookie |
| 历史请求 Cookie | 携带与分析相同的 session_id | credentials、主机名、浏览器 Cookie 策略 |
| 历史响应状态 | 200 | API 地址、CORS、后端日志 |
| 历史响应内容 | 包含刚分析文字的数组 | 会话是否一致、是否连接同一个数据库 |
| 弹窗显示 | 与响应数组一致 | 前端是否加载最新代码、控制台是否报错 |

`session_id` 配置了 `HttpOnly`，不要用 `document.cookie` 是否能读到它来判断保存成功。应通过开发者工具的 Cookie 存储或网络请求信息检查。

之前没有正确关联当前会话的记录，不会因为修正参数就自动改成当前访客的记录。请用修复后新分析的文字验证。

## 11. 建议的代码阅读顺序

1. `InputCard.jsx`：学习点击按钮、发送请求、传回结果。
2. `backend/main.py` 的 `get_session_id()` 和 `analyze()`：学习读取 Cookie、设置 Cookie、保存结果。
3. `backend/database.py` 的 `insert_analysis()` 和 `list_analyses()`：学习带会话字段的写入和条件查询。
4. `TextLabView.jsx` 的 `openHistory()`：学习异步请求、状态和错误处理。
5. `HistoryModal.jsx`：学习如何根据状态选择界面内容。
6. `backend/test_history.py`：学习如何用测试验证保存、查询和访客隔离。

排查过程中曾口头误判 INSERT 占位符数量，随后复核并更正：原代码就是六个字段对应六个占位符，没有这一项 Bug，本次未修改 INSERT 占位符。
