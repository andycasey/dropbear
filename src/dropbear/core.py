__all__ = ["cli"]

import asyncio
from operator import itemgetter

import ads
import aiohttp
import click

from .search_utils import AuthorNetwork


async def run_search(author, number):
    authors = {}
    token = ads.base.BaseQuery().token
    async with aiohttp.ClientSession(
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    ) as session:
        network = AuthorNetwork(session)
        await network.init_cache()
        async for suggestion in network.suggest_authors(
            author, similarity_search_on_author_indices=[0]
        ):
            authors[suggestion["unique_name_descriptor"]] = suggestion

    for author in sorted(
        authors.values(), key=itemgetter("number_of_articles"), reverse=True
    )[:number]:
        print(author["full_name"], author["number_of_articles"])


@click.command()
@click.argument("author", nargs=-1)
@click.option(
    "--number",
    "-n",
    type=int,
    default=10,
    help="the number of matches to return",
)
def cli(author, number):
    """
    Find similar authors for a list of author names
    """
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_search(author, number))
