from __future__ import annotations

import re
from typing import Dict

from nanoshopagent.utils.redact_text import sanitize_text


TOOL_NAME_ZH: Dict[str, str] = {
    # BI
    "daily_report": "生成运营日报",
    "data_query": "查询经营数据",
    # 装修
    "onboarding_build": "店铺初始化搭建",
    "add_menu": "配置导航菜单",
    "page_decoration": "页面装修配置",
    "generate_blog": "生成博客内容",
    # 实施
    "create_domain": "创建店铺域名",
    "change_domain": "修改店铺域名",
    "connect_outer_domain": "绑定外部域名",
    "logistics_setup": "配置物流方案",
    "payment_setup": "配置支付方式",
    "tax_setup": "配置税费规则",
    "unlock_store": "发布/解锁店铺",
    "connect_social_channel": "绑定社媒渠道",
    # 产品
    "create_physical_product": "创建实物商品",
    "create_visual_product": "创建数字商品",
    "create_dropshipping_product": "创建代发商品",
    "create_collection": "创建商品集合",
    "update_collection": "更新商品集合",
    # 营销
    "create_order_discount": "创建订单折扣",
    "create_product_discount": "创建商品折扣",
    "post_social_media": "发布社媒内容",
    "create_EDM": "创建EDM邮件营销",
    "create_sms": "创建短信营销",
    # 订单
    "search_order": "查询订单",
    "update_order": "更新订单",
    # 用户
    "create_customer_segment": "创建用户分群",
    "set_vip_level": "设置VIP等级",
    "update_customer_points": "更新用户积分",
    # meta
    "select_tools_by_llm": "动态选择工具",
}


def tool_display_name(tool_name: str) -> str:
    return TOOL_NAME_ZH.get(tool_name, tool_name)


_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)


def _redact_json_blocks(text: str) -> str:
    """Strong-redact JSON-ish blocks inside text."""

    if not text:
        return text

    out = text

    # 1) redact fenced blocks first
    out = _CODE_FENCE_RE.sub("【JSON已脱敏】", out)

    # 2) redact inline JSON objects/arrays that look like they contain key:value
    obj_re = re.compile(r"\{[\s\S]*?\"\s*:\s*[\s\S]*?\}")
    arr_re = re.compile(r"\[[\s\S]*?\"\s*:\s*[\s\S]*?\]")
    out = obj_re.sub("【JSON已脱敏】", out)
    out = arr_re.sub("【JSON已脱敏】", out)

    return out


def sanitize_reasoning(reasoning: str) -> str:
    """User-facing reasoning: keep text, only apply redaction/mapping.

    No extra model calls.
    """

    if reasoning is None:
        return ""

    out = reasoning

    # strong redact JSON-ish blocks
    out = _redact_json_blocks(out)

    # map tool names -> zh alias (use plain replace first to avoid unicode boundary edge cases)
    for k, zh in TOOL_NAME_ZH.items():
        out = out.replace(k, zh)

    # also handle function-style mentions like `payment_setup(...)`
    for k, zh in TOOL_NAME_ZH.items():
        out = re.sub(rf"\b{re.escape(k)}\b", zh, out)

    # mask common internal ids
    out = re.sub(r"\bcall_[A-Za-z0-9]+\b", "call_***", out)
    out = re.sub(r"\b(paycfg|prod|order|cust|seg)_[A-Za-z0-9]+\b", r"\1_***", out)

    # finally mask any secret-looking tokens
    out = sanitize_text(out)

    return out
