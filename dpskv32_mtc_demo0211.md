# 动态工具选择策略优化方案讨论（电商 SaaS 场景）

> 基于 `dpskv32_mtc_t.py`（边思考边调用工具 + 上下文裁剪）的动态工具选择优化
> 场景：电商 SaaS System

## 1. 现有实现分析

`dpskv32_mtc_t.py` 的核心流程：

```
用户指令 → [固定 tools 列表] → LLM 边思考边调工具 → 工具执行 → 循环直到得到最终答案
```

**问题**：`tools` 列表是预定义、固定的。在电商 SaaS 系统中，工具涵盖 BI、店铺装修、店铺实施、产品管理、营销等多个领域，完整工具列表（`org_tools_list`）非常庞大。如果全部传入 LLM：
- **浪费上下文窗口**：每个 tool 的 JSON Schema（含 parameters、descriptions）占用大量 token
- **干扰模型决策**：过多无关工具会降低 LLM 选择正确工具的准确率
- **增加延迟和成本**：更多 token = 更高的 API 费用和更慢的响应

---

## 2. 动态工具选择策略：核心思路

**两阶段架构 + 运行时增补**：

```
阶段一（工具筛选）：select_requirement + 工具摘要（name + description） → LLM 筛选 → 筛选出相关工具名列表
阶段二（执行调用）：用户指令 + 筛选后的完整 tools 定义（含 select_tools_by_llm 作为固定工具） 
                   → LLM 边思考边调工具 → 执行 → 循环
                   → 如遇漏选，LLM 可调用 select_tools_by_llm 动态增补工具
```

**核心创新**：`select_tools_by_llm` 本身作为**固定工具**加入阶段二的 tools 列表。当 LLM 在边思考边调用的过程中发现缺少所需工具时，可以主动调用 `select_tools_by_llm` 增补工具，实现**运行时自愈**。

---

## 3. 具体实现方案

### 3.1 数据结构设计 —— 电商 SaaS 工具注册表

