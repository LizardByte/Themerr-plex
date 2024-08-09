def _check_themes(items):
    # ensure all items have themes
    for item in items:
        print(item.title)
        assert item.theme, "No theme found for {}".format(item.title)


def test_items(section):
    items = section.all()
    _check_themes(items=items)
