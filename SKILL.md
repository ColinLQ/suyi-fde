# scm-collector Skill

> 衣者 × 多客 数据采集与经营日报智能体技能（V1.5 瘦身分层版）

## 铁律（每次执行前必读）

1. **直连采集为默认**：`scripts/fetch-endpoints.mjs` 直调 `api.yizheyun.com` / `api.duoke.net` 的**只读查询**接口（仅限 endpoints.json 注册端点，**严禁**保存/新建/删除/导入导出类接口）。凭据来自采集浏览器实时登录态（CDP收割，harvest-auth.mjs），不自动登录、不绕过认证、不存账号密码。直连整系统失败 → 读 `references/采集兜底.md` 走浏览器UI采集
2. **每次运行第0步必须实际调用 `list_pages`** 检查/唤起采集浏览器——禁止凭记忆假设登录态、禁止跳过
3. **未登录 → 硬停且不做任何数据回答**：检测到任一系统未登录（登录页/code=201/凭据失效），**立即停止后续所有步骤**（不进入第1步采集、不跑后处理链、不生成日报、不推送、**不呈现任何产出文件、不做任何数据类回答——连既有缓存日报也不能发**），仅做一件事：通知用户去登录。对话+企微双通道提醒「{系统名}未登录，请登录后说继续」，并追加 `state/login-events.jsonl`。**禁止**用旧缓存数据生成日报冒充当日数据；用户说"继续"后从第0步重新检测
4. **Demo模式仅当用户明确说"demo/模拟数据"**时使用（`scripts/mock-capture.mjs`）
5. **只读红线（含页内脚本）**：evaluate_script/CDP 可用于只读查询与翻页驱动，但保存/删除/导出/提交类写操作一律禁止（「导出」按钮未获用户明确放开前禁止点击）

## 触发条件

- 用户说：跑采集 / 出日报 / 发日报 / 看库存 / 采集衣者 / 采集多客 / 检查登录状态 / 补货分析 / 核算X月成本
- 定时（WorkBuddy 定时任务唤起，Skill内无定时器；批次表见 `references/推送与排程.md`）
- 事件：登录恢复后续采

## 执行流程

```
第0步 浏览器在线检查（list_pages → 必要时 new_page 两系统页面 → **登录态硬校验**）
→ 第1步 直连采集 fetch-endpoints.mjs
→ 第2步 后处理链 ingest → match → alert → reconcile → report → notify
→ （可选）第2.5步 补货深度分析 → 第3步 呈现产出
未登录 → 登录阻断流程（全流程硬停+零数据回答，只通知登录）；直连整系统失败 → references/采集兜底.md
```

### 第0步：确保采集浏览器在线并已登录（必做）

1. 调用 `mcp__chrome-devtools__list_pages` 实际检查（MCP按需自动拉起浏览器）
2. 无两系统页面 → `new_page` 打开 `https://scm.yizheyun.com/sample-management/list` 与 `https://air.duoke.net/goods/list`（触发带凭据的请求，喂给第1步收割），`wait_for` 任意列表文案或等3秒
3. **登录态硬校验（V1.6 新增，不可跳过）**：
   - 任一页面 URL 跳转到登录页（如 `scm.yizheyun.com/user/login`）或 `take_snapshot` 可见登录表单 → 判定该系统**未登录** → 立即进入【登录阻断流程】，**不进入第1步**
   - 两页面均停留在业务列表页 → 第1步
   - 若因故无法打开页面（超时/浏览器异常），先按「异常处理速查」恢复浏览器再校验；恢复失败才允许带着明确披露进入第1步（由第1步的 auth 判定兜底）

### 第1步：直连采集

```bash
node scripts/fetch-endpoints.mjs --batch <morning|noon|evening|poll|weekly|first> [--date YYYY-MM-DD] [--slot am|pm] [--only 文件名,…]
```

脚本自动完成：凭据收割（DevTools端口自动发现，实时localStorage直读→网络监听回落→auth.json缓存回落）→ 批次tier映射 → 并发直调只读接口 → 分页落盘 `data/raw/<日期>/<槽>/` → 校验记 `state/capture-issues.jsonl`。末行输出JSON总摘要。