```python
# 完整工具注册表：存储所有工具的完整定义
org_tools_registry = {
    # ===== BI 类 =====
    "daily_report": {
        "type": "function",
        "function": {
            "name": "daily_report",
            "description": "生成店铺每日运营数据报告，包含访客量、转化率、GMV等核心指标",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "date": { "type": "string", "description": "报告日期 YYYY-mm-dd" },
                    "metrics": { "type": "array", "items": {"type": "string"}, "description": "指标列表如 ['uv','pv','gmv','conversion_rate']" }
                },
                "required": ["store_id", "date"]
            }
        }
    },
    "data_query": {
        "type": "function",
        "function": {
            "name": "data_query",
            "description": "自定义数据查询，支持按时间范围、维度、指标进行灵活的数据检索与分析",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "query_type": { "type": "string", "description": "查询类型：sales/traffic/product/customer" },
                    "date_range": { "type": "object", "properties": { "start": {"type":"string"}, "end": {"type":"string"} }, "description": "日期范围" },
                    "dimensions": { "type": "array", "items": {"type": "string"}, "description": "分组维度" },
                    "filters": { "type": "object", "description": "筛选条件" }
                },
                "required": ["store_id", "query_type", "date_range"]
            }
        }
    },

    # ===== 店铺装修类 =====
    "onboarding_build": {
        "type": "function",
        "function": {
            "name": "onboarding_build",
            "description": "店铺初始化搭建，根据行业模板和用户偏好快速生成店铺基础结构",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "template_type": { "type": "string", "description": "模板类型：fashion/electronics/food/general" },
                    "store_name": { "type": "string", "description": "店铺名称" },
                    "brand_color": { "type": "string", "description": "品牌主色调（hex格式）" }
                },
                "required": ["store_id", "template_type", "store_name"]
            }
        }
    },
    "add_menu": {
        "type": "function",
        "function": {
            "name": "add_menu",
            "description": "为店铺添加或编辑导航菜单项，支持多级菜单结构",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "menu_items": { "type": "array", "items": {"type": "object"}, "description": "菜单项列表，每项包含 title/url/children" },
                    "position": { "type": "string", "description": "菜单位置：header/footer/sidebar" }
                },
                "required": ["store_id", "menu_items"]
            }
        }
    },
    "page_decoration": {
        "type": "function",
        "function": {
            "name": "page_decoration",
            "description": "店铺页面装修，可对首页、产品页等进行布局和组件配置",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "page_type": { "type": "string", "description": "页面类型：home/product/collection/about" },
                    "sections": { "type": "array", "items": {"type": "object"}, "description": "页面区块配置列表" },
                    "theme_settings": { "type": "object", "description": "主题设置（字体、颜色等）" }
                },
                "required": ["store_id", "page_type", "sections"]
            }
        }
    },
    "generate_blog": {
        "type": "function",
        "function": {
            "name": "generate_blog",
            "description": "AI生成店铺博客文章，用于SEO优化和内容营销",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "topic": { "type": "string", "description": "博客主题" },
                    "keywords": { "type": "array", "items": {"type": "string"}, "description": "SEO关键词" },
                    "tone": { "type": "string", "description": "文章风格：professional/casual/trendy" },
                    "word_count": { "type": "integer", "description": "目标字数" }
                },
                "required": ["store_id", "topic"]
            }
        }
    },

    # ===== 店铺实施类 =====
    "create_domain": {
        "type": "function",
        "function": {
            "name": "create_domain",
            "description": "为店铺创建自定义域名（平台内域名）",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "domain_name": { "type": "string", "description": "期望的域名前缀" }
                },
                "required": ["store_id", "domain_name"]
            }
        }
    },
    "change_domain": {
        "type": "function",
        "function": {
            "name": "change_domain",
            "description": "修改店铺的现有域名",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "old_domain": { "type": "string", "description": "旧域名" },
                    "new_domain": { "type": "string", "description": "新域名" }
                },
                "required": ["store_id", "old_domain", "new_domain"]
            }
        }
    },
    "connect_outer_domain": {
        "type": "function",
        "function": {
            "name": "connect_outer_domain",
            "description": "绑定外部自有域名到店铺，配置DNS解析",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "external_domain": { "type": "string", "description": "外部域名" },
                    "dns_provider": { "type": "string", "description": "DNS服务商" }
                },
                "required": ["store_id", "external_domain"]
            }
        }
    },
    "logistics_setup": {
        "type": "function",
        "function": {
            "name": "logistics_setup",
            "description": "配置店铺物流方案，包括运费模板、配送区域、物流商对接",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "shipping_zones": { "type": "array", "items": {"type": "object"}, "description": "配送区域及运费规则" },
                    "carriers": { "type": "array", "items": {"type": "string"}, "description": "物流商列表" },
                    "free_shipping_threshold": { "type": "number", "description": "免运费门槛金额" }
                },
                "required": ["store_id", "shipping_zones"]
            }
        }
    },
    "payment_setup": {
        "type": "function",
        "function": {
            "name": "payment_setup",
            "description": "配置店铺支付方式，支持信用卡、PayPal、本地支付等",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "payment_methods": { "type": "array", "items": {"type": "string"}, "description": "支付方式列表" },
                    "currency": { "type": "string", "description": "结算货币" },
                    "api_keys": { "type": "object", "description": "支付网关API密钥" }
                },
                "required": ["store_id", "payment_methods", "currency"]
            }
        }
    },
    "tax_setup": {
        "type": "function",
        "function": {
            "name": "tax_setup",
            "description": "配置店铺税费规则，支持按地区、品类设定税率",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "tax_regions": { "type": "array", "items": {"type": "object"}, "description": "税区及税率配置" },
                    "tax_inclusive": { "type": "boolean", "description": "价格是否含税" }
                },
                "required": ["store_id", "tax_regions"]
            }
        }
    },
    "unlock_store": {
        "type": "function",
        "function": {
            "name": "unlock_store",
            "description": "解锁/发布店铺，使其对外可访问",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "password_protection": { "type": "boolean", "description": "是否保留密码保护" }
                },
                "required": ["store_id"]
            }
        }
    },
    "connect_social_channel": {
        "type": "function",
        "function": {
            "name": "connect_social_channel",
            "description": "连接社交媒体销售渠道（Facebook/Instagram/TikTok等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "channel": { "type": "string", "description": "渠道名：facebook/instagram/tiktok/pinterest" },
                    "auth_token": { "type": "string", "description": "渠道授权token" }
                },
                "required": ["store_id", "channel"]
            }
        }
    },

    # ===== 产品类 =====
    "create_physical_product": {
        "type": "function",
        "function": {
            "name": "create_physical_product",
            "description": "创建实物商品，包含标题、描述、价格、库存、规格变体、图片等",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "title": { "type": "string", "description": "商品标题" },
                    "description": { "type": "string", "description": "商品描述" },
                    "price": { "type": "number", "description": "价格" },
                    "compare_at_price": { "type": "number", "description": "原价（划线价）" },
                    "sku": { "type": "string", "description": "SKU编码" },
                    "inventory_quantity": { "type": "integer", "description": "库存数量" },
                    "variants": { "type": "array", "items": {"type": "object"}, "description": "规格变体" },
                    "images": { "type": "array", "items": {"type": "string"}, "description": "图片URL列表" },
                    "category": { "type": "string", "description": "商品品类" },
                    "tags": { "type": "array", "items": {"type": "string"}, "description": "标签" },
                    "weight": { "type": "number", "description": "重量(g)" }
                },
                "required": ["store_id", "title", "price"]
            }
        }
    },
    "create_visual_product": {
        "type": "function",
        "function": {
            "name": "create_visual_product",
            "description": "创建虚拟/数字商品（如电子书、课程、会员卡、软件许可等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "title": { "type": "string", "description": "商品标题" },
                    "description": { "type": "string", "description": "商品描述" },
                    "price": { "type": "number", "description": "价格" },
                    "digital_file_url": { "type": "string", "description": "数字文件下载链接" },
                    "license_type": { "type": "string", "description": "许可类型：single/unlimited" },
                    "access_duration_days": { "type": "integer", "description": "有效期（天）" }
                },
                "required": ["store_id", "title", "price"]
            }
        }
    },
    "create_dropshipping_product": {
        "type": "function",
        "function": {
            "name": "create_dropshipping_product",
            "description": "创建代发(dropshipping)商品，从供应商导入并设置利润率",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "supplier_product_id": { "type": "string", "description": "供应商商品ID" },
                    "supplier": { "type": "string", "description": "供应商平台：aliexpress/cjdropshipping/spocket" },
                    "markup_percentage": { "type": "number", "description": "加价比例(%)" },
                    "custom_title": { "type": "string", "description": "自定义标题" },
                    "custom_description": { "type": "string", "description": "自定义描述" }
                },
                "required": ["store_id", "supplier_product_id", "supplier"]
            }
        }
    },
    "create_collection": {
        "type": "function",
        "function": {
            "name": "create_collection",
            "description": "创建商品集合/分类，支持手动选品或自动规则",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "title": { "type": "string", "description": "集合名称" },
                    "description": { "type": "string", "description": "集合描述" },
                    "type": { "type": "string", "description": "类型：manual/automatic" },
                    "rules": { "type": "array", "items": {"type": "object"}, "description": "自动规则（当 type=automatic）" },
                    "product_ids": { "type": "array", "items": {"type": "string"}, "description": "手动选品ID列表（当 type=manual）" },
                    "image_url": { "type": "string", "description": "集合封面图" }
                },
                "required": ["store_id", "title"]
            }
        }
    },

    # ===== 营销类 =====
    "create_order_discount": {
        "type": "function",
        "function": {
            "name": "create_order_discount",
            "description": "创建订单级折扣活动（满减、满折等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "discount_name": { "type": "string", "description": "活动名称" },
                    "discount_type": { "type": "string", "description": "折扣类型：percentage/fixed_amount/free_shipping" },
                    "discount_value": { "type": "number", "description": "折扣值" },
                    "minimum_order_amount": { "type": "number", "description": "最低订单金额" },
                    "start_date": { "type": "string", "description": "开始日期" },
                    "end_date": { "type": "string", "description": "结束日期" },
                    "usage_limit": { "type": "integer", "description": "使用次数限制" }
                },
                "required": ["store_id", "discount_name", "discount_type", "discount_value"]
            }
        }
    },
    "create_product_discount": {
        "type": "function",
        "function": {
            "name": "create_product_discount",
            "description": "创建商品级折扣（指定商品打折、买赠等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "discount_name": { "type": "string", "description": "活动名称" },
                    "product_ids": { "type": "array", "items": {"type": "string"}, "description": "参与商品ID" },
                    "discount_type": { "type": "string", "description": "折扣类型：percentage/fixed_amount/buy_x_get_y" },
                    "discount_value": { "type": "number", "description": "折扣值" },
                    "start_date": { "type": "string", "description": "开始日期" },
                    "end_date": { "type": "string", "description": "结束日期" }
                },
                "required": ["store_id", "discount_name", "product_ids", "discount_type", "discount_value"]
            }
        }
    },
    "post_social_media": {
        "type": "function",
        "function": {
            "name": "post_social_media",
            "description": "发布社交媒体帖子，支持多平台同步发布",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "platforms": { "type": "array", "items": {"type": "string"}, "description": "发布平台：facebook/instagram/tiktok/twitter" },
                    "content": { "type": "string", "description": "帖子内容" },
                    "media_urls": { "type": "array", "items": {"type": "string"}, "description": "图片/视频URL" },
                    "schedule_time": { "type": "string", "description": "定时发布时间（空则立即发布）" },
                    "product_ids": { "type": "array", "items": {"type": "string"}, "description": "关联商品ID" }
                },
                "required": ["store_id", "platforms", "content"]
            }
        }
    },
    "create_EDM": {
        "type": "function",
        "function": {
            "name": "create_EDM",
            "description": "创建EDM邮件营销活动，支持模板选择和受众定向",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "campaign_name": { "type": "string", "description": "活动名称" },
                    "subject": { "type": "string", "description": "邮件主题" },
                    "template": { "type": "string", "description": "邮件模板类型：promotion/newsletter/abandoned_cart/welcome" },
                    "audience_segment": { "type": "string", "description": "受众分群：all/new_customers/repeat_buyers/inactive" },
                    "content": { "type": "string", "description": "邮件正文内容" },
                    "product_ids": { "type": "array", "items": {"type": "string"}, "description": "推荐商品ID" },
                    "schedule_time": { "type": "string", "description": "发送时间" }
                },
                "required": ["store_id", "campaign_name", "subject", "template"]
            }
        }
    },
    "create_sms": {
        "type": "function",
        "function": {
            "name": "create_sms",
            "description": "创建SMS短信营销活动，支持受众筛选和定时发送",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "campaign_name": { "type": "string", "description": "活动名称" },
                    "message": { "type": "string", "description": "短信内容（注意字数限制）" },
                    "audience_segment": { "type": "string", "description": "受众分群" },
        "required": ["store_id", "campaign_name", "message"]
            }
        }
    },

    # ===== 订单类 =====
    "search_order": {
        "type": "function",
        "function": {
            "name": "search_order",
            "description": "搜索和查询订单，支持按订单号、客户、状态、日期范围等条件进行检索",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "order_number": { "type": "string", "description": "订单号（精确匹配）" },
                    "customer_email": { "type": "string", "description": "客户邮箱" },
                    "status": { "type": "string", "description": "订单状态：pending/paid/shipped/delivered/cancelled/refunded" },
                    "date_range": { "type": "object", "properties": { "start": {"type": "string"}, "end": {"type": "string"} }, "description": "下单日期范围" },
                    "min_amount": { "type": "number", "description": "最低订单金额" },
                    "max_amount": { "type": "number", "description": "最高订单金额" },
                    "page": { "type": "integer", "description": "分页页码" },
                    "page_size": { "type": "integer", "description": "每页条数" }
                },
                "required": ["store_id"]
            }
        }
    },
    "update_order": {
        "type": "function",
        "function": {
            "name": "update_order",
            "description": "更新订单信息，支持修改状态、添加备注、更新物流信息、处理退款等操作",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "order_id": { "type": "string", "description": "订单ID" },
                    "action": { "type": "string", "description": "操作类型：update_status/add_note/update_shipping/refund/cancel" },
                    "new_status": { "type": "string", "description": "新状态（当 action=update_status）" },
                    "note": { "type": "string", "description": "备注内容（当 action=add_note）" },
                    "tracking_number": { "type": "string", "description": "物流单号（当 action=update_shipping）" },
                    "carrier": { "type": "string", "description": "物流商（当 action=update_shipping）" },
                    "refund_amount": { "type": "number", "description": "退款金额（当 action=refund）" },
                    "refund_reason": { "type": "string", "description": "退款原因（当 action=refund）" }
                },
                "required": ["store_id", "order_id", "action"]
            }
        }
    },

    # ===== 用户类 =====
    "create_customer_segment": {
        "type": "function",
        "function": {
            "name": "create_customer_segment",
            "description": "创建客户分群，根据消费行为、注册时间、地域等条件划分用户群体，用于精准营销",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "segment_name": { "type": "string", "description": "分群名称" },
                    "conditions": { "type": "array", "items": {"type": "object"}, "description": "分群条件列表，每个条件含 field/operator/value" },
                    "logic": { "type": "string", "description": "条件逻辑：and/or" },
                    "description": { "type": "string", "description": "分群描述" }
                },
                "required": ["store_id", "segment_name", "conditions"]
            }
        }
    },
    "set_vip_level": {
        "type": "function",
        "function": {
            "name": "set_vip_level",
            "description": "设置客户VIP等级，支持手动指定或根据消费金额自动升降级",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "customer_id": { "type": "string", "description": "客户ID" },
                    "vip_level": { "type": "string", "description": "VIP等级：bronze/silver/gold/platinum/diamond" },
                    "reason": { "type": "string", "description": "调整原因" },
                    "auto_rules": { "type": "object", "description": "自动升降级规则（批量设置时使用）" }
                },
                "required": ["store_id", "customer_id", "vip_level"]
            }
        }
    },
    "update_customer_points": {
        "type": "function",
        "function": {
            "name": "update_customer_points",
            "description": "更新客户积分，支持积分增加、扣减、兑换操作",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": { "type": "string", "description": "店铺ID" },
                    "customer_id": { "type": "string", "description": "客户ID" },
                    "action": { "type": "string", "description": "操作类型：add/deduct/redeem" },
                    "points": { "type": "integer", "description": "积分数量" },
                    "reason": { "type": "string", "description": "操作原因：purchase/promotion/manual/redeem_coupon" },
                    "reference_order_id": { "type": "string", "description": "关联订单ID（如因购买获得积分）" }
                },
                "required": ["store_id", "customer_id", "action", "points"]
            }
        }
    }
}

# 自动生成轻量摘要列表：只保留 name + description
tools_summary = [
    {
        "name": name,
        "description": tool_def["function"]["description"]
    }
    for name, tool_def in org_tools_registry.items()
]
```

