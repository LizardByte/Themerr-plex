# -*- coding: utf-8 -*-

# standard imports
import json
import os
import tarfile
import time
from threading import Lock
import zipfile

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.constant_kit import CACHE_1DAY  # constant kit
    from plexhints.core_kit import Core  # core kit
    from plexhints.parse_kit import JSON  # parse kit
    from plexhints.prefs_kit import Prefs  # prefs kit
    from plexhints.log_kit import Log  # log kit

# imports from Libraries\Shared
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from typing import Optional

# local imports
from constants import plugin_support_data_directory
from general_helper import is_user_in_eu
import platform_helper

driver_path = os.path.join(plugin_support_data_directory, 'selenium-drivers')
driver_versions_json_path = os.path.join(driver_path, 'installed_versions.json')
temp_path = os.path.join(plugin_support_data_directory, 'temp')

driver_versions_lock = Lock()

# variables
yt_cookies = dict()
yt_cookies_last_updated = 0


# get youtube cookies using selenium
def get_yt_cookies():
    # type: () -> Optional[dict]
    """
    Get YouTube cookies.

    Get the YouTube cookies using Selenium.

    Returns
    -------
    Optional[str]
        The YouTube cookies, or None if the cookies could not be retrieved.

    Examples
    --------
    >>> get_yt_cookies()
    ...
    """
    if not Prefs['bool_youtube_cookies']:
        Log.Debug('Using YouTube cookies is disabled in the plugin settings.')
        return None

    if Prefs['enum_browser_driver'] == 'None':
        Log.Warning('"Browser (driver) for web automations" is not set, please select a browser in the plugin settings.')
        return None

    global yt_cookies, yt_cookies_last_updated

    if time.time() - yt_cookies_last_updated < CACHE_1DAY:
        return yt_cookies

    driver = None
    driver_file = None
    options = None
    if Prefs['enum_browser_driver'] == 'Chrome':
        # setup chrome options
        options = webdriver.ChromeOptions()
        # https://github.com/GoogleChrome/chrome-launcher/blob/main/docs/chrome-flags-for-tools.md
        options.add_argument('--enable-automation')
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        if Prefs['bool_youtube_consent']:
            options.add_argument('--incognito')

        # setup chrome driver
        driver_file = os.path.join(plugin_support_data_directory, 'selenium-drivers', 'chromedriver')
    elif Prefs['enum_browser_driver'] == 'Firefox':
        # setup firefox options
        options = webdriver.FirefoxOptions()
        # https://wiki.mozilla.org/Firefox/CommandLineOptions
        options.add_argument("-headless")
        if Prefs['bool_youtube_consent']:
            options.add_argument('-private')

        # setup firefox driver
        driver_file = os.path.join(plugin_support_data_directory, 'selenium-drivers', 'geckodriver')

    if not os.path.isfile(driver_file):
        Log.Error('Failed to find driver at: {}'.format(driver_file))
        return None

    if Prefs['enum_browser_driver'] == 'Chrome':
        driver = webdriver.Chrome(executable_path=driver_file, options=options)
    elif Prefs['enum_browser_driver'] == 'Firefox':
        driver = webdriver.Firefox(executable_path=driver_file, options=options)

    # get the cookies
    try:
        driver.get('https://www.youtube.com')
        if Prefs['bool_youtube_consent'] and is_user_in_eu():
            consent_button_xpath = ('/html/body/ytd-app/ytd-consent-bump-v2-lightbox/tp-yt-paper-dialog/div[4]/div[2]/'
                                    'div[6]/div[1]/ytd-button-renderer[2]/yt-button-shape/button/div/span')
            WebDriverWait(driver=driver, timeout=10).until(
                webdriver.support.expected_conditions.presence_of_element_located((By.XPATH, consent_button_xpath))
            )

            # click the consent button
            consent_button = driver.find_element_by_xpath(consent_button_xpath)
            consent_button.click()
            time.sleep(10)
        # todo - this is a set of dictionaries (probably not the correct format)
        yt_cookies = driver.get_cookies()
        yt_cookies_last_updated = time.time()
    except Exception as e:
        Log.Exception('Failed to get YouTube cookies: {}'.format(e))
        return None
    finally:
        driver.quit()

    return yt_cookies


