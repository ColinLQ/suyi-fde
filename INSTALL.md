# scm-collector Skill 全自动安装部署文档（AI 执行版）

> **本文档的目标读者是 AI 智能体。** 你（AI）收到本文档后，应按顺序执行全部步骤，在一台全新电脑上完成 scm-collector 技能的完整安装：环境依赖 → 技能本体 → MCP 配置 → 验收。执行过程中先检测操作系统，再走对应分支（Windows / macOS 命令不同）。
>
> 源仓库：https://github.com/ColinLQ/suyi-fde.git （脱敏开源版，已剔除业务数据与凭据）
> 技能本体：`scm-collector` —— 衣者 × 多客 数据采集与经营日报智能体技能

---

## 〇、开始前：先判定操作系统

执行任何命令前，先确认目标系统：

```bash
# Windows（cmd/powershell）与 macOS（zsh/bash）命令语法差异大，
# 下文每一步都标了【Windows】/【macOS】两个分支，只执行匹配当前系统的分支。
```

判定方法：AI 可通过自身运行环境获取 OS 类型；或执行 `uname -s`（macOS/Linux 返回 Darwin/Linux，Windows 该命令通常不存在）。

---

## 一、环境与依赖总览

| # | 组件 | 版本要求 | 用途 | 是否必须 |
|---|------|---------|------|---------|
| 1 | Node.js | **22 或更高**（LTS） | 全部 `.mjs` 采集/计算脚本、chrome-devtools MCP 运行时 | 必须 |
| 2 | Node 第三方包 | 无 | 脚本**零第三方依赖**，仓库**没有 package.json**，**不要执行 npm install** | — |
| 3 | Python | 3.9+ | Excel 日报生成脚本（`build-*.py`） | 必须 |
| 4 | Python 包：openpyxl | >= 3.1.0 | 生成 .xlsx（部分脚本缺包时会自动 pip 安装，但仍需预装） | 必须 |
| 5 | Python 包：Pillow | 最新稳定版 | 销售报表嵌商品图（PIL） | 必须 |
| 6 | Git | 任意较新版本 | 克隆仓库 | 必须 |
| 7 | Chrome 浏览器 | 当前稳定版 | 采集登录态载体（专用 Profile + 调试端口） | 必须 |
| 8 | chrome-devtools MCP | latest | AI 操作采集浏览器（list_pages/new_page 等） | 必须 |
| 9 | WorkBuddy（或同类支持 Skill + MCP 的智能体宿主） | — | 技能运行环境 | 必须 |

**凭据与账号（人工准备，AI 不得代填）**：衣者管理账号（账密登录 scm.yizheyun.com）、多客黑端账号（手机 APP 扫码登录 air.duoke.net）。安装阶段只需装好环境并打开登录页，**登录动作必须由用户本人完成**。

---

## 二、第 1 步：安装 Node.js 22+

**【Windows】**
```powershell
# 方式A（推荐，命令行静默安装）：用 winget
winget install OpenJS.NodeJS.LTS
# 方式B：打开 https://nodejs.org 下载 22.x LTS 的 .msi 安装包，一路下一步
# 验证（新开一个终端窗口）：
node -v    # 应输出 v22.x.x
npm -v     # 应输出 10.x 及以上
```

**【macOS】**
```bash
# 方式A（推荐，有 Homebrew 时）：
brew install node@22 && brew link node@22 --overwrite --force
# 方式B：打开 https://nodejs.org 下载 22.x LTS 的 .pkg 安装包，一路安装
# 验证：
node -v    # 应输出 v22.x.x
```

> ⚠️ 若 `node -v` 显示低于 v22（如 v18/v20），必须先升级：chrome-devtools-mcp 与采集脚本均要求 Node 22+。

---

## 三、第 2 步：安装 Python 3 + 依赖包

**【Windows】**
```powershell
winget install Python.Python.3.12
# 验证（新开终端）：
python --version    # 应输出 3.12.x
# 安装依赖包：
python -m pip install --upgrade pip
python -m pip install "openpyxl>=3.1.0" Pillow
# 验证：
python -c "import openpyxl, PIL; print(openpyxl.__version__, PIL.__version__)"
```

**【macOS】**
```bash
# macOS 自带 python3（Clang 工具链附带）。验证：
python3 --version    # 应输出 3.9+；若提示需要安装开发者工具，执行：
xcode-select --install   # 弹窗确认安装后再验证
# 依赖包：
python3 -m pip install "openpyxl>=3.1.0" Pillow
# 若报 externally-managed-environment（PEP 668），改用：
python3 -m pip install --user "openpyxl>=3.1.0" Pillow
# 验证：
python3 -c "import openpyxl, PIL; print(openpyxl.__version__, PIL.__version__)"
```