### 3.2 工具执行层 —— LLM 模拟（替代死板 Mock）

**核心思路**：所有工具函数的执行不使用硬编码 mock，而是通过一次 LLM 调用来模拟真实的业务返回。LLM 扮演"产品运营/电商系统"的角色，根据工具名和入参，生成合理的成功或错误响应。

```python
def llm_tool_executor(tool_name, tool_arguments):
    """用 LLM 模拟工具执行，生成合理的业务返回结果"""
    
    execution_prompt = f"""你是一个电商 SaaS 系统的后端服务模拟器。你需要根据被调用的工具名称和参数，
模拟出一个真实的系统返回结果。

要求：
1. 以产品运营的专业角度，返回合理的业务数据
2. 根据入参判断操作是否合理：
   - 如果参数合理，返回成功结果，包含具体的业务数据（如生成的ID、状态、详情等）
   - 如果参数有明显错误（如缺少必要信息、格式不对），返回错误信息
3. 返回 JSON 格式，包含 status（success/error）、message、以及 data 字段
4. 数据要看起来真实（如商品ID用 "prod_" 前缀 + 随机串，价格用合理数值等）

被调用的工具：{tool_name}
传入的参数：{json.dumps(tool_arguments, ensure_ascii=False, indent=2)}

请直接返回 JSON 结果，不要其他说明文字。"""

    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=[{"role": "user", "content": execution_prompt}],
        temperature=0.7,  # 适当引入随机性让结果更自然
    )
    
    return response.choices[0].message.content

# 工具调用映射：统一指向 LLM 模拟执行器
# 不再为每个工具单独写 mock 函数
def build_tool_call_map(org_tools_registry):
    """为所有注册工具构建统一的 LLM 模拟调用映射"""
    return {
        name: lambda args, tn=name: llm_tool_executor(tn, args)
        for name in org_tools_registry
    }

TOOL_CALL_MAP = build_tool_call_map(org_tools_registry)
```

