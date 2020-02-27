import json

from aiohttp import web
import jinja2
import aiohttp_jinja2

import search_utils


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(sorted(iterable))
        return json.JSONEncoder.default(self, obj)


async def search(request):
    data = await request.json()

    response = web.StreamResponse(
        status=200, reason="OK", headers={"Content-Type": "text/plain"},
    )
    await response.prepare(request)

    author_names = data["name"].split(";")
    async for suggestion in search_utils.suggest_authors(author_names):
        await response.write(
            (json.dumps(suggestion, cls=CustomEncoder) + "\n").encode("utf-8")
        )

    await response.write_eof()
    return response


@aiohttp_jinja2.template("index.html")
async def index(request):
    return {}


app = web.Application()
app.add_routes(
    [
        web.get("/", index),
        web.post("/search", search),
        web.static("/static", "./front/static"),
    ]
)

aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("./front/templates"))

web.run_app(app)
