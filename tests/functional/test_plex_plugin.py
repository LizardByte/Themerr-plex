# -*- coding: utf-8 -*-
# standard imports
import os


def _check_themes(movies):
    # ensure all movies have themes
    for item in movies.all():
        print(item.title)
        assert item.theme, "No theme found for {}".format(item.title)


def test_plugin_los(plugin_logs):
    print('plugin_logs: {}'.format(plugin_logs))
    assert plugin_logs, "No plugin logs found"


def test_plugin_log_file(plugin_log_file):
    assert os.path.isfile(plugin_log_file), "Plugin log file not found: {}".format(plugin_log_file)


def test_plugin_log_file_exceptions(plugin_log_file):
    # get all the lines in the plugin log file
    with open(plugin_log_file, 'r') as f:
        lines = f.readlines()

    critical_exceptions = []
    for line in lines:
        if ') :  CRITICAL (' in line:
            critical_exceptions.append(line)

    assert len(critical_exceptions) <= 1, "Too many exceptions logged to plugin log file"

    for exception in critical_exceptions:
        # every plugin will have this exception
        assert exception.endswith('Exception getting hosted resource hashes (most recent call last):\n'), (
            "Unexpected exception: {}".format(exception))


def test_movies_new_agent(movies_new_agent):
    _check_themes(movies_new_agent)


def test_movies_imdb_agent(movies_imdb_agent):
    _check_themes(movies_imdb_agent)


def test_movies_themoviedb_agent(movies_themoviedb_agent):
    _check_themes(movies_themoviedb_agent)
