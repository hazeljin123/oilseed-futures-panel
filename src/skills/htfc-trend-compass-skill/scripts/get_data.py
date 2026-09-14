#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Htfc trend compass API helpers."""

import json
import os
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

try:
    from . import _compat_requests as requests
except ImportError:
    import _compat_requests as requests

API_BASE_URL = os.getenv("HTFC_BASE_URL", "").rstrip("/")
TIMEOUT_SECONDS = 60
SUCCESS_CODES = {"0", "200"}

os.environ["no_proxy"] = "*"


def _get_base_url(base_url: Optional[str] = None) -> str:
    value = (base_url or API_BASE_URL or os.getenv("HTFC_BASE_URL") or "").strip().rstrip("/")
    if not value:
        raise ValueError("未识别到天玑接口根地址，请配置环境变量 HTFC_BASE_URL。")
    return value


def _headers(token: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, str]:
    api_key_value = (os.getenv("HTFC_API_KEY") or "").strip()
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


def _normalize_response(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("响应是字符串，但不是合法 JSON。") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"响应格式异常：期望 dict，实际为 {type(payload)}。")
    return payload


def _check_business_code(payload: Dict[str, Any]) -> Dict[str, Any]:
    code = payload.get("errorCode", payload.get("code"))
    if code is not None and str(code) not in SUCCESS_CODES:
        message = payload.get("errorMessage") or payload.get("message") or payload.get("msg") or "未知错误"
        raise RuntimeError(f"接口返回错误：[{code}] {message}")
    return payload


def request_api(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    url = urljoin(_get_base_url(base_url) + "/", path.lstrip("/"))
    try:
        response = requests.request(
            method.upper(),
            url,
            headers=_headers(token=token, user_id=user_id),
            params=params or {},
            json=json_body,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _check_business_code(_normalize_response(response.json()))
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"请求超时（{TIMEOUT_SECONDS}秒）。") from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"连接失败：{exc}") from exc
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"HTTP 错误：{exc.response.status_code} - {exc.response.text}") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"请求异常：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("响应不是合法 JSON。") from exc


def data_of(response_data: Dict[str, Any]) -> Any:
    return response_data.get("data") if isinstance(response_data, dict) and "data" in response_data else response_data


def get_typical_short(
    codes: str,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """GET /bus/trend/typical/short?codes=..."""
    if not codes:
        raise ValueError("查询短线典型指标必须提供 codes，多个代码用逗号分隔。")
    return request_api("GET", "/bus/trend/typical/short", params={"codes": codes}, token=token, user_id=user_id, base_url=base_url)


def get_product_detail(code: str, token: Optional[str] = None, user_id: Optional[str] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
    """GET /bus/trend/product/{code}."""
    if not code:
        raise ValueError("查询风向罗盘旧版品种详情必须提供 code。")
    return request_api("GET", f"/bus/trend/product/{code}", token=token, user_id=user_id, base_url=base_url)


def get_products(token: Optional[str] = None, user_id: Optional[str] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
    """GET /bus/trend/products."""
    return request_api("GET", "/bus/trend/products", token=token, user_id=user_id, base_url=base_url)


def get_rank(token: Optional[str] = None, user_id: Optional[str] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
    """POST /hrms/trend/rank."""
    return request_api("POST", "/hrms/trend/rank", json_body={}, token=token, user_id=user_id, base_url=base_url)


def get_overview(
    codes: Optional[str] = None,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """POST /hrms/trend/overview."""
    body: Dict[str, Any] = {}
    if codes is not None:
        body["codes"] = codes
    return request_api("POST", "/hrms/trend/overview", json_body=body, token=token, user_id=user_id, base_url=base_url)


def get_code_rank_data(token: Optional[str] = None, user_id: Optional[str] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
    """GET /hrms/trend/codeRankData."""
    return request_api("GET", "/hrms/trend/codeRankData", token=token, user_id=user_id, base_url=base_url)


def save_code_rank(
    ranks: List[Any],
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """POST /hrms/trend/codeRank."""
    if not isinstance(ranks, list):
        raise ValueError("保存风向罗盘品种排序必须提供 ranks 数组。")
    return request_api("POST", "/hrms/trend/codeRank", json_body={"ranks": ranks}, token=token, user_id=user_id, base_url=base_url)


def get_code_trend(
    code: str,
    date: Optional[str] = None,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """POST /hrms/trend/codeTrend."""
    if not code:
        raise ValueError("查询单品种趋势必须提供 code。")
    body: Dict[str, Any] = {"code": code}
    if date:
        body["date"] = date
    return request_api("POST", "/hrms/trend/codeTrend", json_body=body, token=token, user_id=user_id, base_url=base_url)


def get_code_detail(
    code: str,
    date: Optional[str] = None,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """POST /hrms/trend/codeDetail."""
    if not code:
        raise ValueError("查询单品种风向详情必须提供 code。")
    body: Dict[str, Any] = {"code": code}
    if date:
        body["date"] = date
    return request_api("POST", "/hrms/trend/codeDetail", json_body=body, token=token, user_id=user_id, base_url=base_url)


def query_exchange_futures(
    module_type: int = 2,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """GET /bus/queryExchangeFutures. moduleType=2 for trend compass."""
    return request_api("GET", "/bus/queryExchangeFutures", params={"moduleType": module_type}, token=token, user_id=user_id, base_url=base_url)


def _iter_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def find_codes(
    keyword: str,
    token: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search code candidates in overview and exchange future tree."""
    if not keyword:
        raise ValueError("搜索风向罗盘品种必须提供关键字。")
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for response in (
        get_overview(token=token, user_id=user_id, base_url=base_url),
        query_exchange_futures(token=token, user_id=user_id, base_url=base_url),
    ):
        for item in _iter_dicts(data_of(response)):
            fields = [
                item.get("code"),
                item.get("codeName"),
                item.get("labelCode"),
                item.get("labelName"),
                item.get("name"),
            ]
            text = " ".join(str(value) for value in fields if value is not None)
            if keyword in text:
                key = item.get("code") or item.get("labelCode") or text
                if key not in seen:
                    seen.add(key)
                    candidates.append(item)
    return candidates
