# suyi-scm-collector 版本演进

## V1.9.5（2026-11-05 真实链路测试 + 衣者前端改版自愈）
- **全链路真实数据测试通过**：check-login（双✓）→ 直连采集 morning+poll 批次 13 端点全成功（衣者+多客）→ ingest 入库 SKU 17526 条 → match/alert/reconcile/report 全链跑通 → 产出日报md/五部门txt/看板html。改版后路径、动态端口、凭据收割、数据外置全部正常。
- **关键修复：衣者前端改版适配**（v/cv 来源变更）。现象：check-login 判已登录但直连全报 code=201「检测到有新版本，请重新登录」。抓包浏览器真实请求体定位根因：衣者新版前端 tokenInfo 瘦身为 {token,uid,cid}，**v 移到 localStorage['version']（前端构建hash）、cv 固定 '4.18.0'**。修复：harvest-auth.mjs storageScan 在 v 为空时回填 v=ls.version、cv='4.18.0'。v 缺失是衣者 code=201 的充分条件——**check-login 的 API 实测信号用的是 get_user_info（不带v也过），与业务接口（带v校验）存在信号差**，check-login 已实测覆盖此场景（业务API轮询监听里首个带v的请求才是权威信号——本轮即靠直连失败暴露）。
- 测试期发现 ingest.mjs 对仅 poll 批次（无 morning 文件）会崩（yFinance null），属既有边界非本次改动引入——本次以补采 morning 批次绕过，**留待后续加固**（readJson null 兜底）。
- 复现路径已固化：任何「code=201 检测到有新版本」类报错先怀疑 v/cv 过期/缺失，用 cdp-eval 抓浏览器真实请求体对比。

## V1.9.4（2026-11-05 skill 改名 suyi-scm-collector）
- skill 本名/目录名统一改为 **`suyi-scm-collector`**（用户要求，与仓库 suyi-fde、比特窗口 suyi 形成统一命名）：SKILL.md name 字段、全套文档标题、`@skill:` 定时任务提示词、部署路径示例（`skills/suyi-scm-collector/`、`D:\suyi-scm-collector`）。
- **不变**：数据根目录仍为 `~/WorkBuddy/scm-collector-data/`（SCM_DATA_HOME 可覆盖，历史数据零迁移）；skill 调用还可用描述触发（跑采集/出日报等触发词不变）；脚本与窗口层无任何改动。
- 改名前备份：~/WorkBuddy/scm-collector-data/.backup-skill-prerename-20261105.tar.gz。
- ⚠️ 已配置的 WorkBuddy 定时任务如引用了旧名 `@skill:scm-collector`，下次执行前需把 prompt 里旧名替换为新名（references/排程.md 已同步新名）。

## V1.9.3（2026-11-05 登录判定机制重写 + 发布前审查修复）
- **check-login 判定机制重写（用户拍板）**：不再读 storage/IndexedDB，改三信号判定——①页面跳登录页/可见密码框（最高优先级）②**浏览器内业务API实测**（CDP Network 只读监听页面自己发的请求读响应体：衣者 code=200/201、多客 err=0/≠0）③业务页 complete 稳定8秒不跳登录页。背景：storage 版判定在多客（key 在 IndexedDB）上误报未登录；API 实测才是登录态的最直接证据，且与第1步直连的 code=201 判定同源。
- **发布前审查修复 5 bug**：
  1. check-login 衣者 hasCreds 把整个 {key:value} 串当 JSON.parse 必失败（已随 storage 机制废弃）
  2. cdp-eval.mjs 用 process.env.HOME（Windows undefined 必崩）→ os.homedir()
  3. cdp.mjs waitPageStable 稳定判定逻辑自相矛盾（stableMs 实际无效、首次 complete 前永不返回）→ 重写
  4. capture-pages.mjs 默认端口硬编码 9222（比特窗口动态端口必然失联）→ 默认经 bit.mjs 自动发现，--port 仍可覆盖
  5. 多客已登录被误判未登录（storage/IDB 机制缺陷）→ API 实测机制根治
