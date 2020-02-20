from aiohttp import web
import jinja2
import aiohttp_jinja2

import search_utils

async def stream(request):
    response = web.StreamResponse(
        status=200, reason="OK", headers={"Content-Type": "text/plain"},
    )
    await response.prepare(request)

    for i in range(5000):
        await response.write("{0}\n".format(i).encode("utf-8"))
    
    #author_names = ("Foreman-Mackey, D", "Casey, A")
    #async for suggestion in search_utils.suggest_authors(author_names):
    #    await response.write(f"{suggestion}".encode("utf-8"))

    await response.write_eof()
    return response


@aiohttp_jinja2.template("index.html")
async def index(request):
    return {}


app = web.Application()
app.add_routes([web.get("/", index)])
app.add_routes([web.get("/stream", stream)])

aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("./templates"))

web.run_app(app)
