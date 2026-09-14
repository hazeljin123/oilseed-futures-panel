#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天玑智能 K 线接口数据获取模块
从 ReportKLineController 接口获取标签树、周期列表、K 线和 AI 解读数据
"""

import json
import os
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

try:
    from . import _compat_requests as requests
except ImportError:
    import _compat_requests as requests

# 配置项
API_BASE_URL = os.getenv("HTFC_BASE_URL", "").rstrip("/")
API_PREFIX = "/htfc/htfc_research/hrms/report"
TIMEOUT_SECONDS = 60
VALID_PERIODS = {"-1month", "-3month", "-6month", "-1year"}

os.environ["no_proxy"] = "*"


def _get_api_base_url(base_url: Optional[str] = None) -> str:
    """获取智能 K 线接口根地址"""
    value = (base_url or API_BASE_URL or os.getenv("HTFC_BASE_URL") or "").strip().rstrip("/")
    if not value:
        raise ValueError("未识别到智能K线接口根地址，请配置环境变量 HTFC_BASE_URL。")
    return value


def _build_headers(
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, str]:
    """构建请求头"""
    api_key_value = (api_key or os.getenv("HTFC_API_KEY") or "").strip()
    if not api_key_value:
        raise ValueError("未识别到您的 API KEY，请配置环境变量 HTFC_API_KEY。")
    headers = {"Content-Type": "application/json", "apikey": api_key_value}
    token_value = (token or "").strip()
    user_id_value = (user_id or "").strip()
    if token_value:
        headers["token"] = token_value
    if user_id_value:
        headers["userId"] = user_id_value
    return headers


def _normalize_response(data: Any) -> Dict[str, Any]:
    """兼容返回 JSON 字符串的接口"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise RuntimeError("响应是字符串，但不是合法 JSON 格式")
    if not isinstance(data, dict):
        raise RuntimeError(f"响应格式异常: 期望 dict，实际为 {type(data)}")
    return data


