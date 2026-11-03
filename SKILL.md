# scm-collector Skill

> 衣者 × 多客 数据采集与经营日报智能体技能（V1.5 瘦身分层版）

## 铁律（每次执行前必读）

1. **直连采集为默认**：`scripts/fetch-endpoints.mjs` 直调 `api.yizheyun.com` / `api.duoke.net` 的**只读查询**接口（仅限 endpoints.json 注册端点，**严禁**保存/新建/删除/导入导出类接口）。凭据来自采集浏览器实时登录态（CDP收割，harvest-auth.mjs），不自动登录、不绕过认证、不存账号密码。直连整系统失败 → 读 `references/采集兜底.md` 走浏览器UI采集
2. **每次运行第0步必须实际调用 `list_pages`** 检查/唤起采集浏览器——禁止凭记忆假设登录态、禁止跳过
3. **未登录 → 硬停且不做任何数据回答**：检测到任一系统未登录（登录页/code=201/凭据失效），**立即停止后续所有步骤**（不进入第1步采集、不跑后处理链、不生成日报、不推送、**不呈现任何产出文件、不做任何数据类回答——连既有缓存日报也不能发**），仅做一件事：通知用户去登录。对话+企微双通道提醒「{系统名}未登录，请登录后说继续」，并追加 `state/login-events.jsonl`。**禁止**用旧缓存数据生成日报冒充当日数据；用户说"继续"后从第0步重新检测
4. **Demo模式仅当用户明确说"demo/模拟数据"**时使用（`scripts/mock-capture.mjs`）
5. **只读红线（含页内脚本）**：evaluate_script/CDP 可用于只读查询与翻页驱动，但保存/删除/导出/提交类写操作一律禁止（「导出」按钮未获用户明确放开前禁止点击）

## 触发条件

- **「跑销售日报」/「出销售报表」/「销售数据」→ 销售数据报表链（Excel，V2.5；见下文「销售数据报表」节）——用户提到销售数据/销售报表/业务负责人报表时一律走这条，不是经营日报**
- **「算提成」/「提成统计」/「首单卖完」→ 首单30天卖完统计链（见「首单30天卖完统计」节）**
- **「样衣日报」/「样衣进度」/「样板管理」→ 样衣管理日报链（见「样衣管理日报」节）**
- 用户说：跑采集 / 出日报 / 发日报 / **经营日报（生产/库存五部门版）** / 看库存 / 采集衣者 / 采集多客 / 检查登录状态 / 补货分析 / 核算X月成本 → 经营日报链（本节主流程）
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

### 样衣管理日报（V1.0，2026-10-26 依据10-23设计部会议落地）★设计部链路

触发词：**「样衣日报」/「样板管理」/「样衣进度」/「设计部日报」**。

**口径（业务方拍板，改动须留痕）**：
- 时间规则：新开发→面辅料齐 **1天** ｜ →已打板 **3天** ｜ →已车板 **3天** ｜ 已车板+复版攒 **20个即可提前审版**（周审兜底）｜ 审版完成→下单 **7天** ｜ 审版完成滞留 **14天必处理**
- 状态机（定稿）：审版完成=确定马上下单（应清空）；待下单=审过观望；废版须按五类原因写备注（雷同/滞销元素/价格带/搭配性/风格偏离）
- 资料必填：款名（设计元素+领型/袖型+廓形+品类）、波段（"2027春一波"式，禁用C1/C2）、季节、预计上新（AI排序核心）、实际上新、版次
- 今日清单排序：待"预计上新"补齐后按其紧迫度排序；未补齐前退化为"环节优先+新创建优先"

**执行链**（第0/1步登录校验通过后）：

```bash
node scripts/fetch-endpoints.mjs --batch evening --only yizhe_template_list.jsonl   # ① 样板全量快照（全量约6页）
node scripts/sample-pipeline-report.mjs --date <日期> [--prev-date <上期>]           # ② 日报 → out/样衣管理日报-<日期>.md
```