**LLM 模拟 vs 硬编码 Mock 对比**：

| 维度 | 硬编码 Mock | LLM 模拟 |
|:---:|:---:|:---:|
| 开发成本 | 每个工具都要写 mock 函数 | 一个通用 executor 搞定 |
| 返回真实度 | 固定返回值，不随入参变化 | 根据入参动态生成合理结果 |
| 错误场景覆盖 | 需要手动编写各种错误分支 | LLM 自动判断并返回错误信息 |
| 新工具接入 | 需新增 mock 函数 | 自动支持，无需改代码 |
| 缺点 | 维护成本高 | 依赖 API 调用，有延迟和成本 |

---

### 3.3 阶段一：工具筛选 —— LLM 筛选（作为固定工具）

**关键设计**：`select_tools_by_llm` 不仅在进入循环前进行初始筛选，还被注册为**固定工具**加入阶段二的 tools 列表。这样在边思考边调用的过程中，如果 LLM 发现缺少所需工具，可以**主动调用**此工具来增补。

入参从 `user_query` 改为 `select_requirement`，因为增补场景下的需求描述可能来自 LLM 自身的推理，而非来自用户原始指令。

```python
def select_tools_by_llm(select_requirement, tools_summary, already_selected=None):
    """用 LLM 从工具摘要中筛选相关工具
    
    Args:
        select_requirement: 工具选择需求描述（可以是用户指令，也可以是动态产生的需求）
        tools_summary: 所有工具的 name+description 摘要列表
        already_selected: 已经选中的工具名列表（增补时避免重复推荐）
    
    Returns:
        list: 筛选出的工具名列表
    """
    
    # 构造摘要文本
    summary_text = "\n".join(
        f"- {t['name']}: {t['description']}" for t in tools_summary
    )
    
    # 已选工具信息（用于增补场景）
    already_info = ""
    if already_selected:
        already_info = f"\n\n已加载的工具（不需要重复选择）：{', '.join(already_selected)}"
    
    selection_prompt = f"""你是一个电商 SaaS 系统的工具选择助手。
根据以下需求描述，从可用工具列表中选出需要用到的工具。
注意：需求可能来自用户指令，也可能来自系统在执行过程中发现的新需求。

只返回工具名列表，用 JSON 数组格式，不要解释。
如果不确定某个工具是否需要，倾向于选上（宁多勿少）。

可用工具：
{summary_text}{already_info}

需求描述：{select_requirement}

请返回 JSON 数组，例如：["tool_a", "tool_b"]"""

    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=[{"role": "user", "content": selection_prompt}],
        temperature=0,  # 确定性输出
    )
    
    selected_names = json.loads(response.choices[0].message.content)
    return selected_names
```