- **验证**：两系统真实已登录 → ok:true exit=0（API code=200/err=0 实测证据）；多客标签页停登录页但会话有效时 API 仍 err=0 → 判已登录（与实际行为一致）；全脚本 node --check 通过；Windows 兼容（无 darwin 专属调用、homedir() 替代 HOME、硬编码路径零残留）。
- release 判定：**可发布**（两平台依赖仅 Node22+python3+比特客户端；bit.mjs 的 mcp.json 读取在无该文件时安全降级为报错提示）。

## V1.9.1（2026-11-05 采集窗口改名 suyi）
- 用户要求采集窗口 name 从 `scm-collector` 改为 **`suyi`**（与仓库 suyi-fde 呼应）。改动：bit.mjs WINDOW_NAME 常量、比特窗口实际名称（browser-update，id 不变 1baea5c1...）、SKILL/INSTALL/README/采集兜底 全部文档引用。skill 名与仓库/数据目录名不变。
- 定位机制不变：默认按 name 精确匹配（API 模糊查询 + 代码 `===` 过滤防误命中），`SCM_BIT_WINDOW_ID` 环境变量可强制指定 id。

## V1.9（2026-11-05 浏览器底座切换：比特浏览器替代 chrome-devtools MCP）
- **chrome-devtools MCP 彻底移除**（mcp.json 已删该 server；用户拍板"彻底去掉"+"裸CDP"）。动机：比特浏览器每个窗口打开后即标准 CDP 端点（已实测 chrome-devtools 可挂载且用户数据一致），但 MCP 只能被动等 AI 调工具；直连采集架构下脚本本身就能跑裸 CDP（零依赖），省一层 MCP、定时任务无人值守更稳。
- **新增 4 个脚本**（全部零 npm 依赖，Node 22 内置 WebSocket）：
  - `scripts/bit.mjs`：比特 Local API 客户端——定位/幂等拉起采集窗口（当时命名 scm-collector，V1.9.1 已改 suyi），返回动态 CDP 端口；API key 单一来源 ~/.workbuddy/mcp.json bitbrowser 配置（SCM_BIT_API/SCM_BIT_API_KEY/SCM_BIT_WINDOW_ID 可覆盖）
  - `scripts/cdp.mjs`：极简裸 CDP 客户端库（附加/收发/Runtime.evaluate求值/标签页列表新建/页面稳定等待）
  - `scripts/check-login.mjs`：第0步登录态硬校验一条命令化——拉窗口+开两系统页+**storage 凭据真值判定**（实测教训：衣者 SPA 未登录先短暂呈现业务页 URL 再客户端跳转登录页，只看 URL/快照会误判已登录）；自动追加 login-events.jsonl；退出码 0/1/2=全登录/有未登录/浏览器异常
  - `scripts/cdp-eval.mjs`：通用页面执行工具（兜底B/登录排查的"AI之眼"）——--list 列标签页、--system+--js 只读求值、--url 导航、--out 大结果落文件
- **harvest-auth.mjs**：端口发现前置比特分支（bit.mjs 拿端口→端口上有两系统页面即直接采用，跳过 netstat 全扫描）；比特离线回落原端口扫描（兼容旧形态）
- **采集窗口落地**：比特浏览器建采集窗口（当时命名 scm-collector，V1.9.1 改 suyi；id=1baea5c1f57a490897e7fa279fa5131a，noproxy 无代理直连，Windows/Chrome147 指纹）；与既有 001~009 海外 socks5 代理窗口严格隔离（衣者/多客走美国IP会触发风控）。实测 open 幂等（重复 open 返回同端口）；CDP /json/version 标准响应。
- **mcp.json 修正**：bitbrowser 从顶层挪进 mcpServers（原位置不生效）；chrome-devtools 删除。
- **SKILL.md 升 V1.8→内版本 1.9**（版本号头 1.8.0）：第0步改一条命令 check-login.mjs；MCP 白名单改"比特 Local API + 裸 CDP"；异常速查增比特客户端/API key/窗口缺失三行。references/采集兜底.md 附A重写（比特五步排查链，cdp-eval 收割替代 MCP 请求文件导入）、附B 操作全量翻译成 cdp-eval 版本、实测事实增补 8 条（动态端口/SPA跳转/指纹/key单一来源/多浏览器隔离等）。
- **验证**：check-login 两系统未登录判定✓（新窗口本无登录态；修判定逻辑后衣者误报"已登录"已消除）；cdp-eval 三模式（--list/--js/导航）✓；harvest-auth 比特分支命中✓；login-events.jsonl 落盘✓。
- **遗留**：两系统尚未在窗口内登录（用户下次操作）；capture-pages.mjs 自身端口扫描未逐一验证（依赖同一 discoverPorts 逻辑，待首跑兜底时验证）。
- 备份：改造前完整备份 ~/WorkBuddy/scm-collector-data/.backup-skill-pre-bitbrowser-20261105.tar.gz（358文件/1.4MB）。