产出六段：管线蓄水池（13环节件数）｜时间预警（1/3/3/7/14天规则）｜今日工作清单｜新品品类结构周报（按创建日期归周）｜数据完整性稽核（款名/波段缺失名单）｜环节流转环比。样板详情字段（expected_new_date/edition_number/remark等）已注册 `get_template_detail` onetime 端点，按 template_id 逐款调用（勿进常规批次）。

### 首单30天卖完统计（提成，V1.4 2026-10-22 定稿）★独立链路

触发词：**「算提成」/「提成统计」/「首单卖完」/「上月提成」**——用户提"提成"一律走本链。

**口径（与业务逐条确认过，改动须留痕）**：
- 统计月=上月；纳入款=30天窗口结束月落在统计月的款（自然月归属）
- 上架时间=多客商品备注日期（state/goods-remarks.json，`fetch-goods-remarks.mjs` 维护）；首单时间=多客首笔销售订单日
- 开始卖时间=min(上架,首单)；**窗口结束=上架日起30个自然日（上架当天=第1天，即上架+29天，含大小月；8/16上架→9/14）**；无备注款用首销起算
- 首单数量=衣者首单(production_type=1)入库SKU按颜色/尺码；无入库明细降级计划数（标"(计划)"）；关联顺序 production_id→follow_order_id→模板号+窗口
- 卖完判定=窗口内销量（含退货负数冲减）≥该颜色/尺码首单量；**任一颜色未达标→款未达标**
- 差额总数：未达标=负数(红)=Σ未达标颜色缺口；达标=正数(绿)=Σ超出量；0=刚好
- 累计销量=开始卖至统计月底（总额+按颜色）；颜色核对提示=多客售出颜色vs衣者首单颜色，对不上标⚠（近似命名标"(近似XX?)"）
- 老款保护：首销早于上架备注>60天=老款重上架，剔除（大批量噪音）
- 颜色归一化：去尾"色"字（米白色↔米白）

**执行链**（第0/1步登录校验通过后；路径一律相对 skill 根目录解析，**勿写绝对路径**，保证可移植）：

```bash
node scripts/refresh-recent.mjs                          # ① 增量刷多客订单明细（基础库目录自动发现）
node scripts/fetch-goods-remarks.mjs                     # ② 备注增量（上架时间用，商品库自动发现）
node scripts/fetch-performance-history.mjs               # ③ 衣者采购/入库全量回捞（perf_*.jsonl，每月1次即可，输出目录自动发现/当天新建）
node scripts/commission-firstsell.mjs --month <YYYY-MM>  # ④ 计算 → out/commission-<月>.json（四类数据源均按mtime自动发现最新）
python3 scripts/build-commission-excel.py <YYYY-MM>      # ⑤ Excel → out/首单30天卖完统计-<月>.xlsx（单表15列）
```

运行约定：node ≥18、python3 带 openpyxl（无则 `pip install openpyxl`）；③失败（登录过期 code=201 等）时若已有历史 perf 数据可跳过并在产出中披露"首单量基于<日期>回捞数据"。产出现状样例（数字为示例）：数十款按"全部卖完/部分/未卖完/无法判定"分布（外购款标"无首单记录"）。

**每月定时任务**（Automation）：每月1日 09:00，prompt 用以下通用文本（不含任何机器特定路径）：

> 执行 scm-collector skill 的首单30天卖完统计链路，统计上一个自然月（如运行于11月则 --month 2026-10）：先做第0步登录校验（未登录→登录阻断流程，提醒用户登录后说"继续"），然后按 SKILL.md「首单30天卖完统计」节的执行链依次跑5个脚本，产出 Excel 后 present_files 呈现并摘要：总款数、全部卖完/部分/未卖完/无法判定分布、有颜色核对提示需人工复核的款数。脚本失败如实报告，不得用旧缓存冒充。

rrule=`FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=0`

### 销售数据报表（V2.5，2026-10-12 定稿；业务负责人三轮沟通口径全量）★与经营日报是两条不同链路