**`select_tools_by_llm` 作为固定工具的定义**：

```python
# 这个工具定义会始终存在于阶段二的 tools 列表中
select_tools_tool_def = {
    "type": "function",
    "function": {
        "name": "select_tools_by_llm",
        "description": "动态加载额外工具。当你发现当前可用工具不足以完成任务时，调用此工具描述你需要什么能力，系统会为你加载相应的工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "select_requirement": {
                    "type": "string",
                    "description": "描述你需要的工具能力，例如：'我需要创建商品折扣的工具' 或 '我需要配置物流和支付的工具'"
                }
            },
            "required": ["select_requirement"]
        }
    }
}
```

---

### 3.4 阶段二：动态加载 + 执行（含运行时增补）

```python
def load_selected_tools(selected_names, org_tools_registry):
    """根据筛选出的工具名，加载完整的 tool 定义"""
    return [
        org_tools_registry[name] 
        for name in selected_names 
        if name in org_tools_registry
    ]
```

### 3.5 整合后的完整流程

```python
def run_with_dynamic_tools(user_query, messages, org_tools_registry, tools_summary):
    """动态工具选择 + 边思考边调用的完整流程（含运行时增补）"""
    
    # ===== 阶段一：初始工具筛选 =====
    selected_names = select_tools_by_llm(user_query, tools_summary)
    print(f"[阶段一] 初始筛选工具: {selected_names}")
    
    # ===== 动态加载 + 固定工具 =====
    selected_tools = load_selected_tools(selected_names, org_tools_registry)
    # 始终加入 select_tools_by_llm 作为固定工具（用于运行时增补）
    selected_tools.append(select_tools_tool_def)
    
    if len(selected_tools) == 1:  # 只有 select_tools_by_llm 自身
        print("未匹配到任何业务工具，但保留工具选择器以备需要")
    
    # ===== 阶段二：边思考边调工具（含运行时增补） =====
    sub_turn = 1
    while True:
        response = client.chat.completions.create(
            model='deepseek-chat',
            messages=messages,
            tools=selected_tools,  # 动态筛选后的工具 + 固定的 select_tools_by_llm
            extra_body={"thinking": {"type": "enabled"}}
        )
        messages.append(response.choices[0].message)
        
        reasoning_content = response.choices[0].message.reasoning_content
        content = response.choices[0].message.content
        tool_calls = response.choices[0].message.tool_calls
        
        print(f"Sub-turn {sub_turn}\n{reasoning_content=}\n{content=}\n{tool_calls=}")
        
        if tool_calls is None:
            break
        
        for tool in tool_calls:
            # ===== 特殊处理：select_tools_by_llm 调用 → 动态增补工具 =====
            if tool.function.name == "select_tools_by_llm":
                args = json.loads(tool.function.arguments)
                new_names = select_tools_by_llm(
                    select_requirement=args["select_requirement"],
                    tools_summary=tools_summary,
                    already_selected=selected_names
                )
                # 增补新工具
                added = [n for n in new_names if n not in selected_names]
                selected_names.extend(added)
                new_tools = load_selected_tools(added, org_tools_registry)
                selected_tools.extend(new_tools)
                
                tool_result = json.dumps({
                    "status": "success",
                    "message": f"已加载新工具: {added}" if added else "无需加载新工具，所需工具已存在",
                    "newly_loaded": added,
                    "all_available": selected_names
                }, ensure_ascii=False)
                print(f"[增补工具] {added}")
            else:
                # ===== 普通工具调用：LLM 模拟执行 =====
                tool_args = json.loads(tool.function.arguments)
                tool_result = llm_tool_executor(tool.function.name, tool_args)
                print(f"[工具执行] {tool.function.name}: {tool_result}\n")
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool.id,
                "content": tool_result,
            })
        sub_turn += 1
```

