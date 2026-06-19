# AI 内容增长 Agent — 部署与使用教程

> 版本：v0.3-G  
> 定位：AI 内容运营工作台，帮助创作者完成选题→生成→审核→复盘的全流程  
> 适用场景：小红书图文内容半自动生产

---

## 一、你需要准备什么

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS / Windows / Linux 均可 |
| Python | 3.11 或更高版本 |
| Node.js | 18 或更高版本 |
| MySQL | 8.0 或更高版本 |
| 硬盘空间 | 约 500MB（含依赖） |

---

## 二、安装 MySQL（如果还没装）

### macOS

```bash
brew install mysql
brew services start mysql
```

安装完后登录 MySQL 创建数据库：

```bash
mysql -u root -p
```

进去后执行：

```sql
CREATE DATABASE ai_content_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

然后 `exit` 退出。

### Windows

1. 去 https://dev.mysql.com/downloads/mysql/ 下载 MySQL 8.0 安装包
2. 安装时记住 root 密码
3. 打开 MySQL Workbench 或命令行，执行上面的建库 SQL

### Linux (Ubuntu/Debian)

```bash
sudo apt install mysql-server
sudo systemctl start mysql
sudo mysql
```

进去后执行同样的建库 SQL。

---

## 三、安装 Python 和 Node.js（如果还没装）

### macOS

```bash
brew install python@3.11 node@20
```

### Windows

- Python: https://www.python.org/downloads/ （安装时勾选"Add to PATH"）
- Node.js: https://nodejs.org/ （下载 LTS 版本）

### Linux

```bash
# Python
sudo apt install python3.11 python3.11-venv python3-pip

# Node.js (使用 NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs
```

---

## 四、部署项目

### 1. 解压项目

把 `ai-content-agent.zip` 解压到你想要的位置，比如：

```bash
# macOS/Linux
unzip ai-content-agent.zip -d ~/projects/

# Windows：右键解压到 C:\Users\你的用户名\projects\
```

### 2. 配置环境变量

进入项目目录，复制环境变量模板：

```bash
cd ai-content-agent
cp .env.example .env
```

编辑 `.env` 文件，至少改这一行：

```
DATABASE_URL=mysql+pymysql://root:你的MySQL密码@127.0.0.1:3306/ai_content_agent?charset=utf8mb4
```

> **重要**：把 `你的MySQL密码` 换成你实际设置的密码。如果 MySQL 用户名不是 root，也相应修改。

`.env` 其他行保持默认即可，默认使用本地规则模型（不花钱，不需要 API Key）。如果你想接入真实大模型获得更好的内容质量，可以填入 DeepSeek 或其他 Key。

### 3. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

如果提示权限不够，加 `--user`：

```bash
pip install --user -r requirements.txt
```

### 4. 安装前端依赖

```bash
cd ../frontend
npm install
```

---

## 五、启动项目

打开两个终端窗口：

**终端 1 — 启动后端：**

```bash
cd ai-content-agent/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 就表示后端启动成功了。

**终端 2 — 启动前端：**

```bash
cd ai-content-agent/frontend
npx vite --host 127.0.0.1 --port 5173
```

看到 `Local: http://127.0.0.1:5173/` 就表示前端启动成功了。

然后打开浏览器，访问：**http://localhost:5173**

---

## 六、使用教程

### 界面说明

打开后你会看到左侧导航栏，有 5 个页面：

| 页面 | 功能 |
|------|------|
| Agent 工作台 | 输入一句话目标，自动生成完整发布包 |
| 选题池 | 管理和创建选题，从这里开始生产内容 |
| 素材库 | 查看和导入外部素材（URL/GitHub） |
| 指标复盘 | 录入发布数据，查看 7 天复盘 |
| 数据录入 | 手动记录各平台发布数据 |

### 方式一：Agent 工作台（推荐新手用）