## V1.6（2026-11-05 数据外置·跨平台通用版）
- **代码与数据彻底分离**：skill 目录只留代码（scripts/config/references/文档），运行时数据全部外置到数据根目录——默认 `~/WorkBuddy/scm-collector-data/`，环境变量 `SCM_DATA_HOME` 可覆盖，首次运行自动创建。日常采集/出日报**不再触碰 skill 目录**（此前 out/state/data 会随运行膨胀，导致 skill 每次被判定"更新"）
- **跨平台（Mac/Windows 通用）**：
  - 全部 22 处 `new URL(import.meta.url).pathname` 写法改为 `fileURLToPath(import.meta.url)`（Windows 下 pathname 会产生 `/C:/...` 坏路径）
  - 全部硬编码 `/Users/colin/...` 绝对路径（14 个 py 脚本 + 11 个 mjs 脚本）改为基于脚本位置动态推导，部署到任何用户任何系统零配置
  - 凭据收割端口发现为纯 TCP 探测（默认 9222），无 macOS 专属命令
- **脚本改动面**：62 个脚本（35 mjs + 26 py + 1 修复）加入 `dataHome`/`DATA_HOME` 变量并将 state/data/out 引用重定向；`config/` 引用保留在 skill 目录
- **验证**：全部脚本语法检查通过；ingest.mjs 实跑写入新数据目录、skill 目录零写入；build-production-report.py 端到端跑通（config 读代码目录、数据读写均在数据目录）
- 已知无关缺陷记录：build-sample-report-excel.py 在含 None 数值的数据集上会抛 TypeError（原版脚本同样崩溃，与本次改造无关，待后续修复）

## V2.3（2026-10-26 落地，2026-11-03 固化迁移版）
- 新增**生产监控日报链路**（10-23 生产会议需求，与经营日报/销售报表并列的第三条独立链路）：
  - 采集：fetch-endpoints --batch first --only 生产订单/裁床记录/物料库存/工厂列表（detail 层）
  - 生成：scripts/build-production-report.py --date <日期> → out/生产监控日报_<日期>.xlsx（5 sheet：总览/①数量比对/②货期预警/③工厂负荷/④辅料物料，每 sheet=汇总KPI(上)+明细(中，整行按档位着色+表头筛选)+口径说明(下)）
  - 规则（老板拍板）：数量偏差>1%且>2件、出货多出零容差、货期=预计完工日优先/裁床开工+7天兜底、物料负结存红/主料剩余≥50可复用、工厂按逾期单数分档（≥5红）
  - 口径全文：references/生产监控口径.md（改规则先改文档再改代码）
- **可迁移性设计**：脚本全相对路径（skill 根目录自解析），参数外置 config/production-params.json（可选，缺省=会议拍板值），依赖仅 python3+openpyxl；换设备登录衣者后跑同两条命令得相同结果。已用 2026-10-26 历史采集数据回归验证：59 数量异常（多5/少54）/65 货期逾期/709 辅料负结存/102 主料剩余，与首版交付一致。
- 未纳入模块（前置未满足，详见口径文档）：采购↔裁床（预裁数口径待老板）、次品（多客次品仓待生产对接人）、损耗率（待定标）、4天备货推送（缺在手量字段）。
- SKILL.md：触发词新增「生产日报/生产监控/裁床出货对不上/货期逾期」；references 索引表补生产监控口径.md。