> 📌 注意差异：后续所有 Python 命令，Windows 用 `python`，macOS 用 `python3`。

---

## 四、第 3 步：安装 Git 并克隆技能仓库

**【Windows】**
```powershell
winget install Git.Git    # 已装可跳过
git --version             # 验证
```

**【macOS】**
```bash
git --version    # 首次执行若弹窗，按提示安装 Command Line Tools 即可
```

**【两平台通用】克隆到 WorkBuddy 用户级技能目录**（`~/.workbuddy/skills/`，没有 skills 文件夹就先创建）：

**【Windows】**（PowerShell）
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.workbuddy\skills" | Out-Null
cd "$env:USERPROFILE\.workbuddy\skills"
git clone https://github.com/ColinLQ/suyi-fde.git scm-collector
# 验证：目录存在 SKILL.md
dir scm-collector\SKILL.md
```

**【macOS】**
```bash
mkdir -p ~/.workbuddy/skills
cd ~/.workbuddy/skills
git clone https://github.com/ColinLQ/suyi-fde.git scm-collector
# 验证：
ls scm-collector/SKILL.md
```

克隆完成后目录结构应为：
```
scm-collector/
├── SKILL.md        ← 技能操作规程（AI 每次执行前必读）
├── README.md       ← 部署与操作手册
├── scripts/        ← Node(.mjs) + Python(.py) 脚本
├── config/         ← endpoints.json（采集端点注册表）、rules.json（业务参数）
├── references/     ← 按需加载的口径文档
├── state/ data/ out/   ← 运行时自动生成，勿手工清理 state
└── CHANGELOG.md
```

> 💡 WorkBuddy 用户级技能位于 `~/.workbuddy/skills/`（Windows 为 `C:\Users\<用户名>\.workbuddy\skills\`），放入后重启 WorkBuddy 会话即可被识别加载。

---

## 五、第 4 步：配置 chrome-devtools MCP

这是本技能**唯一必须的 MCP**——AI 通过它操作采集浏览器（打开页面、校验登录态、兜底 UI 采集）。

### 5.1 写入 MCP 配置

配置文件路径：`~/.workbuddy/mcp.json`（**Windows 为 `C:\Users\<用户名>\.workbuddy\mcp.json`**；注意是 `.workbuddy/mcp.json`，不是 `.mcp.json`）。

**若文件已存在**：读取现有内容，把 `chrome-devtools` 合并进 `mcpServers` 字段，**不得覆盖其他已有 server**。

**若文件不存在**：创建并写入以下内容（两平台通用）：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

**推荐变体（配合第 5 步专用采集浏览器，登录态共用）**：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--browser-url=http://127.0.0.1:9222"]
    }
  }
}
```

> 选变体时必须先按第 5 步把 Chrome 以调试端口 9222 启动，MCP 才能连上；此模式下 MCP 不会自己拉起浏览器。
> 不确定选哪个就用第一种（MCP 自管浏览器，Profile 持久化，登录一次长期有效）——本技能的凭据收割脚本会自动发现 MCP 拉起的随机调试端口。