**判定与分支**：
- `ok=true` → 第2步
- `auth.yizhe=false` 或 `auth.duoke=false` → 【登录阻断流程】
- 报「未发现任何Chrome DevTools端口」→ `references/采集兜底.md` 附A（MCP请求文件导入；多客key在IndexedDB的细节也在该文档）
- 个别端点失败非auth原因 → 记issue继续第2步，日报披露缺项，按报错自愈更新 endpoints.json
- 整系统失败（批量404/结构变化/持续超时）→ `references/采集兜底.md` 附B（浏览器UI采集）

**「检查登录状态」** → `node scripts/harvest-auth.mjs --check`

【登录阻断流程】（V1.7 起为硬停+零数据回答）：
1. **立即停止后续所有步骤**——不跑后处理链、不生成/更新日报、不推送企微、**不呈现任何产出文件（含当日既有日报）、不做任何数据类回答/摘要/表格**
2. 只做一件事——**通知去登录**：对话告知用户：「⛔ {系统名}未登录（原因：登录页跳转/code=201账号在别处登录/凭据失效），本次流程已停止。请在采集浏览器登录 {系统名} 后对我说“继续”，我将从头重新检测」
3. 若在企微可推送时段且通道可用，同步推送一条登录提醒（复用 notify 通道A；通道失效则仅对话提醒，不额外折腾）
4. 追加 `state/login-events.jsonl`（时间/系统/原因/触发批次）
5. **禁止**用旧缓存数据生成日报冒充当日数据，**禁止呈现/重发任何数据产出**（日报/看板/预警/分析一律不发）
6. 用户说"继续"后**从第0步**重新检测（不从第1步，确保登录态真实有效）

### 第2步：后处理脚本链（cd 到 skill 根目录，Node 22）

```bash
node scripts/ingest.mjs --date <日期> --slot <am|pm>
node scripts/match-template-no.mjs
node scripts/alert-rules.mjs --date <日期>
node scripts/reconcile.mjs --date <日期>
node scripts/report-daily.mjs --date <日期>
node scripts/notify.mjs --date <日期>        # 企微推送（双通道，见 references/推送与排程.md）
```

款号人工核对回写：用户确认「SKxxx 对应 SMxxx」→ 写入 `state/mapping.json`（细节见 `references/分析口径.md`）。

### 第2.6步：双系统库存差异比对（衣者 vs 多客）

```bash
node scripts/stock-diff.mjs --from 2026-09-28 --to 2026-10-09 [--top 20]
```

→ `out/库存差异-<from>_<to>.md`（口径体检 + 多客多时点库存动态 + 款级差异分层 + Top清单 + 未匹配款）与同名 .json。
口径体检自动判定衣者 `total_num` 属"当前库存"还是"累计入库"，判定为累计时报告会显式告警（禁止拿两系统量级差异当真实落差）。细节见 `references/分析口径.md`「双系统库存差异比对」。

### 第2.5步：补货深度分析（净缺口×季节×地区）

```bash
node scripts/fetch-orders-region.mjs --days 30   # 可选：30日订单含收件信息
node scripts/restock-deep.mjs [--date 日期]       # → out/restock-deep-<日期>.json + out/补货深度分析-<日期>.md
```

⚠️ 早间批次跑此步前先确认当日槽有 `yizhe_production_list.jsonl`，无则先复制最近快照重跑 ingest（盲区细节见 `references/分析口径.md`）。公式、季节三分类、地区解析、商业事实结论均在 `references/分析口径.md`。

### 月度成本核算

按 `references/分析口径.md` 的「月度成本核算方法」执行（窗口重定向采集 + 动销拼接 + SKU成本价加权，含全部口径坑清单）。

### 销售数据报表（V2，2026-10-10 起；业务负责人需求14项全量）

触发词：**「跑销售日报」** / 「出销售报表」。执行链（第0/1步登录校验通过后）：

