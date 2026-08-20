"""天气查询工具：支持 Tavily 与豆包搜索 REST API。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from config.settings import DoubaoSearchConfig, TavilyConfig, WeatherToolConfig

WEATHER_KEYWORDS = (
    "天气", "气温", "温度", "多少度", "几度", "下雨", "降雨", "雨", "带伞",
    "冷不冷", "热不热", "预报", "空气质量", "风大", "台风",
)

PERIOD_KEYWORDS = {
    "凌晨": "凌晨",
    "早上": "上午",
    "早晨": "上午",
    "上午": "上午",
    "中午": "中午",
    "午后": "下午",
    "下午": "下午",
    "傍晚": "傍晚",
    "晚上": "晚上",
    "夜里": "夜间",
    "夜间": "夜间",
}

LOCATION_HINTS = (
    "北京", "上海", "天津", "重庆", "广州", "深圳", "杭州", "南京", "苏州", "成都", "武汉",
    "西安", "长沙", "郑州", "青岛", "宁波", "厦门", "福州", "济南", "合肥", "昆明",
    "松江", "浦东", "徐汇", "闵行", "黄浦", "静安", "长宁", "普陀", "宝山", "嘉定",
)


class WeatherSearchTool:
    def __init__(self, tavily: TavilyConfig, doubao: DoubaoSearchConfig, weather: WeatherToolConfig):
        self._tavily = tavily
        self._doubao = doubao
        self._weather = weather
        timeout_s = doubao.timeout_s if weather.provider == "doubao" else tavily.timeout_s
        self._client = httpx.AsyncClient(timeout=timeout_s)

    @property
    def provider(self) -> str:
        return self._weather.provider

    @property
    def available(self) -> bool:
        if not self._weather.enabled:
            return False
        if self.provider == "tavily":
            return self._tavily.enabled and bool(self._tavily.api_key)
        if self.provider == "doubao":
            return self._doubao.enabled and bool(self._doubao.api_key)
        return False

    def matches(self, text: str) -> bool:
        return self._weather.enabled and any(keyword in text for keyword in WEATHER_KEYWORDS)

    async def search(self, user_text: str) -> dict:
        """查询天气相关实时信息，返回统一结构。"""
        now = datetime.now(ZoneInfo(self._weather.timezone))
        context = analyze_weather_context(user_text, now, self._weather.default_location)
        query = build_weather_query(user_text, context, self._weather.timezone)
        if self.provider == "tavily":
            data = await self._search_tavily(query)
        elif self.provider == "doubao":
            data = await self._search_doubao(query)
        else:
            raise ValueError(f"未知 weather.provider: {self.provider}")
        data["voxclaw_context"] = context
        data["provider"] = self.provider
        logger.info("{} 天气查询完成：{} 条结果", self.provider, len(data.get("results") or []))
        return data

    async def _search_tavily(self, query: str) -> dict:
        payload = {
            "query": query,
            "search_depth": self._tavily.search_depth,
            "max_results": self._tavily.max_results,
            "include_answer": True,
            "include_raw_content": False,
        }
        headers = {
            "Authorization": f"Bearer {self._tavily.api_key}",
            "Content-Type": "application/json",
        }
        resp = await self._client.post(self._tavily.endpoint, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning("Tavily 天气查询失败 [{}]: {}", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        return {
            "answer": data.get("answer") or "",
            "results": data.get("results") or [],
            "raw": data,
        }

    async def _search_doubao(self, query: str) -> dict:
        payload = {
            "Query": query,
            "DocCount": self._doubao.doc_count,
            "MaxSnippetLength": self._doubao.max_snippet_length,
            "MaxImageCountPerDoc": self._doubao.max_image_count_per_doc,
        }
        headers = {
            "Authorization": f"Bearer {self._doubao.api_key}",
            "Content-Type": "application/json",
        }
        resp = await self._client.post(self._doubao.endpoint, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning("豆包搜索天气查询失败 [{}]: {}", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        raw = parse_doubao_response(resp.text)
        return normalize_doubao_response(raw, resp.text)

    async def close(self):
        await self._client.aclose()


# 兼容旧 import 名称
TavilyWeatherTool = WeatherSearchTool


def parse_doubao_response(text: str) -> object:
    """豆包搜索示例以行流式输出；这里兼容 JSON、NDJSON 和纯文本。"""
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    items = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line.removeprefix("data:").strip()
        if line == "[DONE]":
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"content": line})
    return items


def normalize_doubao_response(raw: object, raw_text: str) -> dict:
    """把豆包搜索结果尽量归一成 Tavily 风格的 answer/results。"""
    results = []
    answer = ""

    def add_result(item: dict):
        title = pick_first(item, "title", "Title", "name", "Name") or "豆包搜索结果"
        url = pick_first(item, "url", "Url", "URL", "link", "Link") or ""
        content = pick_first(
            item, "content", "Content", "snippet", "Snippet", "summary", "Summary", "abstract", "Abstract"
        ) or ""
        if content or url:
            results.append({"title": title, "url": url, "content": str(content)})

    if isinstance(raw, dict):
        answer = str(pick_first(raw, "answer", "Answer", "summary", "Summary") or "")
        for key in ("results", "Results", "docs", "Docs", "data", "Data", "items", "Items"):
            value = raw.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        add_result(item)
            elif isinstance(value, dict):
                for nested_key in ("results", "Results", "docs", "Docs", "items", "Items"):
                    nested = value.get(nested_key)
                    if isinstance(nested, list):
                        for item in nested:
                            if isinstance(item, dict):
                                add_result(item)
        if not results:
            add_result(raw)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                add_result(item)
            else:
                results.append({"title": "豆包搜索结果", "url": "", "content": str(item)})

    if not answer and results:
        answer = "\n".join(result["content"] for result in results[:3] if result.get("content"))
    if not results and raw_text:
        results.append({"title": "豆包搜索返回", "url": "", "content": raw_text[:2000]})
    return {"answer": answer, "results": results, "raw": raw}


def pick_first(data: dict, *keys: str):
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def analyze_weather_context(user_text: str, now: datetime, default_location: str) -> dict:
    """把中文天气问法解析成明确日期、时段和默认地点上下文。"""
    day_offset = 0
    day_label = "今天"
    range_label = ""
    if "大后天" in user_text:
        day_offset = 3
        day_label = "大后天"
    elif "后天" in user_text:
        day_offset = 2
        day_label = "后天"
    elif "明天" in user_text or "明日" in user_text:
        day_offset = 1
        day_label = "明天"
    elif "最近" in user_text or "这几天" in user_text or "未来几天" in user_text or "未来" in user_text:
        range_label = "未来三天"
        day_label = "未来几天"

    target_date = now.date() + timedelta(days=day_offset)
    period = "全天"
    for keyword, label in PERIOD_KEYWORDS.items():
        if keyword in user_text:
            period = label
            break
    if any(keyword in user_text for keyword in ("现在", "当前", "此刻", "多少度", "几度")):
        period = "当前"

    explicit_location = any(hint in user_text for hint in LOCATION_HINTS) or any(
        suffix in user_text for suffix in ("市", "区", "县", "镇", "省")
    )
    location = "用户指定地点" if explicit_location else default_location

    return {
        "now": now.strftime("%Y-%m-%d %H:%M"),
        "target_date": target_date.isoformat(),
        "day_label": day_label,
        "period": period,
        "range_label": range_label,
        "location": location,
        "default_location": default_location,
        "explicit_location": explicit_location,
    }


def build_weather_query(user_text: str, context: dict, timezone: str) -> str:
    location_part = user_text if context["explicit_location"] else context["default_location"]
    target_part = context["range_label"] or f"{context['target_date']} {context['day_label']} {context['period']}"
    return (
        f"{location_part} {target_part} 天气 逐小时预报 降雨概率 气温 是否需要带伞\n"
        f"用户原始问题：{user_text}\n"
        f"当前时间：{context['now']}，时区：{timezone}。\n"
        "请优先返回与目标日期和时段完全匹配的最新天气信息；如果问下午/上午/晚上，请查逐小时预报或分时段预报。"
    )


# 兼容旧函数名
build_tavily_weather_query = build_weather_query


def build_weather_summary_prompt(user_text: str, search_data: dict) -> str:
    answer = search_data.get("answer") or ""
    results = search_data.get("results") or []
    context = search_data.get("voxclaw_context") or {}
    provider = search_data.get("provider") or "search"
    lines = []
    for index, item in enumerate(results[:5], start=1):
        title = item.get("title") or "未命名来源"
        url = item.get("url") or ""
        content = (item.get("content") or "").replace("\n", " ")[:500]
        lines.append(f"{index}. {title}\nURL: {url}\n内容: {content}")

    return (
        f"用户正在询问天气。请只基于下面的 {provider} 实时搜索结果回答，不要编造。\n"
        "要求：用中文口语化回答，适合语音播报；控制在三到五句话以内；"
        "必须优先围绕目标日期和目标时段回答，尽量包含地点、时间、温度、天气状况，如果存在降雨，给出带伞建议，如果天气炎热或者寒冷，给出相应的建议。\n"
        "如果搜索结果不够明确，直接说明信息可能不完整，不要用常识补全。\n\n"
        f"用户问题：{user_text}\n\n"
        f"解析出的查询上下文：{context}\n\n"
        f"搜索 answer：{answer}\n\n"
        "搜索结果：\n"
        + "\n\n".join(lines)
    )
