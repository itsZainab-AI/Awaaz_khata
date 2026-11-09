import os, time, io
from dotenv import load_dotenv
from PIL import Image, ImageOps
from google import genai
from google.genai import types

load_dotenv()
print("PARSER_MODEL in .env:", os.getenv("PARSER_MODEL"))

img = ImageOps.exif_transpose(Image.open("page.png")).convert("RGB")
img.thumbnail((1280, 1280))
buf = io.BytesIO()
img.save(buf, "JPEG", quality=80)

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=60000),
)

names = [m.name.replace("models/", "") for m in client.models.list()
         if "generateContent" in (m.supported_actions or [])]
flash = [n for n in names if "flash" in n and "image" not in n and "tts" not in n]
print("flash models on your key:", flash[:15])

for model in flash[:6]:
    t = time.time()
    try:
        r = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                "List every handwritten row: name, amount, note.",
            ],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        print("OK  ", model, round(time.time() - t, 1), "s")
        print(r.text[:300])
        break
    except Exception as e:
        print("FAIL", model, round(time.time() - t, 1), "s", str(e)[:80])