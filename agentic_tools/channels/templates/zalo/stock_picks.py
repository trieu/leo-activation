from agentic_tools.channels.templates.zalo.models import (
    ZaloMessageTemplate,
    ZaloButtonOpenUrl,
    ZaloButtonQueryHide,
)

STOCK_PICKS_TEMPLATE = ZaloMessageTemplate(
    template_id="stock_picks_v1",
    text=(
        "🚀 Top 3 Mã Cổ Phiếu Tiềm Năng\n\n"
        "Hệ thống đã chọn lọc các mã phù hợp với khẩu vị rủi ro của bạn.\n\n"
        "Nhấn nút bên dưới để xem hoặc tiếp tục theo dõi!"
    ),
    image_url="https://lenguyen153.github.io/innotech-zalo-marketing-assets/banner1.png",
    buttons=[
        ZaloButtonOpenUrl(
            title="Xem Website",
            payload={"url": "https://post.oa.zalo.me/d?id=5670898f40caa994f0db"},
        ),
        ZaloButtonQueryHide(
            title="Tiếp Tục Theo Dõi",
            payload="#GET_WEBSITE_LINK",
        ),
    ],
)
