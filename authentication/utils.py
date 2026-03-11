import random
import io
import string
from PIL import Image, ImageColor, ImageFont, ImageDraw, ImageFilter


def generate_verify_code():
    background = (
        random.randrange(200, 250),
        random.randrange(200, 250),
        random.randrange(200, 250),
    )
    outline = ImageColor.getrgb("Grey")
    line_color = (
        random.randrange(1, 255),
        random.randrange(1, 255),
        random.randrange(1, 255),
    )
    img_width = 200
    img_height = 80
    font_color = (
        random.randrange(100, 160),
        random.randrange(100, 160),
        random.randrange(100, 160),
    )
    font = ImageFont.load_default(img_height - 4)

    canvas = Image.new("RGB", (img_width, img_height))
    code = random.sample(string.ascii_letters + string.digits, 4)
    draw = ImageDraw.Draw(canvas)
    # background
    box = (0, 0, img_width, img_height)
    draw.rectangle(box, fill=background, outline=outline)

    yawp_rate = 0.07
    area = int(yawp_rate * img_height * img_width)
    for x in range(area):
        y = random.randrange(0, img_height - 1)
        x = random.randrange(0, img_width - 1)
        draw.point((x, y), fill=(0, 0, 0))

    # noise lines
    for i in range(random.randrange(3, 23)):
        x = random.randrange(0, img_width - 1)
        y = random.randrange(0, img_height - 1)
        xl = random.randrange(0, 6)
        yl = random.randrange(0, 12)
        draw.line((x, y, x + xl + 40, y + yl + 20), fill=line_color, width=1)

    # print the verify code
    x = 5
    for i in code:
        y = random.randrange(-10, 10)
        draw.text((x, y), i, font=font, fill=random.choice(font_color))
        x += 45

    verify_code = "".join(code).lower()
    im = canvas.filter(ImageFilter.SMOOTH_MORE)
    buf = io.BytesIO()
    im.save(buf, "gif")
    buf.seek(0)

    return verify_code, buf


from .utils import generate_verify_code


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
