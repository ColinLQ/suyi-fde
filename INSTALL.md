# suyi-scm-collector Skill 全自动安装部署文档（AI 执行版）

> **本文档的目标读者是 AI 智能体。** 你（AI）收到本文档后，应按顺序执行全部步骤，在一台全新电脑上完成 suyi-scm-collector 技能的完整安装：环境依赖 → 技能本体 → MCP 配置 → 验收。执行过程中先检测操作系统，再走对应分支（Windows / macOS 命令不同）。
>
> 源仓库：https://github.com/ColinLQ/suyi-fde.git （脱敏开源版，已剔除业务数据与凭据）
> 技能本体：`suyi-scm-collector` —— 衣者 × 多客 数据采集与经营日报智能体技能

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
| 1 | Node.js | **22 或更高**（LTS） | 全部 `.mjs` 采集/计算脚本（内置 WebSocket 跑裸 CDP） | 必须 |
| 2 | Node 第三方包 | 无 | 脚本**零第三方依赖**，仓库**没有 package.json**，**不要执行 npm install** | — |
| 3 | Python | 3.9+ | Excel 日报生成脚本（`build-*.py`） | 必须 |
| 4 | Python 包：openpyxl | >= 3.1.0 | 生成 .xlsx（部分脚本缺包时会自动 pip 安装，但仍需预装） | 必须 |
| 5 | Python 包：Pillow | 最新稳定版 | 销售报表嵌商品图（PIL） | 必须 |
| 6 | Git | 任意较新版本 | 克隆仓库 | 必须 |
| 7 | 比特浏览器客户端 | **≥ 7.1.5** | 采集登录态载体（suyi 专用窗口，Local API + MCP） | 必须 |
| 8 | bitbrowser MCP | — | 智能体管理比特窗口（创建/打开）；日常采集走脚本不依赖 MCP 在线 | 必须 |
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

> ⚠️ 若 `node -v` 显示低于 v22（如 v18/v20），必须先升级：采集脚本（裸 CDP 用内置 WebSocket）要求 Node 22+。

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
git clone https://github.com/ColinLQ/suyi-fde.git suyi-scm-collector
# 验证：目录存在 SKILL.md
dir suyi-scm-collector\SKILL.md
```

**【macOS】**
```bash
mkdir -p ~/.workbuddy/skills
cd ~/.workbuddy/skills
git clone https://github.com/ColinLQ/suyi-fde.git suyi-scm-collector
# 验证：
ls suyi-scm-collector/SKILL.md
```

克隆完成后目录结构应为：
```
suyi-scm-collector/
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

## 五、第 4 步：配置比特浏览器 MCP（V1.8 起，替代原 chrome-devtools MCP）

本技能 V1.8 起用**比特浏览器（BitBrowser）**承载采集登录态，chrome-devtools MCP 已移除。需要：

1. 安装比特浏览器客户端（≥7.1.5，https://www.bitbrowser.cn ），保持运行（Local API 默认端口 54345）
2. 比特客户端「系统设置 → Local API」→ 开启**鉴权控制** → 复制 API Token
3. 写入 MCP 配置 `~/.workbuddy/mcp.json`（**Windows 为 `C:\Users\<用户名>\.workbuddy\mcp.json`**；注意是 `.workbuddy/mcp.json`，不是 `.mcp.json`）。**必须放在 `mcpServers` 字段内**（放外面不生效）：

```json
{
  "mcpServers": {
    "bitbrowser": {
      "url": "http://127.0.0.1:54345/mcp",
      "headers": {
        "x-api-key": "<比特Local API页面生成的Token>"
      }
    }
  }
}
```

> - Token 只此一份来源：skill 脚本（bit.mjs）自动读取该文件，无需另配；比特客户端重新生成 Token 后只需更新此文件
> - MCP 端仅用于智能体管理窗口（创建/打开采集窗口）；日常采集/登录校验走脚本（bit.mjs/check-login.mjs），MCP 不在线不影响主链路——但比特**客户端**必须运行
> - WorkBuddy 中写入后需在连接器管理页对 bitbrowser 点「信任」激活

### 5.2 创建专用采集窗口（suyi）

比特客户端或比特 MCP `browser-create` 创建窗口：**名称必须为 `suyi`**、代理选「不使用代理」（noproxy 直连；严禁挂海外代理——衣者/多客会触发风控）。创建后进入第 5 步登录。

---

## 六、第 5 步：登录两系统（在比特采集窗口内）

1. 打开比特浏览器 suyi 窗口（可让智能体跑 `node scripts/check-login.mjs` 自动拉起，或客户端手动「打开」）
2. 衣者：访问 `https://scm.yizheyun.com` → 账号密码登录
3. 多客：访问 `https://air.duoke.net` → 出现二维码 → 手机多客 APP「我的 → 扫一扫」扫码登录
4. 登录完成对智能体说「继续」→ 脚本从第0步重新检测

