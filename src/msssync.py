import initialization

import time
import logging
import os
import sys
import threading
import requests

from configparser import ConfigParser
from kolibri.utils.cli import main

from bs4 import BeautifulSoup

def update_progress_message(current_status):
    
    loader_page = os.path.abspath(os.path.join("assets", "_load.html"))
    # load the file
    with open(loader_page) as inf:
        txt = inf.read()
        soup = BeautifulSoup(txt, 'html.parser')

    status_tag =  soup.find(id = 'importstatus')
    status_tag.string.replace_with(current_status)
    
    # save the file again
    with open(loader_page, "w") as outf:
        outf.write(str(soup))
        
def get_sync_config_file_location(sync_config_filename):
    kolibri_home = os.environ.get("KOLIBRI_HOME")
    syncini_file = os.path.join(kolibri_home, sync_config_filename)
    return syncini_file

def fetch_remote_sync_file(sync_config_filename, facility_id):
    url = 'http://content.myscoolserver.in/configs/' + facility_id + '/' + sync_config_filename # TODO first check existence of a syncoptions.ini and URL therein else default to hardcoded one
    r = requests.get(url, allow_redirects=True)

    # write the newly fetched config file
    syncini_file = get_sync_config_file_location(sync_config_filename)
    open(syncini_file, 'wb').write(r.content)

    return syncini_file

def fetch_sync_config_file(sync_config_filename, facility_id):
    try:
        return fetch_remote_sync_file(sync_config_filename, facility_id)
    except RequestException:
        # Need to inform the user to connect the device to the Internet
        update_progress_message("Connect the device to the internet for initial setup.")
        return fetch_sync_config_file(sync_config_filename, facility_id)

def update_sync_config_file(sync_config_filename, facility_id):
    try:
        return fetch_remote_sync_file(sync_config_filename, facility_id)
    except RequestException:
        return get_sync_config_file_location(sync_config_filename)

def get_sync_params(syncini_file, grade):
    configur = ConfigParser()

    try:
        file = open(syncini_file, 'r')
    except FileNotFoundError:
        logging.info("Facility sync file not available")

    configur.read(syncini_file)
    sync_params = {}
    sync_params['sync_on'] = configur.getboolean('DEFAULT', 'SYNC_ON')
    sync_params['sync_delay'] = configur.getfloat('DEFAULT', 'SYNC_DELAY')
    sync_params['sync_server'] = configur.get('DEFAULT', 'SYNC_SERVER')
    sync_params['channel'] = configur.get('DEFAULT','CHANNEL')
    sync_params['node_list'] = configur.get('DEFAULT', grade + '_NODE_LIST')
    sync_params['sync_user'] = configur.get('DEFAULT', 'SYNC_ADMIN', fallback=None)
    sync_params['sync_password'] = configur.get('DEFAULT', 'SYNC_ADMIN_PASSWORD', fallback=None)
    # always cleanup admin credentials
    delete_import_credentials(syncini_file)

    return sync_params

def delete_import_credentials(syncini_file):
    configur = ConfigParser()

    try:
        file = open(syncini_file, 'r')
        configur.read(syncini_file)
        configur.remove_option('DEFAULT', 'SYNC_ADMIN')
        configur.remove_option('DEFAULT', 'SYNC_ADMIN_PASSWORD')
        with open(syncini_file,"w") as configfile:
            configur.write(configfile)
    except FileNotFoundError:
        logging.info("Facility sync file not available")

def import_facility(sync_params, facility_id):
    pid = os.fork()
    if pid == 0:
        update_progress_message("Initial setup - Importing institution data...")
        main(["manage", "sync", "--baseurl", sync_params['sync_server'], "--facility", facility_id, "--username", sync_params['sync_user'], "--password", sync_params['sync_password'], "--no-push", "--noninteractive"])
    else:
        os.waitpid(pid, 0)
        update_progress_message("Importing institution data - Completed.")

def import_channel(channel_id):
    pid = os.fork()
    if pid == 0:
        update_progress_message("Intial setup - Importing content channel...")
        main(["manage", "importchannel", "network", channel_id])
    else:
        os.waitpid(pid, 0)
        update_progress_message("Importing content channel - Completed.")