- **V1.7 2026-10-08（未登录零数据回答）**：登录阻断再加码——未登录时**不做任何数据类回答**：不呈现任何产出文件（含当日既有日报）、不发数据摘要/表格，唯一输出=登录提醒通知。取消 V1.6 的「重发当日既有日报不受限」例外，改为全面禁止。背景：10-08 17:43 自动化在两系统未登录下仍呈现了既有日报全文，用户要求未登录时只通知登录、其余一概不做。
- **V1.6 2026-10-08（未登录硬停）**：原「登录通知流程」升级为「登录阻断流程」——检测到任一系统未登录即**全流程硬停**（不采集、不跑后处理、不生成日报、不推送），对话+企微双通道提醒用户登录；第0步新增登录态硬校验（URL跳登录页/快照见登录表单即拦截，不再等到第1步 auth 判定）；禁止用旧缓存数据冒充当日日报（重发当日既有日报不受限）；用户说"继续"后从第0步重新检测。同步更新：SKILL.md 铁律③/流程图/第0步/第1步分支/异常速查表、采集兜底.md 附A前置、fetch-endpoints.mjs 与 fetch-orders-region.mjs 的流程名注释。背景：10-08 17:31 自动化在衣者凭据被顶（code=201）后仍继续跑了预警重算与产出呈现，用户要求未登录即停。
- **V1.5 2026-10-08（瘦身分层重构）**：SKILL.md 从 24KB 瘦身至 ~7KB（Progressive Disclosure 规范）——采集兜底/分析口径/推送排程迁至 `references/`，修改记录迁出为本文件；触发词与执行行为零变化。新增：月度成本核算方法归档（含窗口重定向、动销拼接、口径坑清单）、多客key在IndexedDB的收割细节、pipe模式浏览器事实、早间批次restock-deep生产订单盲区处置。
- **V1.4 2026-10-08（企微双通道推送）**：notify.mjs 改造——通道A=`wecom-cli message aibot` 发授权人（默认，无需webhook；whoami非标准JSON，授权人ID正则提取，机器人aib前缀不可用作chat_id）；通道B=webhook群机器人（保留原逻辑）；新增预警专项推送（⛔/🔴前12款）。待办：机器人「消息」权限过期需用户在企微重新授权。
- **V1.3 2026-09-28（补货深度分析）**：新增第2.5步与两脚本——`fetch-orders-region.mjs`（30日全量订单884单含收件信息，复用凭据收割+直连，`--days N`空格形式参数解析修复）与 `restock-deep.mjs`（净缺口=建议−在产订单计划量；季节三分类：秋季上行上调30-50%/档口预占挂起核实/冬季慢热缓；地区三级解析province→address→客户名前缀，识别率80%）。已验证商业事实沉淀：华南占57%、北方无启动迹象、冬款节奏看10月中档口。产出 out/restock-deep-<date>.json + out/补货深度分析-<date>.md
- **V1.2 2026-09-28（首轮真实数据修复）**：① endpoints.json duoke_goods.jsonl 置 no_version（GET带version报9999 "bi key not exist"，同payment/view_all先例）② ingest.mjs：snapshot层端点自动回落（当前槽→当日另一槽→往前30日pm优先），meta记snapshot_from供日报披露；空品名168款用款号兜底；captured_at改本地时间（原UTC致日报落款差8h）；新增超卖/空品名披露行 ③ alert-rules.mjs：修复超卖款漏报（原 stock<=0 return 把241款负库存款全排除）；超卖款日销回退30日口径；30日零动销的呆滞超卖单独记 stale_oversold 不进预警（建议盘点核销）；级别新增⛔超卖置顶排序 ④ report-daily.mjs：来源文案改「直连API采集」；新增超卖专项板块与呆滞超卖披露；看板/企微版同步 ⑤ notify.mjs 默认日期改本地时区
- **V1.1 2026-09-24（首轮实测后）**：新增「实测环境事实」（MCP落盘根=tmpdir、antd键盘导航改页、多客20条/页上限、翻页节奏与批量收割、校验三板斧、衣者库存total口径、导出按钮列入红线禁区）；批次重构提速——早间轻批次+昨日增量、晚间集中全量快照、午间可选；ingest.mjs修复缺失文件null崩溃（readJsonl兜底`||[]`）；CDP翻页收割器 capture-pages.mjs（仅DOM/Input/Network域、禁一切页内JS执行、失败回落MCP模式）
- **V1.0 2026-09-24（初版）**：纯UI采集（禁代码注入）、早晚双快照分槽、批次分层tier（注册表对齐SOP采集清单21+9端点）、五部门分版日报、款号人工核对队列与回写、企微webhook推送、定时调度外置WorkBuddy定时任务、列表每页条数100、ingest通用兜底落库+Demo标记、state/data/out运行时自建

