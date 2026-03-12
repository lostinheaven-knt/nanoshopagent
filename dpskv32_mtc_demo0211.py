"""
电商 SaaS 动态工具选择 + 边思考边调用 Demo
基于 dpskv32_mtc_t.py 优化，实现：
1. 26 个电商 SaaS 工具注册表（7大类：BI/装修/实施/产品/营销/订单/用户）
2. LLM 模拟工具执行（替代硬编码 mock）
3. select_tools_by_llm 作为固定工具，支持运行时增补漏选工具
4. 上下文裁剪（clear_reasoning_content）
5. 5个工具支持批量操作（items数组），减少工具调用轮次
6. system_prompt 设定电商经营达人角色
"""

import os
import json
import re
from openai import OpenAI

# ============================================================
# 1. OpenAI 客户端初始化
# ============================================================
client = OpenAI(
    api_key=os.environ.get('DEEPSEEK_API_KEY'),
    base_url=os.environ.get('DEEPSEEK_BASE_URL'),
)

# ============================================================
# 2. 电商 SaaS 完整工具注册表（25 个工具，7 大类）
# ============================================================
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "date": {"type": "string", "description": "报告日期 YYYY-mm-dd"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "指标列表如 ['uv','pv','gmv','conversion_rate']"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "query_type": {"type": "string", "description": "查询类型：sales/traffic/product/customer"},
                    "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}, "description": "日期范围"},
                    "dimensions": {"type": "array", "items": {"type": "string"}, "description": "分组维度"},
                    "filters": {"type": "object", "description": "筛选条件"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "template_type": {"type": "string", "description": "模板类型：fashion/electronics/food/general"},
                    "store_name": {"type": "string", "description": "店铺名称"},
                    "brand_color": {"type": "string", "description": "品牌主色调（hex格式）"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "menu_items": {"type": "array", "items": {"type": "object"}, "description": "菜单项列表，每项包含 title/url/children"},
                    "position": {"type": "string", "description": "菜单位置：header/footer/sidebar"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "page_type": {"type": "string", "description": "页面类型：home/product/collection/about"},
                    "sections": {"type": "array", "items": {"type": "object"}, "description": "页面区块配置列表"},
                    "theme_settings": {"type": "object", "description": "主题设置（字体、颜色等）"}
                },
                "required": ["store_id", "page_type", "sections"]
            }
        }
    },
    "generate_blog": {
        "type": "function",
        "function": {
            "name": "generate_blog",
            "description": "AI生成店铺博客文章，用于SEO优化和内容营销。支持一次生成多篇，通过 items 数组传入多组参数",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "items": {
                        "type": "array",
                        "description": "博客列表，每项包含一篇博客的参数",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string", "description": "博客主题"},
                                "keywords": {"type": "array", "items": {"type": "string"}, "description": "SEO关键词"},
                                "tone": {"type": "string", "description": "文章风格：professional/casual/trendy"},
                                "word_count": {"type": "integer", "description": "目标字数"}
                            },
                            "required": ["topic"]
                        }
                    }
                },
                "required": ["store_id", "items"]
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "domain_name": {"type": "string", "description": "期望的域名前缀"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "old_domain": {"type": "string", "description": "旧域名"},
                    "new_domain": {"type": "string", "description": "新域名"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "external_domain": {"type": "string", "description": "外部域名"},
                    "dns_provider": {"type": "string", "description": "DNS服务商"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "shipping_zones": {"type": "array", "items": {"type": "object"}, "description": "配送区域及运费规则"},
                    "carriers": {"type": "array", "items": {"type": "string"}, "description": "物流商列表"},
                    "free_shipping_threshold": {"type": "number", "description": "免运费门槛金额"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "payment_methods": {"type": "array", "items": {"type": "string"}, "description": "支付方式列表"},
                    "currency": {"type": "string", "description": "结算货币"},
                    "api_keys": {"type": "object", "description": "支付网关API密钥"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "tax_regions": {"type": "array", "items": {"type": "object"}, "description": "税区及税率配置"},
                    "tax_inclusive": {"type": "boolean", "description": "价格是否含税"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "password_protection": {"type": "boolean", "description": "是否保留密码保护"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "channel": {"type": "string", "description": "渠道名：facebook/instagram/tiktok/pinterest"},
                    "auth_token": {"type": "string", "description": "渠道授权token"}
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
            "description": "创建实物商品。支持一次创建多个，通过 items 数组传入多组商品参数",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "items": {
                        "type": "array",
                        "description": "商品列表，每项包含一个商品的完整参数",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "商品标题"},
                                "description": {"type": "string", "description": "商品描述"},
                                "price": {"type": "number", "description": "价格"},
                                "compare_at_price": {"type": "number", "description": "原价（划线价）"},
                                "sku": {"type": "string", "description": "SKU编码"},
                                "inventory_quantity": {"type": "integer", "description": "库存数量"},
                                "variants": {"type": "array", "items": {"type": "object"}, "description": "规格变体"},
                                "images": {"type": "array", "items": {"type": "string"}, "description": "图片URL列表"},
                                "category": {"type": "string", "description": "商品品类"},
                                "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
                                "weight": {"type": "number", "description": "重量(g)"}
                            },
                            "required": ["title", "price"]
                        }
                    }
                },
                "required": ["store_id", "items"]
            }
        }
    },
    "create_visual_product": {
        "type": "function",
        "function": {
            "name": "create_visual_product",
            "description": "创建虚拟/数字商品（如电子书、课程、会员卡、软件许可等）。支持一次创建多个，通过 items 数组传入多组参数",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "items": {
                        "type": "array",
                        "description": "虚拟商品列表，每项包含一个商品的参数",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "商品标题"},
                                "description": {"type": "string", "description": "商品描述"},
                                "price": {"type": "number", "description": "价格"},
                                "digital_file_url": {"type": "string", "description": "数字文件下载链接"},
                                "license_type": {"type": "string", "description": "许可类型：single/unlimited"},
                                "access_duration_days": {"type": "integer", "description": "有效期（天）"}
                            },
                            "required": ["title", "price"]
                        }
                    }
                },
                "required": ["store_id", "items"]
            }
        }
    },
    "create_dropshipping_product": {
        "type": "function",
        "function": {
            "name": "create_dropshipping_product",
            "description": "创建代发(dropshipping)商品，从供应商导入并设置利润率。支持一次创建多个，通过 items 数组传入多组参数",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "items": {
                        "type": "array",
                        "description": "代发商品列表，每项包含一个商品的参数",
                        "items": {
                            "type": "object",
                            "properties": {
                                "supplier_product_id": {"type": "string", "description": "供应商商品ID"},
                                "supplier": {"type": "string", "description": "供应商平台：aliexpress/cjdropshipping/spocket"},
                                "markup_percentage": {"type": "number", "description": "加价比例(%)"},
                                "custom_title": {"type": "string", "description": "自定义标题"},
                                "custom_description": {"type": "string", "description": "自定义描述"}
                            },
                            "required": ["supplier_product_id", "supplier"]
                        }
                    }
                },
                "required": ["store_id", "items"]
            }
        }
    },
    "create_collection": {
        "type": "function",
        "function": {
            "name": "create_collection",
            "description": "创建商品集合/分类，支持手动选品或自动规则。支持一次创建多个，通过 items 数组传入多组参数",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "items": {
                        "type": "array",
                        "description": "集合列表，每项包含一个集合的参数",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "集合名称"},
                                "description": {"type": "string", "description": "集合描述"},
                                "type": {"type": "string", "description": "类型：manual/automatic"},
                                "rules": {"type": "array", "items": {"type": "object"}, "description": "自动规则（当 type=automatic）"},
                                "product_ids": {"type": "array", "items": {"type": "string"}, "description": "手动选品ID列表（当 type=manual）"},
                                "image_url": {"type": "string", "description": "集合封面图"}
                            },
                            "required": ["title"]
                        }
                    }
                },
                "required": ["store_id", "items"]
            }
        }
    },
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "discount_name": {"type": "string", "description": "活动名称"},
                    "discount_type": {"type": "string", "description": "折扣类型：percentage/fixed_amount/free_shipping"},
                    "discount_value": {"type": "number", "description": "折扣值"},
                    "minimum_order_amount": {"type": "number", "description": "最低订单金额"},
                    "start_date": {"type": "string", "description": "开始日期"},
                    "end_date": {"type": "string", "description": "结束日期"},
                    "usage_limit": {"type": "integer", "description": "使用次数限制"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "discount_name": {"type": "string", "description": "活动名称"},
                    "product_ids": {"type": "array", "items": {"type": "string"}, "description": "参与商品ID"},
                    "discount_type": {"type": "string", "description": "折扣类型：percentage/fixed_amount/buy_x_get_y"},
                    "discount_value": {"type": "number", "description": "折扣值"},
                    "start_date": {"type": "string", "description": "开始日期"},
                    "end_date": {"type": "string", "description": "结束日期"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "platforms": {"type": "array", "items": {"type": "string"}, "description": "发布平台：facebook/instagram/tiktok/twitter"},
                    "content": {"type": "string", "description": "帖子内容"},
                    "media_urls": {"type": "array", "items": {"type": "string"}, "description": "图片/视频URL"},
                    "schedule_time": {"type": "string", "description": "定时发布时间（空则立即发布）"},
                    "product_ids": {"type": "array", "items": {"type": "string"}, "description": "关联商品ID"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "campaign_name": {"type": "string", "description": "活动名称"},
                    "subject": {"type": "string", "description": "邮件主题"},
                    "template": {"type": "string", "description": "邮件模板类型：promotion/newsletter/abandoned_cart/welcome"},
                    "audience_segment": {"type": "string", "description": "受众分群：all/new_customers/repeat_buyers/inactive"},
                    "content": {"type": "string", "description": "邮件正文内容"},
                    "product_ids": {"type": "array", "items": {"type": "string"}, "description": "推荐商品ID"},
                    "schedule_time": {"type": "string", "description": "发送时间"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "campaign_name": {"type": "string", "description": "活动名称"},
                    "message": {"type": "string", "description": "短信内容（注意字数限制）"},
                    "audience_segment": {"type": "string", "description": "受众分群"},
                    "include_link": {"type": "boolean", "description": "是否包含店铺链接"},
                    "schedule_time": {"type": "string", "description": "发送时间"}
                },
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "order_number": {"type": "string", "description": "订单号（精确匹配）"},
                    "customer_email": {"type": "string", "description": "客户邮箱"},
                    "status": {"type": "string", "description": "订单状态：pending/paid/shipped/delivered/cancelled/refunded"},
                    "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}, "description": "下单日期范围"},
                    "min_amount": {"type": "number", "description": "最低订单金额"},
                    "max_amount": {"type": "number", "description": "最高订单金额"},
                    "page": {"type": "integer", "description": "分页页码"},
                    "page_size": {"type": "integer", "description": "每页条数"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "order_id": {"type": "string", "description": "订单ID"},
                    "action": {"type": "string", "description": "操作类型：update_status/add_note/update_shipping/refund/cancel"},
                    "new_status": {"type": "string", "description": "新状态（当 action=update_status）"},
                    "note": {"type": "string", "description": "备注内容（当 action=add_note）"},
                    "tracking_number": {"type": "string", "description": "物流单号（当 action=update_shipping）"},
                    "carrier": {"type": "string", "description": "物流商（当 action=update_shipping）"},
                    "refund_amount": {"type": "number", "description": "退款金额（当 action=refund）"},
                    "refund_reason": {"type": "string", "description": "退款原因（当 action=refund）"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "segment_name": {"type": "string", "description": "分群名称"},
                    "conditions": {"type": "array", "items": {"type": "object"}, "description": "分群条件列表，每个条件含 field/operator/value"},
                    "logic": {"type": "string", "description": "条件逻辑：and/or"},
                    "description": {"type": "string", "description": "分群描述"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "customer_id": {"type": "string", "description": "客户ID"},
                    "vip_level": {"type": "string", "description": "VIP等级：bronze/silver/gold/platinum/diamond"},
                    "reason": {"type": "string", "description": "调整原因"},
                    "auto_rules": {"type": "object", "description": "自动升降级规则（批量设置时使用）"}
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
                    "store_id": {"type": "string", "description": "店铺ID"},
                    "customer_id": {"type": "string", "description": "客户ID"},
                    "action": {"type": "string", "description": "操作类型：add/deduct/redeem"},
                    "points": {"type": "integer", "description": "积分数量"},
                    "reason": {"type": "string", "description": "操作原因：purchase/promotion/manual/redeem_coupon"},
                    "reference_order_id": {"type": "string", "description": "关联订单ID（如因购买获得积分）"}
                },
                "required": ["store_id", "customer_id", "action", "points"]
            }
        }
    },
}

# ============================================================
# 3. 自动生成工具摘要列表（仅 name + description）
# ============================================================
tools_summary = [
    {"name": name, "description": tool_def["function"]["description"]}
    for name, tool_def in org_tools_registry.items()
]

# ============================================================
# 4. select_tools_by_llm 作为固定工具的定义
# ============================================================
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

# ============================================================
# 5. 工具执行层 —— LLM 模拟（替代硬编码 Mock）
# ============================================================
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
        temperature=0.7,
    )

    return response.choices[0].message.content