**铁律**：该窗口**绝不点「退出登录」**、不日常办公、不复用为其他账号窗口（登录态持久化在窗口 Profile 里，与比特其他窗口物理隔离）。

---

## 七、第 6 步：安装验收（AI 必须逐项跑通）

### 7.1 模拟数据自测（不依赖登录，验证脚本链完整）

先 `cd` 到技能目录（**Windows：`cd /d D:\路径\scm-collector` 或 PowerShell 直接 `cd`；macOS：`cd ~/.workbuddy/skills/suyi-scm-collector`**），逐条执行：

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

### 7.3 比特浏览器链路自测

1. 比特客户端在运行、WorkBuddy 会话中 bitbrowser MCP 已信任启用
2. AI 跑 `node scripts/bit.mjs`——应输出 `{ok:true, found:true, window:{...}}`（suyi 窗口存在且已拉起，返回动态 CDP 端口）
3. AI 跑 `node scripts/check-login.mjs`——应自动开两系统页面并输出登录态 JSON
4. 提醒用户在比特 suyi 窗口内完成两系统登录

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
| 技能目录 | `C:\Users\<用户名>\.workbuddy\skills\suyi-scm-collector\` | `/Users/<用户名>/.workbuddy/skills/scm-collector/` |
| MCP 配置文件 | `C:\Users\<用户名>\.workbuddy\mcp.json` | `~/.workbuddy/mcp.json` |
| Node 安装 | `.msi` / `winget install OpenJS.NodeJS.LTS` | `.pkg` / `brew install node@22` |
| Python 命令 | `python` / `pip` | `python3` / `python3 -m pip` |
| Python 缺失时 | `winget install Python.Python.3.12` | `xcode-select --install` 或 `brew install python` |
| 比特客户端 | 官网下载安装，开机自启建议开启（Local API 54345） | 同左 |
| 进入 D 盘目录 | `cd /d D:\suyi-scm-collector`（cmd） | 直接 `cd` |
| 删除自测产物 | `rmdir /s /q data state out` | `rm -rf data state out` |
| 中文文件名/输出乱码 | 终端执行 `chcp 65001` 切 UTF-8 | 默认 UTF-8 无需处理 |
| 常开要求 | 采集机需常开机不断电（登录态与库存历史都在本机累积）；比特客户端保持运行 | 同左 |

---

## 九、AI 执行时的排障要点

| 现象 | 处置 |
|------|------|
| `node -v` < 22 | 先升级 Node 再继续，否则脚本都会失败 |
| `pip install` 报 externally-managed（macOS） | 加 `--user` 参数或用 `python3 -m pip install --user` |
| git clone 慢/失败 | 改用下载 ZIP：`https://github.com/ColinLQ/suyi-fde/archive/refs/heads/main.zip`，解压后把文件夹改名为 `suyi-scm-collector` 放入 skills 目录 |
| bit.mjs 报「比特Local API ... HTTP 5xx/ECONNREFUSED」 | 比特客户端未运行——启动比特浏览器（Local API 默认 54345）后重试 |
| bit.mjs 报「token 失效/Login out」 | 比特客户端「系统设置→Local API」重新复制 Token，更新 mcp.json 的 bitbrowser.headers.x-api-key |
| bit.mjs 报「未找到 suyi 窗口」 | 按第 5.2 节创建窗口（noproxy，名称精确为 suyi） |
| harvest-auth 报「未发现任何Chrome DevTools端口」 | 采集窗口未拉起——跑 `node scripts/bit.mjs` 或 check-login.mjs 自动拉起后再试 |
| 仓库无 package.json | 正常设计，脚本零第三方依赖，**不要跑 npm install** |
| 脚本运行时自动 pip 装包 | 正常自愈行为（如 build-sales-excel.py 缺 openpyxl 时自动安装） |

---

## 十、红线（安装与使用都必须遵守）

1. **只读采集**：只调用 `config/endpoints.json` 注册的只读查询接口；保存/删除/导出/提交类操作一律禁止
2. **不自动登录、不绕过认证、不存账号密码**：登录态由比特浏览器 suyi 窗口 Profile 维持，凭据只从窗口实时收割、仅缓存在数据目录 `state/auth.json`（12 小时有效）
3. 采集窗口不做日常办公、不登录其他账号（防单点登录互踢）
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
- [ ] `~/.workbuddy/skills/suyi-scm-collector/SKILL.md` 存在
- [ ] `~/.workbuddy/mcp.json` 已写入 bitbrowser（在 mcpServers 内）且用户已点「信任」
- [ ] 比特客户端已安装（≥7.1.5）并运行，suyi 窗口已创建（noproxy）
- [ ] mock 六条自测命令全部跑通并已清理 `data/ state/ out/`
- [ ] 采集窗口可拉起，用户已登录两系统，`check-login.mjs` 双系统 `ok:true`
- [ ] 部署首跑完成，`out/` 产出日报
