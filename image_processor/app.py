import os

from django.db.models import QuerySet
from json2html import *
from django.core.wsgi import get_wsgi_application
from importlib.util import find_spec
from PIL import Image
import io

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'image_processor.settings')

application = get_wsgi_application()

from typing import Annotated
from fastapi import FastAPI, File, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.wsgi import WSGIMiddleware
from resizer.models import Picture
from fastapi.responses import HTMLResponse
import boto3

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'image_processor.settings')
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

application = get_wsgi_application()

session = boto3.session.Session()
s3 = session.client(
    service_name='s3',
    endpoint_url='https://storage.yandexcloud.net'
)

app = FastAPI()

jpeg = '.jpeg'
list_format = [("original", None), ("thumb", (150, 120)), ("big_thumb", (700, 700)),
               ("big_1920", (1920, 1080)), ("d2500", (2500, 2500))]

app.mount('/static',
          StaticFiles(
              directory=os.path.normpath(
                  os.path.join(find_spec('django.contrib.admin').origin, '..', 'static')
              )
          ),
          name='static',
          )

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input name="project_id" type="text" id="messageText" autocomplete="off"/>
            <input name="files" type="file" multiple id="fileBinary">
            <input type="submit">
        </form>
        <form action="/file/download/" enctype="multipart/form-data" method="get">
        <dev>
        Получение списка картинок из хранилища
        </dev><br>
        <input name="project_id" type="text">
        <input type="submit">
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("fileBinary")
                var input_path = document.getElementById("messageText")
                reader = new FileReader();
                rawData = new ArrayBuffer();
                const textEncoder = new TextEncoder();
                const uint8Array = textEncoder.encode(input_path.value);
                ws.send(uint8Array)
                reader.onload = function(evt) {
                    rawData = evt.target.result;
                    ws.send(rawData);
                 }

                reader.readAsArrayBuffer(input.files[0]);

                input.value = ''
                input_path.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""


@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    image = None
    path = None
    while True:
        data = await websocket.receive_bytes()
        try:
            Image.open(io.BytesIO(data))
            image = data
        except:
            path = str(data)[2:-1]
        if image and path:
            json = await create_file(path, image)
            await websocket.send_json(json)
            picture = await put_file_to_db(int(path), image)
            await websocket.send_text("Put file in database - done")
            await websocket.send_text("Put file in s3 storage")
            await check_path_picture(picture)
            await websocket.send_text("Put file in s3 storage - done")


async def check_path_picture(inst_photo):
    path = f'{inst_photo["project_id"]}/{inst_photo["id"]}/'
    photo = inst_photo["picture_data"]
    state = inst_photo["state"]
    image = Image.open(io.BytesIO(photo))
    views = dict()
    views.setdefault("picture_data", {})
    for picture in list_format:
        new_path = path + picture[0] + jpeg
        views["picture_data"].setdefault(picture[0], '')
        if state == 1:
            if picture[1]:
                save_picture(to_byte_array(image.resize(picture[1])), new_path)
                if photo["state"] == 1:
                    photo.update(state=2)
            else:
                save_picture(to_byte_array(image), new_path)
        views["picture_data"][picture[0]] = \
            f'<a href="https://storage.yandexcloud.net/test-bucket-default/{new_path}"> click here to download</a>'
    image.close()
    return views


@app.get("/file/download")
def download_file(project_id: str):
    picture = Picture.objects.filter(project_id=int(project_id)).values("id", "state", "project_id", "picture_data")
    for photo in picture:
        photo["picture_data"] = await check_path_picture(photo)
    return HTMLResponse(json2html.convert(json={"images": [data for data in picture]}, escape=False))


@app.post("/files/")
async def create_file(project_id: str, file: Annotated[bytes, File()]):
    await put_file_to_db(int(project_id), file)
    return {"upload_link": f'https://storage.yandexcloud.net/test-bucket-default/', "params": {}}


async def put_file_to_db(project_id: int, file: bytes):
    picture = Picture(picture_name=list_format[0],
                      project_id=int(project_id),
                      state=1,
                      picture_data=file)
    picture.save()
    picture = \
        Picture.objects.filter(project_id=int(project_id)).values("id", "state", "project_id", "picture_data").order_by(
            '-id')[1]
    return picture


def to_byte_array(image):
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format=image.format)
    img_byte_arr = img_byte_arr.getvalue()
    return img_byte_arr


def save_picture(body, key):
    s3.put_object(Bucket='test-bucket-default', Key=key, Body=body)


app.mount('/django-test', WSGIMiddleware(application))
