import asyncio
import aiohttp
import warnings
import logging
import json
import time
from aiohttp import web
from fuzzywuzzy import fuzz

import ads
import gender_guesser.detector as gender

__gender_detector = gender.Detector()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def _search(session, **params):
    logger.debug(f"Searching {params}")
    async with session.get(
        "https://api.adsabs.harvard.edu/v1/search/query", params=params
    ) as response:
        try:
            # TODO: I'm not sure if we should be awaiting here..
            content = await response.json()
        except:
            if response.status != 200:
                # TODO: Error handling!
                logger.exception("Exception occurred when ")
                return None

    logger.debug(
        f"Found {content['response']['numFound']} articles from {params}"
    )
    return content


def unique_name_descriptor(author_name):
    """
    Return a pseudo-unique name descriptor for the given author name. In other words, parse the given author name and
    return it in the form "Lastname, F.".

    :param author_name:
        The name as given, which could be a number of different formats.
    """

    parsed = parse_author_name(author_name)
    last_name, given_names = (parsed["last_name"], parsed["given_names"])
    given_initial = given_names[:1]
    return f"{last_name}, {given_initial}."


def parse_author_name(author_name):
    """
    Return a dictionary of parsed attributes of an author's name, regardless of the input format.

    :param author_name:
        The name as given, which could be a number of different formats.
    """

    logger.debug(f"Parsing author name '{author_name}'")

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

    first_name = given_names.split(" ")[0].replace(".", "")
    initial_only = len(first_name) == 1

    return dict(
        last_name=last_name,
        given_names=given_names,
        first_name=None if initial_only else first_name,
        initial_only=initial_only,
    )


def similar_author_names_on_author_indices(
    article, given_names, author_indices
):
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


async def network_search(
    session,
    author_names,
    max_initial_rows=500,
    similarity_search_on_author_indices=None,
    **kwargs,
):
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

    if isinstance(author_names, (str,)):
        warnings.warn(
            "author_names should be a list-like object. Assuming single author name given; converting to tuple."
        )
        author_names = (author_names,)

    if isinstance(similarity_search_on_author_indices, int):
        warnings.warn(
            "similarity_search_on_author_indices should be a list-like of integers"
        )
        similarity_search_on_author_indices = (
            similarity_search_on_author_indices,
        )

    # Some tings.
    rows = kwargs.pop("rows", 20)  # number of rows to retrieve per page
    similarity_rows = kwargs.pop(
        "similarity_rows", 5
    )  # number of rows to retrieve per similarity search

    fields = kwargs.pop(
        "fields",
        ["id", "author", "bibcode", "year", "aff", "orcid", "pubdate"],
    )
    max_pages = 1 + int(max_initial_rows / rows)
    fl = ",".join(fields)

    # For our similarity searches (if we make any.)
    similarity_args = (author_names, similarity_search_on_author_indices)
    similarity_search_kwds = dict(
        fl=fl, start=0, rows=similarity_rows, sort="score desc"
    )

    # Let's do an initial search based on the author's name.
    assert '"' not in "".join(
        author_names
    ), 'You\'re going to have a "bad" "time".'
    params = dict(
        q=" OR ".join(
            [f'author:"{author_name}"' for author_name in author_names]
        ),
        fl=fl,
        rows=rows,
        max_pages=max_pages,
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
        if (
            similar_author_names_on_author_indices(article, *similarity_args)
            and article["bibcode"] not in bibcodes_searched_for_similarity
        ):
            bibcodes_searched_for_similarity.add(article["bibcode"])
            awaitables.append(
                _search(
                    session,
                    q=f"similar({article['bibcode']})",
                    **similarity_search_kwds,
                )
            )
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
                    if (
                        similar_author_names_on_author_indices(
                            article, *similarity_args
                        )
                        and article["bibcode"]
                        not in bibcodes_searched_for_similarity
                    ):
                        bibcodes_searched_for_similarity.add(
                            article["bibcode"]
                        )
                        awaitables.insert(
                            0,
                            _search(
                                session,
                                q=f"similar({article['bibcode']})",
                                **similarity_search_kwds,
                            ),
                        )
                    yield article

        if done:
            break


async def suggest_authors(
    author_names,
    max_initial_rows=500,
    similar_author_names_on_author_indices=None,
    session=None,
    affiliation_uniqueness_ratio=75,
    **kwargs,
):
    """
    Perform a network search of NASA/ADS, given some author name(s), and return a generator that will yield suggestions
    of alternative author names, and associated metrics.

    Each execution of the generator will yield a dictionary containing one author suggestion, with relevant metadata.
    If an author is found on multiple articles then that author may be suggested multiple times by the generator, but
    successive dictionaries for that author will contain updated information about that author (e.g., matched bibcodes,
    affiliations, et cetera).

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

    :param session: [optional]
        A `aiohttp.ClientSession` asynchronous object that is already authenticated to execute queries through the
        NASA/ADS API. If `None` is provided then a `aiohttp.ClientSession` will be created for this search.

    :param affiliation_uniqueness_ratio: [optional]
        The ratio (between 0 and 100) of two affiliation strings in order for them to be considered as the same
        affiliation, based on the Levenshtein distance between two affiliation strings. Default is 75.

    :returns:
        A generator that will yield a suggested author name (and relevant metadata), based on the input author names.
    """

    kwds = dict(
        author_names=author_names,
        max_initial_rows=max_initial_rows,
        similar_author_names_on_author_indices=similar_author_names_on_author_indices,
    )
    kwds.update(kwargs)

    if session is None:
        # TODO: Overkill!
        token = ads.base.BaseQuery().token
        async with aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        ) as session:

            async for suggestion in collate_authors(
                network_search(session, **kwds),
                affiliation_uniqueness_ratio=affiliation_uniqueness_ratio,
            ):
                yield suggestion

    else:
        async for suggestion in collate_authors(
            network_search(session, **kwds),
            affiliation_uniqueness_ratio=affiliation_uniqueness_ratio,
        ):
            yield suggestion


