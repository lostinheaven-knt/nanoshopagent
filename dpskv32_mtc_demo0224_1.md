# 迭代设计：批量工具 + update_collection + system_prompt

> 对 `dpskv32_mtc_demo0211.py` 的三项迭代需求

---

## 1. 需求概述

| # | 需求 | 影响范围 |
|:---:|:---|:---|
| ① | 5 个工具改为支持**一次调用生成多个**（批量） | `org_tools_registry` 中 5 个工具的 schema + `tools_summary` 自动同步 |
| ② | 新增工具 `update_collection` | `org_tools_registry` 新增条目 |
| ③ | 增加 `system_prompt`，设定电商经营达人角色 | `__main__` 中 `messages` 初始化 |

---

## 2. 需求①：5 个工具改为支持批量操作

### 2.1 改造策略

核心思路：将原本接收**单个对象参数**的工具，改为接收 **`items` 数组**，一次调用可传入多个对象。同时保留 `store_id` 作为顶层公共参数。

**改造前**（以 `create_physical_product` 为例）：
```json
{
  "store_id": "store_001",
  "title": "帆布包A",
  "price": 89
}
```
LLM 要创建 5 个商品 → 需要调用 5 次。

**改造后**：
```json
{
  "store_id": "store_001",
  "items": [
    {"title": "帆布包A", "price": 89},
    {"title": "帆布包B", "price": 99},
    {"title": "帆布包C", "price": 79}
  ]
}
```
LLM 一次调用即可创建多个，**减少工具调用轮次**。

### 2.2 五个工具的具体 schema 变更

#### ⑴ generate_blog

```diff
 "generate_blog": {
     "function": {
         "name": "generate_blog",
-        "description": "AI生成店铺博客文章，用于SEO优化和内容营销",
+        "description": "AI生成店铺博客文章，用于SEO优化和内容营销。支持一次生成多篇，通过 items 数组传入多组参数",
         "parameters": {
             "properties": {
                 "store_id": {"type": "string", "description": "店铺ID"},
-                "topic": {"type": "string"},
-                "keywords": {...},
-                "tone": {...},
-                "word_count": {...}
+                "items": {
+                    "type": "array",
+                    "description": "博客列表，每项包含一篇博客的参数",
+                    "items": {
+                        "type": "object",
+                        "properties": {
+                            "topic": {"type": "string", "description": "博客主题"},
+                            "keywords": {"type": "array", "items": {"type": "string"}, "description": "SEO关键词"},
+                            "tone": {"type": "string", "description": "文章风格：professional/casual/trendy"},
+                            "word_count": {"type": "integer", "description": "目标字数"}
+                        },
+                        "required": ["topic"]
+                    }
+                }
             },
-            "required": ["store_id", "topic"]
+            "required": ["store_id", "items"]
         }
     }
 }
```

#### ⑵ create_physical_product

```diff
 "create_physical_product": {
     "function": {
-        "description": "创建实物商品，包含标题、描述、价格、库存、规格变体、图片等",
+        "description": "创建实物商品，支持一次创建多个。通过 items 数组传入多组商品参数",
         "parameters": {
             "properties": {
                 "store_id": {"type": "string", "description": "店铺ID"},
-                "title": {...},
-                "description": {...},
-                "price": {...},
-                ...
+                "items": {
+                    "type": "array",
+                    "description": "商品列表，每项包含一个商品的完整参数",
+                    "items": {
+                        "type": "object",
+                        "properties": {
+                            "title": {"type": "string", "description": "商品标题"},
+                            "description": {"type": "string", "description": "商品描述"},
+                            "price": {"type": "number", "description": "价格"},
+                            "compare_at_price": {"type": "number", "description": "原价（划线价）"},
+                            "sku": {"type": "string", "description": "SKU编码"},
+                            "inventory_quantity": {"type": "integer", "description": "库存数量"},
+                            "variants": {"type": "array", "items": {"type": "object"}, "description": "规格变体"},
+                            "images": {"type": "array", "items": {"type": "string"}, "description": "图片URL列表"},
+                            "category": {"type": "string", "description": "商品品类"},
+                            "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
+                            "weight": {"type": "number", "description": "重量(g)"}
+                        },
+                        "required": ["title", "price"]
+                    }
+                }
             },
-            "required": ["store_id", "title", "price"]
+            "required": ["store_id", "items"]
         }
     }
 }
```

#### ⑶ create_visual_product

同理改为 `items` 数组，每项包含 `title`/`description`/`price`/`digital_file_url`/`license_type`/`access_duration_days`，`required: ["title", "price"]`。

#### ⑷ create_dropshipping_product

同理改为 `items` 数组，每项包含 `supplier_product_id`/`supplier`/`markup_percentage`/`custom_title`/`custom_description`，`required: ["supplier_product_id", "supplier"]`。

#### ⑸ create_collection

同理改为 `items` 数组，每项包含 `title`/`description`/`type`/`rules`/`product_ids`/`image_url`，`required: ["title"]`。

