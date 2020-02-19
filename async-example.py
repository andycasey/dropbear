import asyncio
import aiohttp
from itertools import chain

import ads

# TODO: Overkill!
ADS_TOKEN = ads.base.BaseQuery().token


'''
async def search_query(session, q, **kwargs):

    params = dict(
        q=q,
        fl=",".join(["id", "author", "bibcode", "year", "aff"]),
        start=0,
        rows=20,
    )

    while True:
        print(f"Searching {params}")

        async with session.get(
                'https://api.adsabs.harvard.edu/v1/search/query',
                params=params
            ) as response:

            content = await response.json()
            
            # parse response
            for article in content["response"]["docs"]:
                yield article
                        
        if params["start"] >= content["response"]["numFound"]:
            # Retrieved all articles.
            break

        # Update start value to retrieve new articles.
        params.update(
            start=params["start"] + params["rows"]
        )

'''
'''
async def search_query(session, q, start=0, rows=20, **kwargs):

    params = dict(
        q=q,
        fl=",".join(["id", "author", "bibcode", "year", "aff"]),
        start=start,
        rows=rows
    )

    print(f"Searching {params}")

    async with session.get(
            'https://api.adsabs.harvard.edu/v1/search/query',
            params=params
        ) as response:

        content = await response.json()

        # Immediately start looking for more articles.
        if content["response"]["numFound"] >= (params["start"] + params["rows"]):
            async for each in search_query(
                    session, 
                    q=q, 
                    rows=rows,
                    start=params["start"] + params["rows"]
                ):
                yield each
        
        # Yield responses
        for article in content["response"]["docs"]:
            yield article
'''

"""
async def _search_query(session, **params):
    print(f"Searching {params}")
    async with session.get(
            'https://api.adsabs.harvard.edu/v1/search/query',
            params=params
        ) as response:

        content = await response.json()
        
        # Yield responses
        for article in content["response"]["docs"]:
            yield article



async def search_query(session, q, start=0, rows=20, **kwargs):
    params = dict(
        q=q,
        fl=",".join(["id", "author", "bibcode", "year", "aff"]),
        start=start,
        rows=rows
    )

    print(f"Searching {params}")

    async with session.get(
            'https://api.adsabs.harvard.edu/v1/search/query',
            params=params
        ) as response:

        content = await response.json()
        raise a
        
        numFound = content["response"]["numFound"]
        if "__skip" not in kwargs:
            coroutines = [
                search_query(session, q, start=s, rows=rows, __skip=True) \
                    for s in range(rows, numFound, rows)
            ]
            #for each in asyncio.as_completed(coroutines):
            #    return await each
            return chain(*(await asyncio.gather(*coroutines)))

        return content["response"]["docs"]
        # Yield responses
        #for article in content["response"]["docs"]:
        #    yield article


async def _search_query(session, q, start, rows):
    params = dict(
        q=q,
        fl=",".join(["id", "author", "bibcode", "year", "aff"]),
        start=start,
        rows=rows
    )

    print(f"Searching {params}")

    async with session.get(
            'https://api.adsabs.harvard.edu/v1/search/query',
            params=params
        ) as response:

        content = await response.json()
    return content["response"]["docs"]


async def search_query(session, q, start=0, rows=20, max_rows=500, **kwargs):
    return chain(*(await asyncio.gather(*(
        _search_query(session, q, s, rows) for s in range(0, max_rows, rows)
    ))))
"""


async def _search(session, **params):
    print(f"Searching {params}")
    async with session.get(
            "https://api.adsabs.harvard.edu/v1/search/query",
            params=params) \
        as response:
        # TODO: I'm not sure if we should be awaiting here..
        content = await response.json()
    return content


async def network_search(session,
                         author_name, 
                         max_initial_rows=500, 
                         similarity_search_on_author_indices=None, 
                         **kwargs):

    rows = 20 # number of rows to retrieve per page
    max_pages = 1 + int(max_initial_rows / rows)
    fields = ["id", "author", "bibcode", "year", "aff"]

    # Let's do an initial search based on the author's name.
    params = dict(
        q=f"author:\"{author_name}\"",
        fl=",".join(fields),
        rows=rows,
        max_pages=max_pages
    )
    # We await here because we really need this content.
    content = await _search(session, start=0, **params)

    num_found = content["response"]["numFound"]

    # Start asynchronous queries for later pages.
    awaitables = []
    max_rows = min(num_found, max_initial_rows)
    for start in range(rows, max_rows, rows):
        awaitables.append(_search(session, start=start, **params))

    # Start streaming back the initial articles.
    for article in content["response"]["docs"]:
        yield article

    for coroutine in asyncio.as_completed(awaitables):
        next_content = await coroutine
        for article in next_content["response"]["docs"]:
            yield article





if __name__ == '__main__':

    from time import time

    """
    # ~10 seconds compared to 2.5 seconds (async) 
    # Not a completely fair comparison for various reasons but whatever.
    t_a = time()
    import ads
    bar = []
    for article in ads.SearchQuery(q="author:\"Casey, A\"", rows=20, max_pages=100,
                                   fl=["id", "author", "bibcode", "year", "aff"]):
        bar.append(article)
    print(time() - t_a)
    """

    async def main():
        t_a = time()
        async with aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {ADS_TOKEN}",
                "Content-Type": "application/json",
            }) as session:

            foo = []
            async for each in network_search(session, "Casey, A"):
                print(each)
                foo.append(each)

            print(len(foo))
            print(time() - t_a)


    event_loop = asyncio.get_event_loop()
    try:
        event_loop.run_until_complete(main())
    finally:
        event_loop.close()