# 场景测试用例（企业微信 + API）

面向日常使用场景的手工测试清单，覆盖：直接查价、歧义确认、对比查询（便宜/更贵）、Top/区间筛选、错误与边界。示例均为中文自然语言，适配企业微信聊天与 REST API。

- 默认定价：未指定时按 C级 + 标准色
- 类目关键词：泳镜/潜水镜/呼吸管/蛙鞋/帽子（帽子配件）
- 常用示例型号：GT10S、GT10P、2321P（泳镜）

## 1) 直接查价（按型号）

- 用例1：`GT10S 多少钱`（未指定层级/颜色 → 返回全价目表）
  - 期望：status=success；result_text 含“产品：GT10S …”与“价格一览: - C级标准色: …”
  - API：`POST /api/query {"query":"GT10S 多少钱"}`

- 用例2：`GT10S C级 标准色 价格`
  - 期望：status=success；包含“价格：$.. (C级标准色)”

- 用例3：`GT10S A级 定制色 价格`
  - 期望：status=success；包含“价格：$.. (A级定制色)”

- 用例4：`2321P C级 标准色 多少钱`
  - 期望：status=success；包含“产品：2321P … 价格：$.. (C级标准色)”

- 用例5（材质推断）：`GT10 硅胶 C级 标准色 价格`
  - 期望：命中 SILICONE 变体（GT10S），status=success；价格为 C级标准色

- 用例6（材质推断）：`2321 PVC 价格`
  - 期望：命中 PVC 变体（2321P），status=success

## 2) 歧义与确认（needs_confirmation）

- 用例7：`GT10 多少钱`
  - 期望：status=needs_confirmation；options 至少包含 GT10S / GT10P；企业微信文本返回“需要确认，请选择以下产品：1. GT10S … 2. GT10P …”

- 用例8：`2321 价格`
  - 期望：status=needs_confirmation；若存在多个变体给出选项；携带 confirmation_id

- 用例9（带材质消歧）：`GT10 PVC C级 标准色` → 直接命中 GT10P（不需确认）

- 用例10（确认后查询）：
  - 步骤1：调用 `/api/query` 拿到 confirmation_id + options
  - 步骤2：`POST /api/confirm {"confirmation_id":"...","selected_option":1}`
  - 期望：status=success；返回对应型号价格

## 3) 对比查询（更便宜/更贵）

- 用例11（按型号）：`比 GT10S 便宜的`
  - 期望：status=success；列表包含更便宜的产品，每行含“(节省 $..)”

- 用例12（按型号 + 类目）：`比 2321P 贵的 泳镜 前 10`
  - 期望：仅泳镜，按“贵 $..”降序，最多10条

- 用例13（按描述 + 材质）：`比 儿童分体简易 Silicone 便宜的`
  - 期望：找到描述匹配的参考产品（如 GT10S），标题含“参考产品”，列表为更便宜项

- 用例14（按描述 + 材质）：`比 成人款大框 PVC 贵的`
  - 期望：找到 PVC 参考，返回更贵项；result_text 含参考清单

- 用例15（描述过于宽泛）：`比 成人款 便宜的`
  - 期望：可多参考并取最严格阈值；若全无明确参考则返回 reference_not_found 错误

## 4) Top N / 价格区间

- 用例16（最便宜 Top N）：`最便宜的 泳镜 前 5`
  - 期望：status=success；5条，按价格升序；默认 C级标准色

- 用例17（最贵 Top N）：`最贵的 蛙鞋 前 3`
  - 期望：status=success；3条，按价格降序

- 用例18（价格区间）：`价格 0.70-0.90 的 泳镜`
  - 期望：status=success；均在区间内，升序

- 用例19（不带类目）：`最便宜的 前 10`
  - 期望：全品类；若执行超过 4s，企业微信采用主动消息返回

## 5) 错误与边界

- 用例20：`比 不存在的产品 便宜的`
  - 期望：status=error；error_type=reference_not_found；message 提示更具体描述或代码

- 用例21：`XJ1234 多少钱`（未知码）
  - 期望：status=error；error_type=product_not_found；给出建议

- 用例22（空内容）：`\n\n` 或仅空格
  - 期望：企业微信回空响应（不回消息）；API 返回 validation_error 或 error 提示

- 用例23（非文本消息，企业微信）
  - 期望：回空字符串（忽略）

## 6) 企业微信聊天示例

- 示例A：`GT10S A级标准色`
  - 期望：1-2s 内被动回复加密 XML；文本含“产品：GT10S … 价格：$.. (A级标准色)”

- 示例B：`比 GT10S 便宜的`
  - 期望：2-3s 内被动回复；列表含“1. GT10P … (节省 $..)”

- 示例C：`最便宜的前20个`
  - 期望：立即空回包；5-10s 内主动 Markdown 消息到达（Top 20 列表）

- 示例D（确认流）：`GT10`
  - 期望：返回“需要确认，请选择以下产品：1. GT10S … 2. GT10P …”

## 7) 常用 API 示例

- 查价（直接）：
```bash
curl -s -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"GT10S C级 标准色 价格"}' | jq
```

- 对比（更便宜）：
```bash
curl -s -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"比 GT10S 便宜的"}' | jq
```

- Top N（最便宜 泳镜 前5）：
```bash
curl -s -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"最便宜的 泳镜 前 5"}' | jq
```

- 确认接口：
```bash
# 第一步：拿到 confirmation_id
curl -s -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"GT10"}' | tee /tmp/resp.json

# 第二步：选择第1项
CONF_ID=$(jq -r .confirmation_id /tmp/resp.json)
curl -s -X POST http://localhost:8000/api/confirm \
  -H 'Content-Type: application/json' \
  -d '{"confirmation_id":"'"$CONF_ID"'","selected_option":1}' | jq
```

## 8) 断言建议（人工验收）

- result_text 包含型号（如“产品：GT10S …”）与层级/颜色（如“C级标准色”）
- 对比结果每行包含“节省 $..”或“贵 $..”，并按预期排序
- 描述对比类结果包含“参考产品”清单
- needs_confirmation 返回 options 和 confirmation_id；企业微信返回文本化选项
- 错误场景包含明确 error_type 与 message

以上用例可直接用于企业微信手测或本地 API 验收。如需扩展到“潜水镜/呼吸管/蛙鞋/帽子配件”其它类目，只需在查询中加入类目关键词与 Top/区间条件即可。

