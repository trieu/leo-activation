EMAIL_STOCK_PICKS_SUBJECT = "📊 Cổ phiếu tiềm năng hôm nay dành cho bạn"

EMAIL_STOCK_PICKS_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px;color:#333">
  <h2 style="color:#1a73e8">📊 Cổ phiếu tiềm năng hôm nay</h2>
  <p>Hệ thống đã phân tích và chọn lọc các mã phù hợp với khẩu vị đầu tư của bạn:</p>

  {% for stock in stocks %}
  <div style="border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin-bottom:12px">
    <h3 style="margin:0 0 4px 0">
      {{ stock.symbol }}
      <span style="font-size:13px;color:#666">({{ stock.exchange }})</span>
    </h3>
    <p style="margin:2px 0;color:#888;font-size:13px">
      Ngành: {{ stock.industry }} &nbsp;|&nbsp; Score: {{ "%.2f"|format(stock.score) }}
    </p>
    <ul style="margin:8px 0;padding-left:20px">
      {% for reason in stock.reasons %}
      <li style="font-size:14px;margin-bottom:4px">{{ reason }}</li>
      {% endfor %}
    </ul>
  </div>
  {% endfor %}

  <p style="margin-top:24px">
    <a href="https://trading-uat.1invest.vn/priceboard"
       style="background:#1a73e8;color:white;padding:10px 20px;border-radius:4px;text-decoration:none;font-size:14px">
      Xem Chi Tiết Trên Hệ Thống
    </a>
  </p>
  <p style="font-size:12px;color:#aaa;margin-top:32px;border-top:1px solid #eee;padding-top:12px">
    © {{ year }} LEO CDP &nbsp;|&nbsp; Bạn nhận email này vì đã đăng ký nhận thông báo đầu tư.
  </p>
</body>
</html>
"""