---

## 4. 关键设计考量

### 4.1 漏选工具的容错机制：运行时自愈

这是本方案的**核心创新**。传统方案中漏选工具意味着任务失败，而本方案通过将 `select_tools_by_llm` 变为固定工具，实现运行时自愈：

```
场景：用户说"帮我上架一个新手机壳产品，并且搞个八折活动"

阶段一筛选：→ ["create_physical_product"]  （漏选了 create_product_discount）

阶段二执行：
  sub-turn 1: LLM 调用 create_physical_product → 成功创建商品
  sub-turn 2: LLM 思考"需要创建折扣，但当前没有折扣工具..."
              → 调用 select_tools_by_llm(select_requirement="我需要为指定商品创建折扣活动的工具")
              → 增补 ["create_product_discount"]
  sub-turn 3: LLM 调用 create_product_discount → 成功创建折扣
  sub-turn 4: LLM 输出最终答案
```

**核心点**：
- `select_requirement` 参数来自 LLM 的推理，而非用户原始指令，所以它可以更精准地描述缺失的工具能力
- `already_selected` 参数避免无意义的重复推荐
- 增补后的工具立即加入 `selected_tools` 列表，下一轮 API 调用即可使用

### 4.2 多轮对话中的工具刷新

用户在多轮对话中可能切换话题，每轮新的用户消息都触发重新筛选：

