# -*- coding: utf-8 -*-

# standard imports
import json
import os
from threading import Lock

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.core_kit import Core  # core kit
    from plexhints.log_kit import Log  # log kit

# imports from Libraries\Shared
from requests.exceptions import ReadTimeout
from typing import Optional

# local imports
from constants import themerr_data_directory
import plex_api_helper


class MigrationHelper:
    """
    Helper class to perform migrations.

    Attributes
    ----------
    migration_status_file : str
        The path to the migration status file.
    migration_status_file_lock : Lock
        The lock for the migration status file.

    Methods
    -------
    _validate_migration_key(key, raise_exception=False)
        Validate the given migration key.
    get_migration_status(key)
        Get the migration status for the given key.
    set_migration_status(key)
        Update the migration status file.
    perform_migration(key)
        Perform the migration for the given key, if it has not already been performed.
    migrate_locked_themes()
        Unlock all locked themes.
    """
    # Define the migration keys as class attributes for dot notation access
    LOCKED_THEMES = 'locked_themes'

    def __init__(self):
        self.migration_status_file = os.path.join(themerr_data_directory, 'migration_status.json')
        self.migration_status_file_lock = Lock()

        # Map keys to their respective functions
        self.migration_functions = {
            self.LOCKED_THEMES: self.migrate_locked_themes,
        }

    def _validate_migration_key(self, key, raise_exception=False):
        # type: (str, bool) -> bool
        """
        Validate the given migration key.

        Ensure the given key has a corresponding class attribute and function.

        Parameters
        ----------
        key : str
            The key to validate.
        raise_exception : py:class:`bool`
            Whether to raise an exception if the key is invalid.

        Returns
        -------
        py:class:`bool`
            Whether the key is valid.

        Raises
        ------
        AttributeError
            If the key is invalid and raise_exception is True.
        """
        # Ensure the key is a class attribute
        upper_key = key.upper()
        if not hasattr(self, upper_key):
            Log.Error('{} key is not a class attribute'.format(upper_key))
            if raise_exception:
                raise AttributeError('{} key is not a class attribute'.format(upper_key))
            return False

        # ensure the class attribute value is the same and lowercase
        if getattr(self, upper_key) != key:
            Log.Error('{} key is not the same as the class attribute value'.format(key))
            if raise_exception:
                raise AttributeError('{} key is not the same as the class attribute value'.format(key))
            return False

        # Ensure the key has a corresponding function
        if not self.migration_functions.get(key):
            Log.Error('{} key does not have a corresponding function'.format(key))
            if raise_exception:
                raise AttributeError('{} key does not have a corresponding function'.format(key))
            return False

        # if we made it this far, the key is valid
        return True

    def get_migration_status(self, key):
        # type: (str) -> Optional[bool]
        """
        Get the migration status for the given key.

        Parameters
        ----------
        key : str
            The key to get the migration status for.

        Returns
        -------
        Optional[py:class:`bool`]
            The migration status for the given key, or None if the key is not found.

        Examples
        --------
        >>> MigrationHelper().get_migration_status(key=self.LOCKED_THEMES)
        True
        """
        # validate
        self._validate_migration_key(key=key, raise_exception=True)

        with self.migration_status_file_lock:
            if os.path.isfile(self.migration_status_file):
                migration_status = json.loads(
                    s=str(Core.storage.load(filename=self.migration_status_file, binary=False)))
            else:
                migration_status = {}

        return migration_status.get(key)

    def set_migration_status(self, key):
        # type: (str) -> None
        """
        Update the migration status file.

        Parameters
        ----------
        key : str
            The key to update in the migration status file.

        Examples
        --------
        >>> MigrationHelper().set_migration_status(key=self.LOCKED_THEMES)
        """
        # validate
        self._validate_migration_key(key=key, raise_exception=True)

        Log.Debug('Updating migration status file: {}'.format(key))
        with self.migration_status_file_lock:
            if os.path.isfile(self.migration_status_file):
                migration_status = json.loads(
                    s=str(Core.storage.load(filename=self.migration_status_file, binary=False)))
            else:
                migration_status = {}

            if not migration_status.get(key):
                migration_status[key] = True
                Core.storage.save(filename=self.migration_status_file, data=json.dumps(migration_status), binary=False)

    @staticmethod
    def migrate_locked_themes():
        """
        Unlock all locked themes.

        Prior to v0.3.0, themes uploaded by Themerr-plex were locked which leads to an issue in v0.3.0 and newer, since
        Themerr-plex will not update locked themes. Additionally, there was no way to know if a theme was added by
        Themerr-plex or not until v0.3.0, so this migration will unlock all themes.
        """
        plex = plex_api_helper.setup_plexapi()

        plex_library = plex.library

        sections = plex_library.sections()

        # never update this list, it needs to match what was available before v0.3.0
        contributes_to = (
            'tv.plex.agents.movie',
            'com.plexapp.agents.imdb',
            'com.plexapp.agents.themoviedb',
            'dev.lizardbyte.retroarcher-plex'
        )

        for section in sections:
            if section.agent not in contributes_to:
                continue  # skip items with unsupported metadata agents for < v0.3.0

            field = 'theme'

            # not sure if this unlocks themes for collections
            try:
                section.unlockAllField(field=field, libtype='movie')
            except ReadTimeout:
                # this may timeout, but no big deal, we can just unlock the items individually
                Log.Warn('ReadTimeout occurred while unlocking all themes for section: {}, will fallback to '
                         'individual item unlocking'.format(section.title))

            # get all the items in the section
            media_items = section.all()  # this is redundant, assuming unlockAllField() works on movies

            # collections were added in v0.3.0, but collect them as well for anyone who may have used a nightly build
            # get all collections in the section
            collections = section.collections()

            # combine the items and collections into one list
            # this is done so that we can process both items and collections in the same loop
            all_items = media_items + collections

            for item in all_items:
                if item.isLocked(field=field):
                    plex_api_helper.change_lock_status(item=item, field=field, lock=False)

    def perform_migration(self, key):
        # type: (str) -> None
        """
        Perform the migration for the given key, if it has not already been performed.

        Parameters
        ----------
        key : str
            The key to perform the migration for.

        Examples
        --------
        >>> MigrationHelper().perform_migration(key=MigrationHelper.LOCKED_THEMES)
        """
        # validate
        self._validate_migration_key(key=key, raise_exception=True)

        # check if the migration has already been performed
        migration_status = self.get_migration_status(key=key)
        if migration_status:
            Log.Debug('Skipping "{}" migration, already completed.'.format(key))
            return

        # Use the dictionary to find and call the corresponding function
        migration_function = self.migration_functions.get(key)
        migration_function()

        # update the migration status file
        self.set_migration_status(key)