def fetch_data_from_api(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    从智能 K 线 API 获取数据

    Args:
        path: 接口路径，如 /k/report_k_line
        params: GET 查询参数
        token: 天玑登录 token，用于 token 头
        user_id: 用户 ID，用于 userId 头
        api_key: 可选 API Key，用于 apikey 头
        base_url: 接口根地址，优先级高于 HTFC_BASE_URL

    Returns:
        dict: API 返回的数据

    Raises:
        ValueError: 当 base_url 为空时
        RuntimeError: 当 API 请求失败或业务返回错误时
    """
    root = _get_api_base_url(base_url)
    full_path = f"{API_PREFIX.rstrip('/')}/{path.lstrip('/')}"
    url = urljoin(root + "/", full_path.lstrip("/"))
    headers = _build_headers(token=token, user_id=user_id, api_key=api_key)

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params or {},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = _normalize_response(response.json())
    except requests.exceptions.Timeout:
        raise RuntimeError(f"请求超时（{TIMEOUT_SECONDS}秒）")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"连接失败: {str(e)}")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP 错误: {e.response.status_code} - {e.response.text}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"请求异常: {str(e)}")
    except json.JSONDecodeError:
        raise RuntimeError("响应不是合法的 JSON 格式")

    code = data.get("code")
    if code is not None and str(code) not in {"0", "1", "200"}:
        msg = data.get("msg", data.get("message", data.get("errorMessage", "未知错误")))
        sub_msg = data.get("subMsg")
        if sub_msg:
            msg = f"{msg}: {sub_msg}"
        raise RuntimeError(f"接口返回错误: [{code}] {msg}")

    return data


def parse_api_response(response_data: Dict[str, Any]) -> Any:
    """
    解析 API 响应，提取 data 字段

    Args:
        response_data: API 原始响应

    Returns:
        Any: 响应 data
    """
    if not isinstance(response_data, dict):
        raise RuntimeError(f"响应格式异常: 期望 dict，实际为 {type(response_data)}")
    if "data" in response_data:
        return response_data.get("data")
    return response_data


def _validate_period(period: str) -> str:
    """校验周期"""
    value = period or "-1month"
    if value not in VALID_PERIODS:
        raise ValueError("周期参数错误，仅支持 -1month、-3month、-6month、-1year。")
    return value


def _iter_labels(labels: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    """遍历标签树"""
    for item in labels:
        yield item
        children = item.get("child") or item.get("children")
        if isinstance(children, list):
            yield from _iter_labels(children)


def _is_leaf_label(label: Dict[str, Any]) -> bool:
    """判断是否叶子标签"""
    value = label.get("leafNode")
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def get_report_label_tree(
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """获取研报标签树"""
    return fetch_data_from_api(
        "/list_report_label_tree",
        token=token,
        user_id=user_id,
        api_key=api_key,
        base_url=base_url,
    )


def parse_label_tree(response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析研报标签树"""
    data = parse_api_response(response_data)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def find_labels(
    keyword: str,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按名称或 code 搜索标签"""
    labels = parse_label_tree(
        get_report_label_tree(token=token, user_id=user_id, api_key=api_key, base_url=base_url)
    )
    keyword = (keyword or "").strip()
    if not keyword:
        return list(_iter_labels(labels))

    result = []
    for item in _iter_labels(labels):
        fields = [item.get("code"), item.get("name"), item.get("parentCode")]
        text = " ".join(str(value) for value in fields if value is not None)
        if keyword in text:
            result.append(item)
    return result


def resolve_single_label(
    keyword: str,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """定位唯一标签；多标签时返回候选项"""
    labels = find_labels(keyword, token=token, user_id=user_id, api_key=api_key, base_url=base_url)
    if not labels:
        return {"status": "not_found", "keyword": keyword, "labels": []}
    if len(labels) > 1:
        return {"status": "multiple_labels", "keyword": keyword, "labels": labels}
    return {"status": "ok", "label": labels[0]}


def get_date_periods(
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """获取 K 线周期列表"""
    return fetch_data_from_api(
        "/list_date_period",
        token=token,
        user_id=user_id,
        api_key=api_key,
        base_url=base_url,
    )


def get_report_k_line(
    var_num: str,
    period: str = "-1month",
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """获取单个二级品种智能 K 线数据"""
    if not var_num:
        raise ValueError("查询智能K线必须提供 varNum。")
    period = _validate_period(period)
    return fetch_data_from_api(
        "/k/report_k_line",
        {"varNum": var_num, "period": period},
        token=token,
        user_id=user_id,
        api_key=api_key,
        base_url=base_url,
    )


def page_report_k_line(
    parent_code: str,
    period: str = "-1month",
    page_num: int = 1,
    page_size: int = 10,
    child_code: Optional[str] = None,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """分页查询一级品种大类下的二级品种智能 K 线数据"""
    if not parent_code:
        raise ValueError("分页查询智能K线必须提供 parentCode。")
    period = _validate_period(period)
    params: Dict[str, Any] = {
        "parentCode": parent_code,
        "period": period,
        "pageNum": page_num,
        "pageSize": page_size,
    }
    if child_code:
        params["childCode"] = child_code
    return fetch_data_from_api(
        "/page_report_k_line",
        params,
        token=token,
        user_id=user_id,
        api_key=api_key,
        base_url=base_url,
    )


def get_smart_kline_data(
    query: str,
    period: str = "-1month",
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取智能 K 线数据（完整流程）

    Args:
        query: 用户查询中的品种名称或标签 code
        period: 周期，默认 -1month
        token: 天玑登录 token
        user_id: 用户 ID
        api_key: 可选 API Key
        base_url: 接口根地址

    Returns:
        dict: 标签信息和智能 K 线数据
    """
    period = _validate_period(period)
    label_result = resolve_single_label(query, token=token, user_id=user_id, api_key=api_key, base_url=base_url)
    if label_result.get("status") != "ok":
        return label_result

    label = label_result["label"]
    code = label.get("code")
    if not code:
        raise RuntimeError("标签数据中未找到 code。")

    if _is_leaf_label(label):
        return {
            **label_result,
            "period": period,
            "varNum": code,
            "kline": get_report_k_line(
                code,
                period=period,
                token=token,
                user_id=user_id,
                api_key=api_key,
                base_url=base_url,
            ),
        }

    return {
        **label_result,
        "period": period,
        "parentCode": code,
        "page": page_report_k_line(
            code,
            period=period,
            token=token,
            user_id=user_id,
            api_key=api_key,
            base_url=base_url,
        ),
    }