触发词：**「跑销售日报」** / 「出销售报表」 / 「销售数据」——**优先级高于经营日报**：只要用户话里带"销售"，走本链，不走 ingest/report-daily 五部门链。产出=out/销售数据报表-<当天>.xlsx（40 sheet）。执行链（第0/1步登录校验通过后）：

```bash
node scripts/refresh-recent.mjs          # ① 增量刷订单+新单明细至当天（窗口勿硬编码）
node scripts/build-dedup-groups.mjs      # ② 客户账户合并组（周一跑；平时跳过）
node scripts/build-sales-report-v2.mjs   # ③ 报表引擎 → out/销售数据报告-<日期>.json（中间产物）
node scripts/fetch-goods-remarks.mjs     # ④a 商品备注增量拉取（state/goods-remarks.json 缓存，上市时间用）
node scripts/fetch-goods-pics.mjs        # ④b 商品图增量下载（state/goods-pics 缓存）
python3 scripts/build-sales-excel.py     # ⑤ 最终交付：Excel 39 sheet 嵌图版 → out/销售数据报表-<日期>.xlsx
```

**口径要点（V2.2 全集，业务负责人已逐表确认）**：
- 客户按**同人账户合并**（同名+同手机号并查集，审计表可拆分）；新客=3年历史首次建档下单
- 客单价/建单价=购买金额÷购买单数（退单不计）；连带=件数÷购买单数；**复购=客户再次购买同一款**（V2.4 业务负责人口径，替代补单）
- **月未下单**=近3个月有下单、但本月（自然月）还没下单
- **新客未复购**档位=15-30天 / 30-60天（60天以上不管）
- **复购款TOP30**按款式统计（客户×款第2次购买起算），周/半月/月三窗
- **导购业绩三张**：昨日（每日晨发）/上周（周一晨发）/本月截至昨日（每日发），全部**按店铺分开**
- **所有客户表**含手机号（合并组任一账户，大部分覆盖）+归属店铺（下单次数最多的店）
- **所有单品表**含上市时间+价格（price_range.range[0]）+品类+实时库存；**上市时间三级口径（V2.4）：商品备注日期（goods/get desc，fetch-goods-remarks.mjs 拉取缓存）→ 无备注用首次销售时间 → 兜底建档日**
- 动销周/半月/月×2（全量+剔除专属≥2客户）；单品类TOP10×2版本；新品上市三档（1-7/7-15/15-30天）
- **库存告急**=总库存<近7日销量×2（卖不过两周即告急）；库存表仅当年当季（sales-params.json）
- 已删除：老客断档（与流失三档重叠）、预售欠货（业务不需要）
- 流失三档=30-60天/60天-1年/1-2年（超2年剔除）

- 数据落 `data/raw/<日期>/pm/`；参数在 `config/sales-params.json`（内部账户清单/告急线/vip对应/当季定义——拍板后改配置即生效）
- **交付偏好**：最终产出只发 **Excel**（40 sheet：00·口径说明页置首 + 39 数据 sheet、商品类嵌图、全量名单、筛选+冻结），md/json 仅中间产物
- 待业务负责人拍板：专属剔除门槛≥2还是≥5；内部账户剔除清单
- 哪些能定时、哪些要单独索取：见 `references/销售报表排程.md`
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
| `out/首单30天卖完统计-<月>.xlsx` | 提成统计交付物（单表15列：时间4列+首单数量/窗口销量/累计总额/累计按色/差额总数/退货冲减/卖完情况/颜色核对提示/备注） |
| `references/推送与排程.md` | 配企微推送、建定时任务、调 rules.json 参数、批次tier明细 |
| `references/销售报表排程.md` | 销售报表：哪些数据可定时/哪些按需索取、定时任务配置方法、脚本速查、待拍板参数 |
| `CHANGELOG.md` | 查版本演进与历史决策 |

## 运行时目录

`state/`（auth.json、db.json、mapping.json、capture-issues.jsonl、login-events.jsonl）｜ `data/raw/<日期>/<槽>/` ｜ `out/`（日报/看板/分析）——均自动创建，勿手工清理 state。
