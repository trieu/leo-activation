from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, HttpUrl


class ZaloButtonOpenUrl(BaseModel):
    title: str
    type: str = "oa.open.url"
    payload: Dict[str, str]  # {"url": "..."}


class ZaloButtonQueryHide(BaseModel):
    title: str
    type: str = "oa.query.hide"
    payload: str  # plain string like "#GET_WEBSITE_LINK"


ZaloButton = Union[ZaloButtonOpenUrl, ZaloButtonQueryHide]


class ZaloMessageTemplate(BaseModel):
    template_id: str
    text: str
    image_url: str
    buttons: Optional[List[ZaloButton]] = None


class StockRecommendation(BaseModel):
    symbol: str
    industry: str
    exchange: str
    rank: int
    score: float
    reasons: List[str]


class ZaloSuggestedStockTemplate(BaseModel):
    template_id: str
    image_url: str
    view_url: str
    max_stocks: int = 3
    buttons: Optional[List[ZaloButton]] = None
