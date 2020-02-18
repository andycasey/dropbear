from collections import OrderedDict
import ads


def parse_name(author_name):
    """
    Parse attributes of an author's name.

    :param author_name:
        The name as given, which could be a number of different formats.

    :returns:
        A dictionary of parsed attributes.
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
    first_name = given_names.split(" ")[0]
    full_name = f"{first_name} {last_name}"

    # Check if it's a suffix or an actual name
    # if re.search("([A-Z]\. ?)+", given_names):
    only_initials = len(given_names.replace(".", "").replace(" ", "")) <= 2
    is_collaboration = (
        "collaboration" in last_name.lower()
        or "survey" in last_name.lower()
        or "university" in last_name.lower()
    )

    has_full_name = not any([is_collaboration, only_initials])

    return OrderedDict(
        [
            ("first_name", first_name),
            ("last_name", last_name),
            ("given_names", given_names),
            ("suffix", suffix),
            ("full_name", full_name),
            ("has_full_name", has_full_name),
            ("only_initials", only_initials),
            ("is_collaboration", is_collaboration),
        ]
    )


def name_generator(author_name, **kwargs):
    """
    Return a generator that yields author names (and associated information) based
    on a network search of the author name that was given.

    :param author_name:
        The name of the author to search on.
    """

    # Some magic things first before we figure out how to set these.
    rows = 20
    max_pages = 5

    # Parse the input name
    parsed_author_name = parse_name(author_name)

    search_kwds = dict(
        q=f'author:"{author_name}"',
        rows=rows,
        start=0,
        max_pages=max_pages,
        fl=["id", "author", "bibcode", "year", "aff"],
    )

    # We want the generator to start yielding results back quickly.
    bibcodes = []
    first_author_bibcodes = []

    for j, article in enumerate(ads.SearchQuery(**search_kwds)):

        suggestion = dict(
            id=article.id, year=article.year, bibcode=article.bibcode
        )
        bibcodes.append(article.bibcode)

        for k, (author, aff) in enumerate(zip(article.author, article.aff)):
            suggestion.update(author=author, aff=aff)
            yield suggestion

            # Does the first author match our author name?
            # TODO: Just checking by last name here. Consider doing things betterer.
            if (
                not k
                and parsed_author_name["last_name"]
                == parse_name(author)["last_name"]
            ):
                first_author_bibcodes.append(article.bibcode)

    # Now let's do a similarity search on the first author bibcodes.

    raise StopIteration(f"that's all I got (from {j+1} articles)!")


def bulk_similarity_search(
    bibcodes, batch_size=20, rows=20, max_pages=5, **kwargs
):
    """
    Search for articles that are similar to the bibcodes provided.
    """
    bibcodes = list(set(bibcodes))
    search_kwds = dict(rows=rows)


if __name__ == "__main__":

    default_name = "Foreman-Mackey, Dan"
    author_name = input(f"Author name? (default: {default_name})\n")

    if not len(author_name.strip()):
        author_name = default_name

    print(f"Searching '{author_name}'")

    for i, suggestion in enumerate(name_generator(author_name)):
        print(i, suggestion)

