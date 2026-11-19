"""Create the app icon and synthetic evidence with simple geometric shapes."""
from pathlib import Path
from io import BytesIO
import base64
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent.parent
(root / "assets").mkdir(exist_ok=True)
icon = Image.new("RGB", (1024, 1024), "#183e34")
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((195, 250, 770, 730), radius=90, fill="#d4ef91")
draw.polygon([(280, 360), (705, 360), (655, 635), (325, 635)], fill="#205b46")
for x in [370, 470, 570]:
    draw.line((x, 405, x + 15, 590), fill="#d4ef91", width=22)
draw.rounded_rectangle((260, 320, 730, 370), radius=20, fill="#205b46")
icon.save(root / "assets/icon.png")
photo = Image.new("RGB", (640, 400), "#e7ecdf")
draw = ImageDraw.Draw(photo)
draw.rectangle((0, 280, 640, 400), fill="#bbc8af")
draw.polygon([(110, 130), (535, 130), (490, 305), (145, 305)], fill="#205b46")
for x in [185, 265, 345, 425]:
    draw.line((x, 155, x + 10, 280), fill="#527d58", width=10)
draw.rectangle((100, 118, 545, 142), fill="#183e34")
draw.text((225, 215), "SAMPLE EVIDENCE", fill="#d4ef91", font=ImageFont.load_default(size=22))
draw.text((20, 20), "Fieldwork One / Synthetic demo image", fill="#183e34", font=ImageFont.load_default(size=18))
buffer = BytesIO()
photo.save(buffer, format="JPEG", quality=75)
(root / "src/shared/sample-photo.ts").write_text("export const samplePhoto = '" + base64.b64encode(buffer.getvalue()).decode() + "';\n")