# ============================================================
# 6. 阶段一：LLM 工具筛选
# ============================================================
def select_tools_by_llm(select_requirement, tools_summary_list, already_selected=None):
    """用 LLM 从工具摘要中筛选相关工具

    Args:
        select_requirement: 工具选择需求描述（可以是用户指令，也可以是动态产生的需求）
        tools_summary_list: 所有工具的 name+description 摘要列表
        already_selected: 已经选中的工具名列表（增补时避免重复推荐）

    Returns:
        list: 筛选出的工具名列表
    """
    summary_text = "\n".join(
        f"- {t['name']}: {t['description']}" for t in tools_summary_list
    )

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
        temperature=0,
    )

    raw_content = response.choices[0].message.content.strip()
    # 尝试从返回内容中提取 JSON 数组（兼容模型可能附带的 markdown 代码块）
    json_match = re.search(r'\[.*?\]', raw_content, re.DOTALL)
    if json_match:
        selected_names = json.loads(json_match.group())
    else:
        selected_names = json.loads(raw_content)

    return selected_names


# ============================================================
# 7. 工具加载
# ============================================================
def load_selected_tools(selected_names):
    """根据筛选出的工具名，从 org_tools_registry 加载完整的 tool 定义"""
    return [
        org_tools_registry[name]
        for name in selected_names
        if name in org_tools_registry
    ]


