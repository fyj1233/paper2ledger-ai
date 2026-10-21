# 同类开源项目调研（2026-09-02）

目的：学习同类项目的优点，吸收进本系统。结论已映射到 PROGRESS.md 的任务清单。

## 一、参考的项目/产品

| 项目 | 类型 | 值得学的点 |
|------|------|-----------|
| 华夏ERP（jshERP） | 国内开源进销存，SpringBoot，小微企业向 | 模块划分清晰（采购/销售/库存），数据导入导出完善 |
| ERPNext / Dolibarr / Akaunting | 国际开源 ERP | Akaunting 的财务看板极简（收入/支出/利润卡片+现金流），适合小微企业审美 |
| invoice2data | 发票结构化提取（2k+ star） | 模板化提取：对固定格式的文档用「模板+正则」提取，不依赖大模型，快且稳 |
| ICEPOS / money-pos | 开源收银系统 | 日销售统计看板、报表中心、数据统计模块 |
| 银豹 BI / OctShop | 商业收银产品 | 图表下钻与联动、总部实时看板、热销商品排行、支付方式占比 |
| NARD / Tagrain / FlexPOS | 国外 POS 报表 | 日/周/月/年四级报表、高峰时段分析、客单价与交易笔数指标 |

## 二、小微企业看板通用指标（多产品共识）

1. 今日营收、交易笔数、客单价、同比/环比
2. 销售趋势（折线）+ 分类占比（饼图）+ 热销排行（条形）
3. 支付方式占比（现金/微信/支付宝）
4. 目标完成进度条
5. 高峰时段分析（需要时间级数据，二期）

## 三、已吸收进计划的改进

| 调研收获 | 落到哪 | 对应任务 |
|---------|--------|---------|
| 环比/同比对比是看板标配 | 看板卡片加涨跌箭头和百分比 | A1 |
| 图表下钻/联动（点分类看明细） | 饼图点击联动日折线图 | A1 |
| 交易笔数、客单价 | 提取 schema 增加可选字段「笔数」，看板加客单价卡片 | B4 |
| 支付方式占比 | 提取 schema 增加可选字段「支付方式拆分」，看板加饼图 | B4 |
| 报表导出/数据导入导出 | 按日期区间导出 Excel | B3 |
| 模板化提取兜底（invoice2data 思路） | 对固定格式文档用自定义正则模板提取，省 LLM 费用 | C5（低优先） |
| 目标进度条 | 月度目标设置 + 看板进度 | B2 |
| 手工修正数据（ERP 惯例） | 页面补录/修改数据并留痕 | B1 |

## 四、明确不抄的

- 采购/库存/会员等完整 ERP 模块：当前定位是「经营分析」，模块铺太大反而粗糙
- JimuReport 等重型报表引擎：自建轻量报表页已够用
- 多门店/多租户：单店场景暂不需要

## 参考来源

- [10 个最受开发者喜爱的开源 ERP / CRM 项目](https://juejin.cn/post/7012247134175133726)（NocoBase 榜单转载）
- [invoice-x/invoice2data](https://github.com/invoice-x/invoice2data)
- [xmosnewone/ICEPOS-Cashier-System_Manage](https://github.com/xmosnewone/ICEPOS-Cashier-System_Manage)
- [ycf1998/money-pos](https://github.com/ycf1998/money-pos)
- [银豹数据 BI](https://www.pospal.cn/main/pages/solution/bi.html)
- [NARD POS Reports](https://nardpos.com/NARDsoftwares/reports-and-statistics/)
- [Tagrain 零售看板](https://tagrain.com/retail-dashboard-reports/)
- [FlexPOS: What Is POS Reporting](https://flexpos.net/what-is-pos-reporting/)