**【Windows 特有】若 MCP 启动报 "npx not found"**，改用 cmd 包裹写法：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "cmd",
      "args": ["/c", "npx", "-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

### 5.2 激活 MCP（WorkBuddy 专属步骤）

写入 `mcp.json` 后 **MCP 不会自动生效**。需要用户在 WorkBuddy 中操作：打开连接器管理页面 → 右上角「自定义连接器」入口 → 找到 `chrome-devtools` → 点击**「信任」**启用。AI 应在完成后提醒用户执行此步（此步涉及用户授权，AI 不可跳过提示）。

---

## 六、第 5 步：准备 Chrome 采集浏览器

本技能要求一个**专用 Chrome**（独立 Profile，只跑采集不办公），两种形态二选一：

### 形态 A：MCP 自管浏览器（省事，推荐新机首选）

什么都不用配。首次使用时让 AI 说「检查登录状态」，AI 会用 chrome-devtools MCP 打开浏览器和两系统页面，用户**在这个浏览器里**完成登录，Profile 持久化后登录态长期保留。

### 形态 B：手动启动专用 Chrome + 固定调试端口（与 MCP 配置 `--browser-url` 变体配套）

**【Windows】** 桌面右键 → 新建 → 快捷方式，目标填：
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir=D:\scm-profile --remote-debugging-port=9222
```
（Chrome 装在其他位置就改前半段路径；建议把快捷方式命名为「采集浏览器」）

**【macOS】** 在 `~/.zshrc` 加别名，或直接执行：
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --user-data-dir=$HOME/scm-profile --remote-debugging-port=9222
```
（macOS 也可在「自动操作/快捷指令」里做一个启动器；Chrome 未安装时先从 https://www.google.com/chrome 下载安装）

**启动后登录两系统（人工操作，AI 只负责打开页面）：**
1. 衣者：访问 `https://scm.yizheyun.com` → 账号密码登录
2. 多客：访问 `https://air.duoke.net` → 出现二维码 → 手机多客 APP「我的 → 扫一扫」扫码登录

**铁律**：此浏览器**绝不点「退出登录」**、不日常办公、用完直接关窗口（登录态保留在 Profile 里）。

---

## 七、第 6 步：安装验收（AI 必须逐项跑通）

### 7.1 模拟数据自测（不依赖登录，验证脚本链完整）

先 `cd` 到技能目录（**Windows：`cd /d D:\路径\scm-collector` 或 PowerShell 直接 `cd`；macOS：`cd ~/.workbuddy/skills/scm-collector`**），逐条执行：

```bash
node scripts/mock-capture.mjs --slot am
node scripts/ingest.mjs --slot am
node scripts/match-template-no.mjs
node scripts/alert-rules.mjs
node scripts/reconcile.mjs
node scripts/report-daily.mjs
```

**验收标准**：`out/` 目录下生成当天的「日报-*.md / 日报-*.txt」等文件，全程无 `Cannot find module`、无 Node 版本报错。

> ⚠️ 自测产物是模拟数据。全部通过后**删除 `data/`、`state/`、`out/` 三个目录**（Windows：`rmdir /s /q data state out`；macOS：`rm -rf data state out`），从干净状态开始正式使用。**只删这三个运行时目录，绝不动 scripts/config/references。**

### 7.2 Python 链路自测

```bash
# Windows: python    macOS: python3
python3 scripts/build-sales-excel.py --help 2>&1 | head -5 || python3 -c "import openpyxl, PIL; print('py deps OK')"
```
（只要 import 不报错即算通过；部分脚本无 --help 参数，以 import 验证为准。）

### 7.3 MCP 与浏览器链路自测

1. 确认 WorkBuddy 会话中 chrome-devtools MCP 工具可用（工具列表出现 `list_pages` / `new_page` 等）
2. AI 调用 `list_pages` 检查浏览器 → `new_page` 打开 `https://scm.yizheyun.com/sample-management/list` 与 `https://air.duoke.net/goods/list`
3. 提醒用户在采集浏览器中完成两系统登录

### 7.4 登录态检查（用户登录后）

```bash
cd <技能目录>
node scripts/harvest-auth.mjs --check
```
输出应显示两个系统登录态有效。也可以直接对 WorkBuddy 说「**检查登录状态**」让 AI 执行同一命令。

### 7.5 正式首跑（全部就绪后）

对 WorkBuddy 说：
> 跑采集——部署首跑，包含 onetime 端点

**成功标志**：`data/raw/<今天>/am/` 下出现约 30 个采集文件；`out/` 下出现日报、五部门分版和看板 HTML；校验差异记录在 `state/capture-issues.jsonl`（不静默丢弃）。

---

## 八、Windows / macOS 差异速查表

| 事项 | Windows | macOS |
|------|---------|-------|
| 技能目录 | `C:\Users\<用户名>\.workbuddy\skills\scm-collector\` | `/Users/<用户名>/.workbuddy/skills/scm-collector/` |
| MCP 配置文件 | `C:\Users\<用户名>\.workbuddy\mcp.json` | `~/.workbuddy/mcp.json` |
| Node 安装 | `.msi` / `winget install OpenJS.NodeJS.LTS` | `.pkg` / `brew install node@22` |
| Python 命令 | `python` / `pip` | `python3` / `python3 -m pip` |
| Python 缺失时 | `winget install Python.Python.3.12` | `xcode-select --install` 或 `brew install python` |
| Chrome 可执行文件 | `"C:\Program Files\Google\Chrome\Application\chrome.exe"` | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` |
| 专用 Profile 目录 | `D:\scm-profile` | `~/scm-profile` |
| 进入 D 盘目录 | `cd /d D:\scm-collector`（cmd） | 直接 `cd` |
| MCP 启动 npx 异常时 | `cmd /c npx -y chrome-devtools-mcp@latest` | 直接 `npx` |
| 删除自测产物 | `rmdir /s /q data state out` | `rm -rf data state out` |
| 中文文件名/输出乱码 | 终端执行 `chcp 65001` 切 UTF-8 | 默认 UTF-8 无需处理 |
| 常开要求 | 采集机需常开机不断电（登录态与库存历史都在本机累积） | 同左 |

---

## 九、AI 执行时的排障要点

| 现象 | 处置 |
|------|------|
| `node -v` < 22 | 先升级 Node 再继续，否则 MCP 与脚本都会失败 |
| `pip install` 报 externally-managed（macOS） | 加 `--user` 参数或用 `python3 -m pip install --user` |
| git clone 慢/失败 | 改用下载 ZIP：`https://github.com/ColinLQ/suyi-fde/archive/refs/heads/main.zip`，解压后把文件夹改名为 `scm-collector` 放入 skills 目录 |
| MCP 启动后工具列表无变化 | 确认用户已在 WorkBuddy「自定义连接器」中点了「信任」；确认写的是 `.workbuddy/mcp.json`（不带点前缀） |
| `--browser-url` 模式连不上 9222 | 采集浏览器没启动或启动时没带调试参数——先按第 5 步形态 B 启动 Chrome；或回退为 MCP 自管浏览器配置 |
| `harvest-auth.mjs` 报「未发现任何Chrome DevTools端口」 | 浏览器未启动；让 AI 用 MCP 的 new_page 拉起浏览器后再试 |
| 仓库无 package.json | 正常设计，脚本零第三方依赖，**不要跑 npm install** |
| 脚本运行时自动 pip 装包 | 正常自愈行为（如 build-sales-excel.py 缺 openpyxl 时自动安装） |

---

## 十、红线（安装与使用都必须遵守）

1. **只读采集**：只调用 `config/endpoints.json` 注册的只读查询接口；保存/删除/导出/提交类操作一律禁止
2. **不自动登录、不绕过认证、不存账号密码**：登录态由专用浏览器 Profile 维持，凭据只从浏览器实时收割、仅缓存在数据目录 `state/auth.json`（12 小时有效）
3. 专用 Chrome 不做日常办公（防单点登录互踢）
4. 采集机常开机：快照漏一天就永久缺一天
5. `state/` 目录运行时勿手工清理；自测后的清理仅限数据目录下 `data/ state/ out/` 三个运行时目录
6. **仓库只含代码不含数据**：业务数据（auth.json、采集快照、报表）全部在数据目录，不得提交回仓库

---

## 十一、数据目录（V1.6 起，代码与数据分离）

- **代码目录**：skill 安装目录（本仓库克隆内容），运行**不会**在其中写入任何数据
- **数据目录**：所有运行时数据（`state/`、`data/raw/`、`out/`、可选 `config-local/`）的根，默认 `~/WorkBuddy/scm-collector-data/`（Windows 同理解析到用户主目录），可用环境变量 `SCM_DATA_HOME` 覆盖；首次运行自动创建，无需手工初始化
- **敏感配置**：内部账户清单等业务敏感项放数据目录 `config-local/sales-params.local.json`（参考仓库内 `config/sales-params.json` 的键名），脚本运行时优先读取本地文件，仓库内文件仅为脱敏模板
- 本文档与 SKILL.md 中提到的 `out/...`、`state/...`、`data/raw/...` 均指**数据目录**下的相对路径

---

## 附：定时任务（可选，安装完成后按需配置）

验收通过后，可在 WorkBuddy「定时任务/自动化」中按 README 步骤 6 配置：早间 08:30 日报、晚间 18:30 全量+对账、每小时预警轮询、周一 07:00 维度刷新。提示词原文见仓库 `README.md` 步骤 6 表格，**照抄勿改写**。

---

**安装完成判定清单（AI 逐项确认后才算完成）：**
- [ ] `node -v` ≥ v22
- [ ] `python3 --version`（或 `python --version`）≥ 3.9，且 `import openpyxl, PIL` 成功
- [ ] `~/.workbuddy/skills/scm-collector/SKILL.md` 存在
- [ ] `~/.workbuddy/mcp.json` 已写入 chrome-devtools 且用户已点「信任」
- [ ] mock 六条自测命令全部跑通并已清理 `data/ state/ out/`
- [ ] 采集浏览器可拉起，用户已登录两系统，`harvest-auth.mjs --check` 双系统有效
- [ ] 部署首跑完成，`out/` 产出日报