def speculate_gender_expression(first_name):
    """
    Speculate on the gender of a person, given their first name.

    :param first_name:
        The first name of a person.

    :returns:
        The result will be one of unknown (name not found), andy (androgynous), male, female, mostly_male, or
        mostly_female. The difference between andy and unknown is that the former is found to have the same probability
        to be male than to be female, while the later means that the name wasn’t found in the training set.
    """
    xyz = __gender_detector.get_gender(first_name)
    return xyz


async def collate_authors(articles, affiliation_uniqueness_ratio):
    """
    Returns a generator that constantly yields summary statistics on the given articles. This function will take the
    `articles` generator and provide name suggestions and associated metrics.

    :param articles:
        An iterable that yields articles.

    :param affiliation_uniqueness_ratio:
        The ratio (between 0 and 100) of two affiliation strings in order for them to be considered as the same
        affiliation, based on the Levenshtein distance between two affiliation strings.

    :returns:
        A generator that will constantly yield name suggestions.
    """

    suggestions = dict()
    ignore_affiliations = set({"", "-"})

    pd_format = "%Y-%m-%d"
    _affiliation_split_str = " ; "  # because &amp; exists.
    _fix_month = lambda s: s.replace("-00-", "-01-")
    _fix_pubdate = lambda s: _fix_month(
        f"{s[:-1]}1" if s.endswith("-00") else s
    )

    async for article in articles:
        for j, (author, aff) in enumerate(
            zip(article["author"], article["aff"])
        ):

            key = unique_name_descriptor(author)

            suggestions.setdefault(
                key,
                dict(
                    full_name=None,
                    unique_name_descriptor=key,
                    orcid=None,
                    most_recent_primary_affiliation=None,
                    most_recent_pubdate=None,
                    bibcodes=[],
                    affiliations=set(),
                    parsed_affiliations=set(),
                    matched_names=set(),
                    number_of_articles_as_first_author=0,
                    number_of_articles=0,
                    article_years=[],
                    inferred_gender="unknown",
                ),
            )

            # Add bibcode and year.
            suggestions[key]["bibcodes"].append(article["bibcode"])
            suggestions[key]["article_years"].append(int(article["year"]))

            # Update names.
            # TODO: Parse the name instead?
            suggestions[key]["matched_names"].add(author)

            previous_full_name = suggestions[key]["full_name"]
            suggestions[key]["full_name"] = max(
                suggestions[key]["matched_names"], key=len
            )

            # Infer gender expression.
            # TODO: Should we run gender detector on all matched names and take the most common?
            #       Right now if we searched for
            #           "Foreman-Mackey, Dan"
            #       and found a *single* article authored by
            #           "Foreman-Mackey, Danielle"
            #       then this would return female because Danielle is longer than Dan.
            if (
                previous_full_name is None
                or previous_full_name != suggestions[key]["full_name"]
            ) and suggestions[key]["inferred_gender"] == "unknown":
                # Name updated.
                parsed_name = parse_author_name(suggestions[key]["full_name"])
                if not parsed_name["initial_only"]:
                    suggestions[key][
                        "inferred_gender"
                    ] = speculate_gender_expression(parsed_name["first_name"])

            # Update affiliations.
            new_affiliations = set(
                map(str.strip, aff.split(_affiliation_split_str))
            )
            new_affiliations = new_affiliations.difference(
                ignore_affiliations
            ).difference(suggestions[key]["affiliations"])
            for new_affiliation in new_affiliations:
                for existing_affiliation in suggestions[key]["affiliations"]:
                    if (
                        fuzz.partial_ratio(
                            existing_affiliation, new_affiliation
                        )
                        >= affiliation_uniqueness_ratio
                    ):
                        break

                else:
                    # Add new parsed affiliation
                    suggestions[key]["parsed_affiliations"].add(
                        new_affiliation
                    )

            # Now add those new affiliations to the full list.
            suggestions[key]["affiliations"] |= new_affiliations

            # Update counts.
            suggestions[key]["number_of_articles"] += 1
            if not j:
                suggestions[key]["number_of_articles_as_first_author"] += 1

            article_pubdate = _fix_pubdate(article["pubdate"])
            most_recent_pubdate = suggestions[key]["most_recent_pubdate"]

            if most_recent_pubdate is None or time.strptime(
                article_pubdate, pd_format
            ) > time.strptime(most_recent_pubdate, pd_format):
                suggestions[key].update(
                    most_recent_pubdate=article_pubdate,
                    most_recent_primary_affiliation=aff.split(
                        _affiliation_split_str
                    )[0].strip(),
                )

            # ORCID not always returned by NASA/ADS, even if we ask nicely.
            try:
                orcid = article["orcid"][j]
            except KeyError:
                None
            else:
                if orcid not in ("-", "", "."):
                    assert (
                        suggestions[key]["orcid"] is None
                        or suggestions[key]["orcid"] == orcid
                    ), f"{author} has multiple orcids!"
                    suggestions[key]["orcid"] = orcid

            # TODO: Calculate other metrics for filtering/sorting.

            yield suggestions[key]
