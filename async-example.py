import asyncio
import aiohttp
import warnings
import json
from aiohttp import web

import ads

# TODO: Overkill!
ADS_TOKEN = ads.base.BaseQuery().token



async def _search(session, **params):
    print(f"Searching {params}")
    async with session.get(
            "https://api.adsabs.harvard.edu/v1/search/query",
            params=params) \
        as response:
        try:
            # TODO: I'm not sure if we should be awaiting here..
            content = await response.json()
        except:
            if response.status != 200:
                # TODO: Error handling!
                return None

    print(f"Found {content['response']['numFound']} articles from {params}")
    return content


def unique_name_descriptor(author_name):
    """
    Return a pseudo-unique name descriptor for the given author name. In other words, parse the given author name and
    return it in the form "Lastname, F.".

    :param author_name:
        The name as given, which could be a number of different formats.
    """
    number_of_commas = author_name.count(",")
    suffix = None
    if number_of_commas == 0:
        *given_names, last_name = author_name.split(" ")
        given_names = " ".join(given_names)
    elif number_of_commas == 1:
        last_name, given_names = author_name.split(",")
    else:
        last_name, given_names, suffix = author_name.split(",")

    last_name = last_name.strip()
    given_names = given_names.strip()
    given_initial = given_names[:1]

    return f"{last_name}, {given_initial}."


def similar_author_names_on_author_indices(article, given_names, author_indices):
    if author_indices is None:
        return False

    # We must define what constitutes "similar" enough as an author name.
    # Here we will define "Lastname, F." as being sufficient.
    parsed_given_names = list(map(unique_name_descriptor, given_names))

    for index in author_indices:
        try:
            author = article["author"][index]

        except IndexError:
            continue
        
        else:
            parsed_author = unique_name_descriptor(author)

            if parsed_author in parsed_given_names:
                return True
    
    return False
            



async def network_search(session,
                         author_names, 
                         max_initial_rows=500, 
                         similarity_search_on_author_indices=None, 
                         **kwargs):
    """
    Returns a generator that yields articles found through a network search of NASA/ADS, given author names.

    :param session:
        A `aiohttp.ClientSession` to use for the search. The session is expected to already have the appropriate 
        NASA/ADS authentication headers.
    
    :param author_names:
        A list-like object containing names (as "Last, First I.") for the initial search.
    
    :param max_initial_rows: [optional]
        The maximum number of initial articles (rows) that will be retrieved for *each* entry in `author_names`. The 
        default is 500 rows (per entry in `author_names`). The total number of articles generated will be higher than 
        `len(author_names) * max_initial_rows` if a similarity search is also performed.

    :param similarity_search_on_author_indices: [optional]
        A list-like object containing the indices where a similarity search should be performed, if any of the
        `author_names` appear as one of these authored indices. For example, if `author_names = ("Snow, Mary", "Water, M.")`
        and `similarity_search_on_author_indices = (0, 3, 5)` then any time an article was found where _Mary Snow_ or 
        _M. Water_ appeared as the first, fourth, or sixth author (i.e., zero-indexed), then a similarity search would 
        be performed on that article, using the NASA/ADS "similar(bibcode)" functionality. 
        
        Set `similarity_search_on_author_indices = None` to prevent any similarity searches.
    """

    if isinstance(author_names, (str, )):
        warnings.warn("author_names should be a list-like object. Assuming single author name given; converting to tuple.")
        author_names = (author_names, )

    if isinstance(similarity_search_on_author_indices, int):
        warnings.warn("similarity_search_on_author_indices should be a list-like of integers")
        similarity_search_on_author_indices = (similarity_search_on_author_indices, )
    
    # Some tings.
    rows = kwargs.pop("rows", 20) # number of rows to retrieve per page
    similarity_rows = kwargs.pop("similarity_rows", 5) # number of rows to retrieve per similarity search

    fields = kwargs.pop("fields", ["id", "author", "bibcode", "year", "aff", "orcid"])
    max_pages = 1 + int(max_initial_rows / rows)
    fl = ",".join(fields)
    
    # For our similarity searches (if we make any.)
    similarity_args = (author_names, similarity_search_on_author_indices)
    similarity_search_kwds = dict(fl=fl, start=0, rows=similarity_rows, sort="score desc")

    # Let's do an initial search based on the author's name.
    assert '"' not in ''.join(author_names), "You're going to have a \"bad\" \"time\"."
    params = dict(
        q=" OR ".join([f"author:\"{author_name}\"" for author_name in author_names]),
        fl=fl,
        rows=rows,
        max_pages=max_pages
    )
    # We await here because we really need this content.
    content = await _search(session, start=0, **params)

    num_found = content["response"]["numFound"]

    # Start asynchronous queries for later pages.
    awaitables = []
    bibcodes_searched_for_similarity = set()

    max_rows = min(num_found, max_initial_rows)
    for start in range(rows, max_rows, rows):
        awaitables.append(_search(session, start=start, **params))

    # Start streaming back the initial articles.
    for article in content["response"]["docs"]:
        # If the article author matches our similarity author indices, add a coroutine to do a similarity search.
        if similar_author_names_on_author_indices(article, *similarity_args) \
        and article["bibcode"] not in bibcodes_searched_for_similarity:
            bibcodes_searched_for_similarity.add(article["bibcode"])
            awaitables.append(_search(session, q=f"similar({article['bibcode']})", **similarity_search_kwds))
        yield article

    # We use an outer loop here because we might add coroutines to `awaitables` while we are awaiting on those 
    # coroutines. In practice we are awaiting on results from future pages from ADS, and we may want to asynchronously 
    # do similarity searches on some of those articles that have been returned.
    
    # This is probably too hacky; there is probably a better way.
    while True:
        done = True
        for coroutine in asyncio.as_completed(awaitables):
            try:
                next_content = await coroutine

            except RuntimeError:
                # Already used this awaited coroutine.
                continue

            else:
                if next_content is None:
                    # TODO: Exception handling.
                    continue

                done = False
                for article in next_content["response"]["docs"]:
                    # If the article author matches our similarity author indices, add a coroutine to do a similarity search
                    if similar_author_names_on_author_indices(article, *similarity_args) \
                    and article["bibcode"] not in bibcodes_searched_for_similarity:
                        bibcodes_searched_for_similarity.add(article["bibcode"])
                        awaitables.insert(0, _search(session, q=f"similar({article['bibcode']})", **similarity_search_kwds))
                    yield article

        if done: break

    #raise StopIteration()
    #return None