def install_chromedriver():
    # type: () -> None
    """Install chromedriver."""
    driver = 'chromedriver'
    Log.Info('Installing {}'.format(driver))

    # get the chromedriver version
    release_data = JSON.ObjectFromURL(
        url='https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json',
        errors='ignore'
    )
    version = release_data['channels']['stable']['version']

    if version == get_installed_version(driver=driver):
        Log.Debug('{} {} is already installed'.format(driver, version))
        return

    architectures = dict(
        darwin=dict(
            aarch64='mac-arm64',
            x86_64='mac-x64',
        ),
        linux=dict(
            x86_64='linux64',
        ),
        windows=dict(
            x86='win32',
            x86_64='win64',
        ),
    )

    release_platform = architectures[platform_helper.os_system][platform_helper.architecture]

    # download the release
    Log.Info('Downloading {} {}'.format(driver, version))
    for asset in release_data['channels']['stable']['downloads'][driver]:
        if asset['platform'] == release_platform:
            Log.Info('Downloading {}'.format(asset['name']))
            download_path = os.path.join(temp_path, asset['name'])
            with requests.get(asset['url'], stream=True) as r:
                f = open(download_path, 'wb')
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                f.close()

            # extract the release
            Log.Info('Extracting chromedriver {}'.format(version))
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall(driver_path)

            # delete the download
            os.remove(download_path)

            # make the driver executable
            if platform_helper.os_system != 'windows':
                os.chmod(os.path.join(driver_path, driver), 0o755)

            # update the installed versions json
            update_version_file(driver=driver, version=version)

            break


def install_geckodriver():
    # type: () -> None
    """Install geckodriver."""
    driver = 'geckodriver'
    Log.Info('Installing {}'.format(driver))

    # get the geckodriver version
    release_data = JSON.ObjectFromURL(
        url='https://api.github.com/repos/mozilla/geckodriver/releases/latest',
        errors='ignore'
    )
    version = release_data['tag_name']

    if version == get_installed_version(driver=driver):
        Log.Debug('{} {} is already installed'.format(driver, version))
        return

    architectures = dict(
        darwin=dict(
            aarch64='{}-{}-macos-aarch64.tar.gz'.format(driver, version),
            x86_64='{}-{}-macos.tar.gz'.format(driver, version),
        ),
        linux=dict(
            aarch64='{}-{}-Linux-aarch64.tar.gz'.format(driver, version),
            x86='{}-{}-Linux32.tar.gz'.format(driver, version),
            x86_64='{}-{}-Linux64.tar.gz'.format(driver, version),
        ),
        windows=dict(
            x86='{}-{}-win32.zip'.format(driver, version),
            x86_64='{}-{}-win64.zip'.format(driver, version),
        ),
    )

    release_file_name = architectures[platform_helper.os_system][platform_helper.architecture]

    # download the release
    Log.Info('Downloading {} {}'.format(driver, version))
    for asset in release_data['assets']:
        if asset['name'] == release_file_name:
            Log.Info('Downloading {}'.format(asset['name']))
            download_path = os.path.join(temp_path, asset['name'])
            with requests.get(asset['browser_download_url'], stream=True) as r:
                f = open(download_path, 'wb')
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                f.close()

            # extract the release
            Log.Info('Extracting geckodriver {}'.format(version))
            if platform_helper.os_system == 'windows':
                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(driver_path)
            else:
                with tarfile.open(download_path, 'r:gz') as tar_ref:
                    tar_ref.extractall(driver_path)

            # delete the download
            os.remove(download_path)

            # make the driver executable
            if platform_helper.os_system != 'windows':
                os.chmod(os.path.join(driver_path, driver), 0o755)

            # update the installed versions json
            update_version_file(driver=driver, version=version)

            break


def get_installed_version(driver):
    # type: (str) -> Optional[str]
    """
    Get the installed version of the specified driver.
    """
    with driver_versions_lock:
        if os.path.isfile(driver_versions_json_path):
            data = json.loads(s=str(Core.storage.load(filename=driver_versions_json_path, binary=False)))
        else:
            data = dict()
        return data.get(driver)


def update_version_file(driver, version):
    # type: (str, str) -> None
    """
    Update the installed versions json file.
    """
    with driver_versions_lock:
        if os.path.isfile(driver_versions_json_path):
            data = json.loads(s=str(Core.storage.load(filename=driver_versions_json_path, binary=False)))
        else:
            data = dict()
        data[driver] = version
        Core.storage.save(filename=driver_versions_json_path, data=json.dumps(data), binary=False)


def install_driver():
    # type: () -> None
    """
    Install the driver.
    """
    try:
        browser_map[Prefs['enum_browser_driver']]()
    except KeyError:
        Log.Warning(
            '"Browser (driver) for web automations" is not set, please select a browser in the plugin settings.')


browser_map = dict(
    Chrome=install_chromedriver,
    Firefox=install_geckodriver,
)