def import_content(channel_id, content_node):
    pid = os.fork()
    if pid == 0:
        update_progress_message("Initial setup - Importing learning resources...")
        main(["manage", "importcontent", "--node_ids", content_node, "network", channel_id])
    else:
        os.waitpid(pid, 0)
        update_progress_message("Partial resources imported. Learning can start. Remaining resources shall be imported in the background whenever internet is connected.")
        time.sleep(2)
        # Tagging for end of minimal import process completion
        update_progress_message("Let the learning begin...")
        # Giving enough time for parallel thread to proceed with application UI loading
        time.sleep(2)

def facility_sync(sync_server, facility_id):
    pid = os.fork()
    if pid == 0:
        main(["manage", "sync", "--baseurl", sync_server, "--facility", facility_id])
    else:
        os.waitpid(pid, 0)

def import_resources(default_sync_params):
    # Channel import fetches updted channel data when available, hence must be tried everytime
    import_channel(default_sync_params['channel'])
    for content_node in default_sync_params['node_list'].split(','):
        import_content(default_sync_params['channel'], content_node)   

# MSS Cloud sync for multifacilities on user device
def run_sync():
    logging.basicConfig(level=logging.INFO)
#    logging.disable(logging.INFO)
#    logging.disable(logging.WARNING)
    sync_config_filename = 'syncoptions.ini'
    facility_id = 'bd7acfae2045fa0c09289a2b456cf9ab' # TODO ideally should transfer it to config.py if hardcoded or take as input from user
    grade = 'TEN' # TODO  ideally should transfer it to config.py if hardcoded or take as input from user
    configur = ConfigParser()

    try:
        syncini_file = get_sync_config_file_location(sync_config_filename)
        file = open(syncini_file, 'r')

    except FileNotFoundError:

        if (facility_id):
            syncini_file = fetch_sync_config_file(sync_config_filename, facility_id)
            default_sync_params = get_sync_params(syncini_file, grade)

            from django.core.management import execute_from_command_line
            sys.__stdout__ = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            execute_from_command_line(sys.argv)
            sys.stdout = sys.__stdout__

            try:
                import_facility(default_sync_params, facility_id)
            except requests.exceptions.HTTPError: # raised when unable to connect due to morango certificate unavailability
                # refetch and try to handle credentials change case
                syncini_file = fetch_sync_config_file(sync_config_filename, facility_id)
                default_sync_params = get_sync_params(syncini_file, grade)
                import_facility(default_sync_params, facility_id)

            import_resources(default_sync_params)

        else: # handling the case of default app or where facility may have been deleted on server side
            configur['DEFAULT'] = { 'SYNC_ON': 'True',
                                    'SYNC_SERVER': 'content.myscoolserver.in',
                                    'SYNC_DELAY': '900.0'
                                    }
            with open(syncini_file, 'w') as config_file:
                configur.write(config_file)

    # Try to fetch an updated config file if online else continue with existing file
    syncini_file = update_sync_config_file(sync_config_filename, facility_id)
    default_sync_params = get_sync_params(syncini_file, grade)
    try:
        import_resources(default_sync_params)
    except requests.exceptions.HTTPError:
        logging.info('Will attempt again when connection to server is available')

    if (default_sync_params['sync_on']):
        threading.Timer(default_sync_params['sync_delay'], run_sync).start()
        
        from django.core.management import execute_from_command_line
        sys.__stdout__ = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        execute_from_command_line(sys.argv)
        sys.stdout = sys.__stdout__

        from kolibri.core.auth.models import Facility
        sync_facilities = Facility.objects.filter()
        sync_server = default_sync_params['sync_server']
        if sync_facilities:
            configur.read(syncini_file)
            for sync_facility in sync_facilities:
                sync_facility_id = sync_facility.id
                if sync_facility_id in configur:
                    sync_server = configur.get(sync_facility_id, 'SYNC_SERVER')
                facility_sync(sync_server, sync_facility_id)