async def author_suggestions(articles):
    """
    Returns a generator that constantly yields summary statistics on the given articles. This function will take the 
    `articles` generator and provide name suggestions and associated metrics.

    :param articles:
        An iterable that yields articles.

    :returns:
        A generator that will constantly yield name suggestions.
    """

    suggestions = dict()
    ignore_affiliations = set({'', '-'})

    async for article in articles:
        for j, (author, aff) in enumerate(zip(article["author"], article["aff"])):

            key = unique_name_descriptor(author)
            
            suggestions.setdefault(key, dict(
                full_name=None,
                orcid=None,
                bibcodes=[],
                affiliations=set(),
                matched_names=set(),
                number_as_first_author=0
                )
            )

            suggestions[key]["bibcodes"].append(article["bibcode"])
            suggestions[key]["matched_names"].add(author)
            suggestions[key]["affiliations"] |= set(map(str.strip, aff.split(";"))).difference(ignore_affiliations)
            
            # TODO: Parse the name instead of just taking the longest name (as these will have many formats)
            suggestions[key]["full_name"] = max(suggestions[key]["matched_names"], key=len)

            if not j:
                suggestions[key]["number_as_first_author"] += 1

            # ORCID not always returned by NASA/ADS, even if we ask nicely.
            try:
                orcid = article["orcid"][j]

            except KeyError:
                None
            
            else:
                if orcid not in ("-", ""):
                    assert suggestions[key]["orcid"] is None \
                        or suggestions[key]["orcid"] == orcid, f"{author} has multiple orcids!"
                    
                    suggestions[key]["orcid"] = orcid

            yield suggestions[key]





if __name__ == '__main__':

    """
    from time import time 
    async def main():
        t_a = time()
        async with aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {ADS_TOKEN}",
                "Content-Type": "application/json",
            }) as session:

            foo = []
            count = 0
            async for each in network_search(
                    session, 
                    ("Casey, A", ),
                    similarity_search_on_author_indices=(3, )
                ):
                #print(each)
                print(count, time() - t_a)
                foo.append(each)
                count += 1

            print(count)
            print(time() - t_a)
            raise a

    event_loop = asyncio.get_event_loop()
    try:
        event_loop.run_until_complete(main())
    finally:
        event_loop.close()
    """




    # Web stuff below.
    from time import time
    async def main():
        t_a = time()
        async with aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {ADS_TOKEN}",
                "Content-Type": "application/json",
            }) as session:

            args = (session, ("Casey, A"))

            count = 0
            async for suggestions in author_suggestions(network_search(*args)):
                print(time() - t_a, count, len(suggestions))
                count += 1

            print(time() - t_a, count)
            raise a

    event_loop = asyncio.get_event_loop()
    try:
        event_loop.run_until_complete(main())
    finally:
        event_loop.close()


    raise a


    async def single_author_handler(request):
        author_name = request.match_info["author_name"]
        
        async with aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {ADS_TOKEN}",
                "Content-Type": "application/json",
            }) as session:

            response = web.StreamResponse(
                status=200,
                reason="OK",
                headers={"Content-Type": "text/plain"}
            )

            await response.prepare(request)

            async for article in network_search(session, (author_name, )):
                await response.write(json.dumps(article).encode("utf-8"))

            await response.write_eof()

        return response


    async def hello(request):
        return web.Response(text="Hello, world")



    app = web.Application()
    app.add_routes([
        web.get("/", hello),
        web.get("/stream/{author_name}", single_author_handler)
    ])
    web.run_app(app)

    print("Ready?")