# ============================================================
# 8. 上下文裁剪
# ============================================================
def clear_reasoning_content(messages):
    """清除历史消息中的 reasoning_content 以节省上下文"""
    for message in messages:
        if hasattr(message, 'reasoning_content'):
            message.reasoning_content = None


# ============================================================
# 9. 核心流程：动态工具选择 + 边思考边调用（含运行时增补）
# ============================================================
def run_with_dynamic_tools(user_query, messages):
    """动态工具选择 + 边思考边调用的完整流程（含运行时增补）

    Args:
        user_query: 用户指令文本
        messages: 对话消息列表
    """
    # ===== 阶段一：初始工具筛选 =====
    print(f"\n{'='*60}")
    print(f"[阶段一] 正在根据用户指令筛选工具...")
    print(f"用户指令: {user_query}")
    print(f"{'='*60}")

    selected_names = select_tools_by_llm(user_query, tools_summary)
    print(f"[阶段一] 初始筛选结果: {selected_names}")

    # ===== 动态加载 + 固定工具 =====
    selected_tools = load_selected_tools(selected_names)
    # 始终加入 select_tools_by_llm 作为固定工具（用于运行时增补）
    selected_tools.append(select_tools_tool_def)

    tool_names_display = [t["function"]["name"] for t in selected_tools]
    print(f"[阶段一] 已加载工具: {tool_names_display}")

    if len(selected_tools) == 1:  # 只有 select_tools_by_llm 自身
        print("[阶段一] 未匹配到任何业务工具，但保留工具选择器以备需要")

    # ===== 阶段二：边思考边调工具（含运行时增补） =====
    print(f"\n{'='*60}")
    print(f"[阶段二] 开始边思考边调用工具...")
    print(f"{'='*60}")

    sub_turn = 1
    while True:
        print(f"\n--- Sub-turn {sub_turn} ---")

        response = client.chat.completions.create(
            model='deepseek-chat',
            messages=messages,
            tools=selected_tools,
            extra_body={"thinking": {"type": "enabled"}}
        )
        msg = response.choices[0].message
        messages.append(msg)

        reasoning_content = msg.reasoning_content
        content = msg.content
        tool_calls = msg.tool_calls

        # 打印思考过程（截断过长内容）
        if reasoning_content:
            display_reasoning = reasoning_content[:500] + "..." if len(reasoning_content) > 500 else reasoning_content
            print(f"[思考] {display_reasoning}")
        if content:
            print(f"[回复] {content}")

        # 无工具调用 → 得到最终答案，退出循环
        if tool_calls is None:
            print(f"\n[阶段二] 已获得最终答案，结束循环")
            break

        # 处理工具调用
        for tool in tool_calls:
            tool_name = tool.function.name
            tool_args = json.loads(tool.function.arguments)
            print(f"\n[工具调用] {tool_name}")
            print(f"[参数] {json.dumps(tool_args, ensure_ascii=False, indent=2)}")

            if tool_name == "select_tools_by_llm":
                # ===== 特殊处理：运行时增补工具 =====
                requirement = tool_args["select_requirement"]
                print(f"[增补请求] {requirement}")

                new_names = select_tools_by_llm(
                    select_requirement=requirement,
                    tools_summary_list=tools_summary,
                    already_selected=selected_names
                )
                # 增补新工具（去重）
                added = [n for n in new_names if n not in selected_names]
                selected_names.extend(added)
                new_tools = load_selected_tools(added)
                selected_tools.extend(new_tools)

                tool_result = json.dumps({
                    "status": "success",
                    "message": f"已加载新工具: {added}" if added else "无需加载新工具，所需工具已存在",
                    "newly_loaded": added,
                    "all_available": selected_names
                }, ensure_ascii=False)
                print(f"[增补结果] 新增工具: {added}")

            else:
                # ===== 普通工具调用：LLM 模拟执行 =====
                tool_result = llm_tool_executor(tool_name, tool_args)
                # 截断显示
                display_result = tool_result[:300] + "..." if len(tool_result) > 300 else tool_result
                print(f"[执行结果] {display_result}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool.id,
                "content": tool_result,
            })

        sub_turn += 1