```bash
node scripts/refresh-recent.mjs          # ① 增量刷近20日订单+新单明细（1-3分钟）
node scripts/build-dedup-groups.mjs      # ② 客户账户合并组（周一跑；平时跳过）
node scripts/build-sales-report-v2.mjs   # ③ V2报表 → out/销售数据报告-<日期>.md/.json（中间产物）
node scripts/fetch-goods-pics.mjs        # ④ 商品图增量下载（有缓存，缺图才拉）
python3 scripts/build-sales-excel.py     # ⑤ 最终交付：Excel 嵌图版 → out/销售数据报表-<日期>.xlsx
```

- 口径要点：客户按**同人账户合并**（同名/同手机号归并，组明细见审计表）；客单价=购买金额÷购买单数（退单不计）；补单金额=老客（非首单）下单金额；流失档位30-60天/60天-1年/1-2年；款级窗口周/半月/月；库存表仅当年当季；负库存=预售欠货单列
- 数据落 `data/raw/<日期>/pm/`（3年订单 hist3y + 明细 order_details）；参数在 `config/sales-params.json`（内部账户清单/告急线/vip对应/当季定义——拍板后改配置即生效）
- **交付偏好（V1.9）**：最终产出以 **Excel 为主**（11 sheet、商品类嵌图、全量名单、筛选+冻结），md/json 仅作中间产物存档，不作为交付物
- **多客商品详情"购买客户"页签按客户等级分组且脱敏**，核对客户明细须走「财务→单据→搜单号/客户名」
- 哪些能定时、哪些要单独索取：见 `references/销售报表排程.md`（定时任务配置方法也在该文档）
- 按需专项：保本/亏本款（月度，需成本核算）、上市×天气归因、3年全量重采、合并组拆分重算、历史日期回溯报表

### 第3步：产出呈现

- `out/看板-<日期>.html` → present_files 给用户
- `out/日报-<日期>.md` 与企微版 → 摘要给用户
- `out/补货深度分析-<日期>.md` → 补货决策依据，摘要给用户
- 数据质量异常必须显式说明，禁止静默

## 允许使用的MCP工具（白名单）

list_pages / new_page / navigate_page / close_page ｜ take_snapshot ｜ click / fill / fill_form / drag / hover / press_key ｜ evaluate_script（只读；结果大时落文件）｜ wait_for ｜ list_network_requests / get_network_request（只读监听）｜ handle_dialog ｜ take_screenshot

**唯一禁区**：写操作——保存/删除/导出/提交类按钮与接口，无论 UI 点击还是 evaluate_script/CDP 执行。

## 异常处理速查

| 状况 | 处置 |
|---|---|
| 浏览器未启动 | 第0步 list_pages/new_page 唤起 |
| 收割器无调试端口（pipe模式） | 回落auth.json缓存；失效则 `references/采集兜底.md` 附A |
| 未登录 | 登录阻断流程（硬停+零数据回答，第0步或第1步判定均可触发；不发任何日报/看板/数据摘要） |
| 直连单端点失败 | 记issue继续；日报披露；自愈更新endpoints.json |
| 直连整系统失败 | `references/采集兜底.md` 附B；同时探查新接口自愈 |
| 限速/风控迹象 | 调大 rules.json「直连采集」请求间隔毫秒 |
| wait_for 超时 | reload重试1次；仍超时标记缺项，日报注明 |
| 翻页>max_pages | 停止记录，剩余页写 capture-issues.jsonl |
| 弹窗遮挡 | handle_dialog(accept) 后重试 |

## references 索引（按需加载，勿全量读）

| 文档 | 何时读 |
|---|---|
| `references/采集兜底.md` | 直连失败/收割器连不上调试端口/接口改版排查/浏览器UI采集 |
| `references/分析口径.md` | 补货深度分析、月度成本核算、款号核对回写、对账规则 |
| `references/推送与排程.md` | 配企微推送、建定时任务、调 rules.json 参数、批次tier明细 |
| `references/销售报表排程.md` | 销售报表：哪些数据可定时/哪些按需索取、定时任务配置方法、脚本速查、待拍板参数 |
| `CHANGELOG.md` | 查版本演进与历史决策 |

## 运行时目录

`state/`（auth.json、db.json、mapping.json、capture-issues.jsonl、login-events.jsonl）｜ `data/raw/<日期>/<槽>/` ｜ `out/`（日报/看板/分析）——均自动创建，勿手工清理 state。
