from agentic_tools.channels.templates.zalo.models import (
    ZaloSuggestedStockTemplate,
    ZaloButtonOpenUrl,
    ZaloButtonQueryHide,
)

SUGGESTED_STOCK_TEMPLATE = ZaloSuggestedStockTemplate(
    template_id="suggested_stock_v1",
    image_url="https://lenguyen153.github.io/innotech-zalo-marketing-assets/banner1.png",
    view_url="https://trading-uat.1invest.vn/priceboard",
    max_stocks=1,
    buttons=[
        ZaloButtonOpenUrl(
            title="Xem Chi Tiết",
            payload={"url": "https://trading-uat.1invest.vn/priceboard"},
        ),
        ZaloButtonQueryHide(
            title="Tiếp Tục Theo Dõi",
            payload="#GET_WEBSITE_LINK",
        ),
    ],
)