## V2.3.1（2026-11-04 样衣日报 Excel 固化）
- 新增 `scripts/build-sample-report-excel.py`：样衣管理日报从一次性 openpyxl 脚本固化为正式链路脚本——直接读 `data/raw/<日期>/<槽>/yizhe_template_list.jsonl` 派生全部明细（pool/warns/today_work/category/audit），不再经中间 CSV；相对路径自解析（与 build-production-report.py 同迁移范式），`SEASON_START` 脚本顶部可调。
- 产出 `out/样衣管理日报-<日期>.xlsx`（6 sheet：00总览/01管线蓄水池/02时间预警/03今日工作清单/04品类结构/05数据稽核，每 sheet=顶部总结+中部明细+底部口径）；会议需求台账不进日报（静态），保留 md 版。
- SKILL.md：样衣管理日报节升 V1.1，执行链明确 Excel 为终交付、md 版为可选中间产物；声明生成后须重打 AIGC 标。
- 回归验证：用 2026-10-26 快照重跑，明细数据区与首版交付逐行零差异（00总览文案微调、01总结区少一行属预期简化）。
- user-callback：用户明确"我需要的是给我日报"——日报=每日增量数据，静态内容一律移出工作簿。

## V1.8（2026-10-10）
- 新增销售报表链路（销售负责人14项需求）：refresh-recent增量刷单 → build-sales-report-v2 → build-sales-dashboard-v2
- 新增客户账户合并（同人归并）：build-dedup-groups（同名+同手机号并查集）+ audit-client-counts 审计表；报表全指标按合并口径
- 新增 config/sales-params.json（内部账户清单/告急线/vip对应/当季定义，拍板后改配置生效）
- 新增 references/销售报表排程.md（定时vs按需分类、定时任务配置、脚本速查）；SKILL.md 挂接触发词「跑销售日报」
- 探明多客商品详情"购买客户"页签=按vip等级分组+脱敏；核对客户明细走财务→单据搜索

## V1.9（2026-10-10 下午）
- 新增 Excel 交付链路：fetch-goods-pics.mjs（商品图批量下载：analysis/get_goods_detail 取 hash → CDN cn-cdn-oss.duoke.net/user_19228/<hash>.jpeg，缓存 state/goods-pics/）+ build-sales-excel.py（openpyxl 11 sheet，商品类 sheet 嵌图，需 Pillow）
- 图片嵌入规格：图片列固定第2列、140px 缩略图、冻结从图片列后开始、无图标注"无图"
- 用户交付偏好：**只要 Excel（xlsx），不要 md/json**——后续日报产出以 Excel 为主

## V2.0（2026-10-10 15:00）
- Excel sheet 结构按销售负责人 14 项需求维度重排为 21 个 sheet，编号+需求标签命名（01·日周月总览【需求9】…21·流失三档【需求10】）
- 补齐此前缺失维度：新老客占比(5)/月未下单(3附)/导购(4)/新客未复购(6)/老客断档(6)/ABCD(8)/补单TOP(2)/新客月度(7)/新品客户数TOP10(1)/库存三表拆分(积压/告急/欠货)
- build-sales-report-v2.mjs：jsonOut 补 reorder_top_30d + new_client_monthly；补单聚合修正为合并组口径
- 商品类 10 个 sheet 嵌图 441 张