### 2.3 description 措辞统一规范

所有改造过的工具 description 统一追加后缀：**"支持一次创建/生成多个，通过 items 数组传入多组参数"**，确保 LLM 在筛选和调用时都能感知到批量能力。

---

## 3. 需求②：新增 update_collection 工具

```python
"update_collection": {
    "type": "function",
    "function": {
        "name": "update_collection",
        "description": "更新商品集合，支持添加或移除集合中的商品、修改集合信息",
        "parameters": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "店铺ID"},
                "collection_id": {"type": "string", "description": "集合ID"},
                "action": {"type": "string", "description": "操作类型：add_products/remove_products/update_info"},
                "product_ids": {"type": "array", "items": {"type": "string"}, "description": "要添加或移除的商品ID列表（当 action 为 add_products/remove_products 时）"},
                "title": {"type": "string", "description": "新的集合名称（当 action=update_info）"},
                "description": {"type": "string", "description": "新的集合描述（当 action=update_info）"},
                "image_url": {"type": "string", "description": "新的集合封面图（当 action=update_info）"}
            },
            "required": ["store_id", "collection_id", "action"]
        }
    }
}
```

**插入位置**：`create_collection` 之后，营销类工具之前。

---

## 4. 需求③：增加 system_prompt

### 4.1 system_prompt 内容

```python
SYSTEM_PROMPT = """你是一位经验丰富的电商经营达人和店铺运营专家。你精通：
- 选品策略：能根据市场趋势和目标受众推荐合适的产品组合
- 店铺运营：熟悉店铺搭建、装修、域名配置、支付物流等全流程
- 营销推广：擅长制定折扣活动、社交媒体营销、EDM邮件营销等策略
- 数据分析：能解读运营数据报告，给出优化建议
- 客户管理：懂得客户分群、VIP体系、积分运营等用户增长手段

请以专业、友好的语气与用户交流。在执行操作时：
1. 主动思考操作的合理性，必要时给出建议
2. 如果用户的要求模糊，可以先给出合理的默认方案再确认
3. 操作完成后给出简洁的结果总结和后续建议"""
```

### 4.2 代码改动

在 `__main__` 的 `messages` 初始化和 `/reset` 命令处，注入 system message：

```diff
-    messages = []
+    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
```

```diff
     if user_input.lower() == "/reset":
-        messages = []
+        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
         turn = 0
```

---

## 5. 变更文件清单

仅修改 **`dpskv32_mtc_demo0211.py`** 一个文件：

| 区域 | 行号范围 | 改动内容 |
|:---|:---|:---|
| `org_tools_registry` | 114-131 | `generate_blog` schema → 批量 |
| `org_tools_registry` | 264-288 | `create_physical_product` schema → 批量 |
| `org_tools_registry` | 289-308 | `create_visual_product` schema → 批量 |
| `org_tools_registry` | 309-327 | `create_dropshipping_product` schema → 批量 |
| `org_tools_registry` | 328-347 | `create_collection` schema → 批量 |
| `org_tools_registry` | 347 后 | 新增 `update_collection` 工具定义 |
| 模块顶层 | 新增 | `SYSTEM_PROMPT` 常量 |
| `__main__` | 862 | `messages` 初始化带 system_prompt |
| `__main__` | /reset 分支 | `messages` 重置带 system_prompt |

`tools_summary` 由 `org_tools_registry` 自动生成，**无需手动改动**。

---

## 6. 验证方案

### 6.1 语法检查
```bash
python3 -c "import py_compile; py_compile.compile('dpskv32_mtc_demo0211.py', doraise=True)"
```

### 6.2 结构检查（AST 验证）
```bash
python3 << 'EOF'
import ast, re
with open('dpskv32_mtc_demo0211.py') as f:
    content = f.read()
tree = ast.parse(content)
# 验证工具数 = 26（原 25 + update_collection）
tool_keys = re.findall(r'"(\w+)":\s*\{\s*"type":\s*"function"', content)
print(f"工具数: {len(tool_keys)}")
# 验证 SYSTEM_PROMPT 存在
assert "SYSTEM_PROMPT" in content, "缺少 SYSTEM_PROMPT"
# 验证 5 个工具含 items 字段
for tool_name in ["generate_blog", "create_physical_product", "create_visual_product", "create_dropshipping_product", "create_collection"]:
    assert f'"items"' in content, f"{tool_name} 缺少 items"
print("ALL PASS")
EOF
```

### 6.3 用户手动验证（运行 Demo）
1. 运行 `python3 dpskv32_mtc_demo0211.py`
2. 验证欢迎信息显示工具数为 **26 个**
3. 输入 `/tools`，确认列表中包含 `update_collection` 且 5 个改造工具的 description 含 "支持一次" 字样
4. 输入"帮我在 store_001 上架 3 款春季女装"，验证 LLM 通过 `items` 数组一次调用 `create_physical_product` 创建 3 个商品（而非调用 3 次）
5. 输入 `/reset` 后确认对话重置但 system_prompt 保留