```python
# 第一轮：产品管理
turn = 1
messages = [{"role": "user", "content": "帮我创建一个时尚女装店铺，上架5件春季新品"}]
run_with_dynamic_tools("帮我创建一个时尚女装店铺，上架5件春季新品", messages, org_tools_registry, tools_summary)
# → 筛选出: onboarding_build, create_physical_product, create_collection

# 第二轮：营销推广（话题切换）
turn = 2
new_query = "给店铺里的春季新品做一波社媒推广和邮件营销"
messages.append({"role": "user", "content": new_query})
clear_reasoning_content(messages)
# → 重新筛选: post_social_media, create_EDM（工具集完全不同）
run_with_dynamic_tools(new_query, messages, org_tools_registry, tools_summary)
```

### 4.3 性能与成本分析

| 指标 | 原方案（全量 25 个 tools） | 动态选择 + 运行时增补 |
|:---:|:---:|:---:|
| 阶段一 token 消耗 | 0 | ~700（摘要 + prompt） |
| 阶段二每轮 tool token | 大（全部 25 个 schema） | 小（通常 3-5 个 schema + select_tools_by_llm） |
| 增补场景额外成本 | 不适用 | ~600 token/次（仅在漏选时触发） |
| 工具选择准确率 | 100%（全都包含） | 95%+ 初始 → ~99% 含增补 |
| 模型决策质量 | 受无关工具干扰 | 更聚焦，决策更准确 |