## V2.1（2026-10-12 改动需求落实）
- 口径修正：月未下单=近3月有单+本月自然月无单；新客未复购档位15-30/30-60天+建单价件单价；补单TOP改按款式（周/半月/月）；新客月度=自然月；新老客占比+建单价
- 通用：所有单品表+上市时间+价格(price_range.range[0])+品类；所有客户明细表+手机号（合并组取任一账户，~78%覆盖，缺失显示—）
- 动销三窗×2（全量+剔除专属客户数≥2版）；单品类6类×2版本；新品上市三档(1-7/7-15/15-30天)；库存告急新定义=库存<近7日销量×2
- 删除：老客断档、预售欠货 sheet
- 37 sheet；补单款口径=老客再拿款（系统tag无字面「补单」，tag_info 15个已核实）
- 产出：out/销售数据报表-2026-10-12.xlsx（嵌图~430）+ 销售数据报告-2026-10-12.json

## V2.2（2026-10-12 11:40）
- 导购业绩拆三张：昨日（每日晨发）/上周（周一晨发）/本月截至昨日（每日发）；全部按店铺分开（shop_name维度）
- 所有客户统计表加归属店铺列（=下单次数最多的店铺）
- 新品上市三档表+新品客户数TOP10加实时库存列
- refresh-recent 窗口参数化修正（此前硬编码10-10漏了10-11/12数据）

## V2.3（2026-10-12 13:45 skill 定稿同步）
- SKILL.md 销售报表节更新为 V2.2 口径全集（销售负责人三轮确认：10-09需求会/10-10修正/10-12逐表核对+增量）
- references/销售报表排程.md 重写为定稿版（导购三张发送节奏、39 sheet 清单、脚本速查、待拍板）
- refresh-recent.mjs 窗口彻底动态化（20天前~今天，杜绝再漏日期）
- 当前定版产出：out/销售数据报表-2026-10-12.xlsx（39 sheet，V2.2）

## V2.4（2026-10-12 15:30 补单→复购 + 上市时间新口径）
- 全报表"补单"改"复购"：口径=客户再次购买同一款（明细行按客户×款时间序，第2次起算复购）；总览复购金额/单数、导购三张复购金额/单数、复购款TOP30（周/半月/月，替代补单款TOP）
- 新接口：GET goods/get?id= → info.desc=商品备注；fetch-goods-remarks.mjs 全量4248款（704款备注含日期，如"9.21"→2026-09-21），缓存state/goods-remarks.json
- 上市时间三级口径：备注日期 → 无备注用首次销售时间（3年明细推导）→ 兜底建档日
- 近30日复购实况：¥852,650 / 688单 / 9,423件

## V2.5（2026-10-12 15:50 Excel口径说明页）
- build-sales-excel.py 新增「00·口径说明」sheet 置于工作簿首位：七类32条口径（客户/交易/名单/单品/库存/导购/其他），分节底色+冻结表头，每期自动携带
- wb 标题更新为 V2.4 复购口径+备注上市时间

## V2.6（2026-10-12 17:45 修「跑销售日报」路由撞车）
- 问题：用户说"跑销售日报"被路由到经营日报链（ingest/report-daily五部门版）而非销售Excel链——SKILL.md 触发条件未区分两条链
- 修复：触发条件区+销售报表节明确「销售」关键词优先走 Excel 链；"出日报/发日报"保留给经营日报（生产/库存版）
- 附带修复：报表引擎/Excel 生成器输出文件名动态化（此前硬编码 2026-10-12，跨天会读不到文件）

## V2.7（2026-11-03 移除企微推送，skill 回归纯数据处理）
- 删除 scripts/notify.mjs（企微双通道推送脚本）；推送需求改由外部承接（WorkBuddy 自动化/人工转发），skill 只负责采集、计算与落盘产出
- report-daily.mjs 停产「企微版/企微全文版」文本（该格式仅为推送载荷），保留 markdown 日报+五部门分版+看板 HTML
- rules.json 删除「推送」参数块（日报时刻/轮询间隔/登录提醒参数）
- references/推送与排程.md 更名为 排程.md，移除企微推送双通道章节，保留批次表与 rules 速查
- SKILL.md/README 同步清理：后处理链去掉 notify、登录阻断改为仅对话提醒、部署步骤从 8 步减为 7 步（删除企微配置步骤）、定时任务提示词与验收项改为"生成/落盘"口径；README 自测链路补全 match/alert/reconcile 三步（此前照抄会因缺 alerts/reconcile 产物报错）
- 分析口径.md/销售报表排程.md 清理推送措辞（款号核对卡片、导购"晨发"节奏等）
