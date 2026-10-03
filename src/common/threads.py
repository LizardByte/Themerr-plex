"""
src/common/threads.py

Functions related to threading.

Routine Listings
----------------
run_in_thread : method
    Alias of the built in method `threading.Thread`.

Examples
--------
>>> from common import config, threads, tray_icon
>>> config_object = config.create_config(config_file='config.ini')
>>> tray_icon.icon = tray_icon.tray_initialize()
>>> threads.run_in_thread(target=tray_icon.tray_run, name='pystray', daemon=True).start()

>>> from common import config, threads, webapp
>>> config_object = config.create_config(config_file='config.ini')
>>> threads.run_in_thread(target=webapp.start_webapp, name='FastAPI', daemon=True).start()
INFO:     Uvicorn running on https://... (Press CTRL+C to quit)
"""
# standard imports
import threading

# Keep the standard Thread API so callers can configure and start their own workers.
run_in_thread = threading.Thread