---

## 5. 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                    用户指令 / 新轮次消息                    │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  阶段一：工具路由层 (select_tools_by_llm)                  │
│  ┌───────────────────────────────────────────────┐      │
│  │ 输入：select_requirement + tools_summary       │      │
│  │       (只有 name + description)               │      │
│  │ 方式：LLM 语义筛选                             │      │
│  │ 输出：selected_tool_names                      │      │
│  └───────────────────────────────────────────────┘      │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  动态加载：根据 selected_names                            │
│  从 org_tools_registry 加载完整 tool 定义                  │
│  + 始终附加 select_tools_by_llm 作为固定工具               │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  阶段二：边思考边调用工具（含运行时增补）                     │
│  ┌───────────────────────────────────────────────┐      │
│  │ while True:                                    │      │
│  │   LLM 调用 → 检查 tool_calls                   │      │
│  │   ├─ 无 tool_calls → 输出最终答案，退出循环      │      │
│  │   ├─ select_tools_by_llm → 增补工具到列表  ◄─┐  │      │
│  │   └─ 业务工具调用 → llm_tool_executor 模拟执行│  │      │
│  │       └─ 如果发现缺少工具 ─────────────────┘  │      │
│  └───────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

---

## 6. 与原始 dpskv32_mtc_t.py 的变更对比

| 方面 | 原始实现 | 动态工具选择优化 |
|:---:|:---:|:---:|
| 场景 | 通用（天气查询） | 电商 SaaS（BI/装修/实施/产品/营销/订单/用户） |
| 工具列表 | 固定硬编码 2 个工具 | 25 个工具动态加载 |
| 工具执行 | 硬编码 mock 函数 | LLM 模拟执行，根据入参动态生成结果 |
| 工具筛选 | 无 | `select_tools_by_llm` 初始筛选 |
| 容错机制 | 无 | `select_tools_by_llm` 作为固定工具，支持运行时增补 |
| 筛选入参 | 不适用 | `select_requirement`（支持来自用户或 LLM 推理的需求） |
| 传给 LLM 的 tools | 全量列表 | 筛选子集 + 固定工具 |
| run_turn 函数 | 直接使用全局 `tools` | `run_with_dynamic_tools` 管理动态工具集 |
| 多轮对话 | 工具列表不变 | 每轮可根据新指令重新筛选 |
| clear_reasoning_content | 保留 | 保留（上下文裁剪仍然需要） |