1. 点击左侧「Agent 工作台」
2. 在输入框输入你的内容目标，比如：`普通人怎么用 AI 自动化副业内容`
3. 点击「启动 Agent」
4. Agent 会自动执行 10 个步骤：选题建议 → 入库 → 评分 → 生成发布包 → 生成卡片 → 合规检查 → 质量评分 → 自动改稿 → 决策摘要
5. 等待 1-2 分钟，你会看到完整的发布包，包含标题、正文、知识卡片
6. 点击卡片可以编辑样式（字号、密度等），右侧实时预览
7. 点击「导出 ZIP」可以下载所有卡片 PNG + 文案

### 方式二：选题池手动流程

1. 点击左侧「选题池」
2. 点击「自定义创作」，输入主题，选择「主题灵感创作」，生成 5 个选题建议
3. 选一个满意的，编辑标题/摘要后点击「确认入库」
4. 在选题列表中点击「评分」查看评分
5. 点击「生成」生成小红书发布包
6. 进入「发布包编辑」页面：
   - 左上角可以查看发布包内容
   - 「组合诊断」面板会给出实时结构评分
   - 点击「生成匹配卡片」生成知识小卡
   - 点击任意卡片可编辑样式
   - 完成人工审核清单

### 方式三：从 URL 导入

1. 点击「选题池」→「导入 URL」
2. 粘贴一篇 AI 相关文章的链接
3. 系统自动抓取标题和摘要，生成多个选题角度
4. 勾选想要的、编辑后入库

---

## 七、切换真实大模型

默认使用本地规则模型（不花钱，效果够用）。如果想用 DeepSeek 等真实模型提升效果：

编辑 `.env` 文件：

```bash
# 把 local 改成 deepseek
DEFAULT_LLM_PROVIDER=deepseek
DEFAULT_LLM_MODEL=deepseek-v4-pro

# 填入你的 Key 和地址
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

> **省钱提示**：日常使用 `local` 完全够用，只在需要高质量内容时切换到真实模型。切换后重启后端即可。

---

## 八、常见问题

**Q: 启动后端报错 "Can't connect to MySQL"**

检查 MySQL 是否在运行：
```bash
# macOS
brew services list | grep mysql

# Windows: 服务里找 MySQL80
# Linux
sudo systemctl status mysql
```

**Q: 端口被占用**

换端口：
```bash
# 后端换 8001
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# 前端换 5178，并指定后端地址
VITE_API_TARGET=http://127.0.0.1:8001 npx vite --host 127.0.0.1 --port 5178
```

**Q: 前端页面白屏**

1. 确认后端已启动并能访问 http://localhost:8000/api/health
2. 打开浏览器 F12 控制台看报错信息
3. 如果报 CORS 错误，编辑 `.env` 确保 `BACKEND_CORS_ORIGINS` 包含前端地址

**Q: Agent 工作台没有反应**

检查后端终端输出，确认没有报错。首次使用建议切换到「选题池」手动走一遍流程，确认每个环节正常。

---

## 九、项目结构

```
ai-content-agent/
├── SETUP.md                  ← 你正在看的文档
├── README.md                 ← 项目说明
├── .env.example              ← 环境变量模板
├── .gitignore
├── backend/
│   ├── requirements.txt      ← Python 依赖
│   └── app/
│       ├── main.py           ← FastAPI 入口
│       ├── models/           ← 数据库表定义
│       ├── schemas/          ← 请求/响应模型
│       ├── api/routes/       ← API 接口
│       ├── services/         ← 核心业务逻辑
│       ├── agents/prompts/   ← LLM 提示词
│       └── llm/              ← 多模型适配
├── frontend/
│   ├── package.json          ← Node 依赖
│   └── src/
│       ├── pages/            ← 页面组件
│       ├── components/       ← 通用组件
│       └── api/              ← 前端 API 调用
└── scripts/                  ← 测试脚本
```

---

有问题随时问！祝你内容创作顺利 🚀