# ============================================================
# 10. System Prompt
# ============================================================
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

# ============================================================
# 11. 主程序 —— 交互式命令行多轮对话
# ============================================================

def get_user_input(prompt):
    """支持多行输入的用户输入函数

    使用方式：
    - 短指令：直接输入一行后回车即可提交
    - 长指令（含回车）：输入多行内容，最后单独一行输入 /// 表示提交
    - 特殊命令（/quit 等）：直接输入即提交
    """
    print(prompt, end="")
    first_line = input().strip()

    # 特殊命令或空行：直接返回
    if not first_line or first_line.startswith("/"):
        return first_line

    # 第一行以 /// 结尾 → 去掉标记返回
    if first_line.endswith("///"):
        return first_line[:-3].strip()

    # 检查是否需要多行输入：提示用户
    print("  (多行输入模式：继续输入，单独一行 /// 提交；或直接回车提交当前内容)")
    lines = [first_line]

    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break

        # 单独一行 /// → 结束多行输入
        if line.strip() == "///":
            break

        # 空行 → 如果是第一次遇到空行，当作结束（兼容快速单行输入后直接回车）
        if line == "" and len(lines) == 1:
            break

        lines.append(line)

    return "\n".join(lines).strip()


if __name__ == "__main__":
    print("=" * 60)
    print("  电商 SaaS 动态工具选择 — 交互式 Demo")
    print(f"  已注册工具: {len(org_tools_registry)} 个（7大类）")
    print("=" * 60)
    print("输入你的指令开始对话：")
    print("  短指令 → 输入后直接回车提交")
    print("  长指令 → 输入多行内容，单独一行 /// 提交")
    print("特殊命令：")
    print("  /quit  或 /exit  — 退出程序")
    print("  /reset           — 清空对话历史，开启新会话")
    print("  /history         — 查看当前对话轮次数")
    print("  /tools           — 列出所有可用工具摘要")
    print("=" * 60)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    turn = 0

    while True:
        # ===== 等待用户输入 =====
        try:
            user_input = get_user_input(f"\n[Turn {turn + 1}] 你> ")
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        # ===== 特殊命令处理 =====
        if user_input.lower() in ("/quit", "/exit"):
            print("再见！")
            break

        if user_input.lower() == "/reset":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            turn = 0
            print("[系统] 对话已重置，你可以开始新的会话。")
            continue

        if user_input.lower() == "/history":
            user_turns = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
            print(f"[系统] 当前会话已进行 {user_turns} 轮对话，messages 共 {len(messages)} 条。")
            continue

        if user_input.lower() == "/tools":
            print("[系统] 可用工具列表：")
            for i, t in enumerate(tools_summary, 1):
                print(f"  {i:2d}. {t['name']}: {t['description']}")
            continue

        # ===== 正常对话流程 =====
        turn += 1

        # 非首轮时清除历史 reasoning_content 节省上下文
        if turn > 1:
            clear_reasoning_content(messages)

        messages.append({"role": "user", "content": user_input})

        print(f"\n{'#' * 60}")
        print(f"# Turn {turn}")
        print(f"{'#' * 60}")

        try:
            run_with_dynamic_tools(user_input, messages)
        except Exception as e:
            print(f"\n[错误] 执行过程中出现异常: {e}")
            print("[系统] 你可以继续输入新指令，或输入 /reset 重置对话。")

