# import initialization

import time
import logging
import os
import sys
import threading
import requests

from configparser import ConfigParser
from kolibri.utils.cli import main

import django
django.setup()
from kolibri.core.content.utils.channels import get_channels_for_data_folder
from kolibri.core.content.utils.paths import get_channel_lookup_url

from bs4 import BeautifulSoup
from config import SYNC_CONFIG_FILENAME, FACILITY_ID, GRADE, DEFAULT_SYNC_SERVER, DEFAULT_CONFIG_DIR

kolibri_home = os.environ.get('KOLIBRI_HOME')


def update_progress_message(current_status):
    
    loader_page = os.path.abspath(os.path.join("assets", "_load.html"))
    # load the file
    with open(loader_page) as inf:
        txt = inf.read()
        soup = BeautifulSoup(txt, 'html.parser')

    status_tag =  soup.find(id = 'importstatus')
    status_tag.string.replace_with(current_status)
    
    # save the file again
    with open(loader_page, 'w') as outf:
        outf.write(str(soup))
        
def get_sync_config_file_location(sync_config_filename):
    syncini_file = os.path.join(kolibri_home, sync_config_filename)
    return syncini_file

def fetch_remote_sync_file(sync_config_filename, facility_id, sync_server, config_dir):
    url = 'http://'+ sync_server + '/' + config_dir + '/' + facility_id + '/' + sync_config_filename
    r = requests.get(url, allow_redirects=True)

    # write the newly fetched config file
    syncini_file = get_sync_config_file_location(sync_config_filename)
    open(syncini_file, 'wb').write(r.content)

    return syncini_file

def fetch_sync_config_file(sync_config_filename, facility_id, sync_server = DEFAULT_SYNC_SERVER, config_dir = DEFAULT_CONFIG_DIR):
    try:
        return fetch_remote_sync_file(sync_config_filename, facility_id, sync_server, config_dir)
    except requests.exceptions.RequestException:
        # Need to inform the user to connect the device to the Internet
        update_progress_message('Connect the device to the internet for initial setup. Trying again in 15 seconds.')
        time.sleep(15)
        return fetch_sync_config_file(sync_config_filename, facility_id, sync_server, config_dir)

def update_sync_config_file(sync_config_filename, facility_id, sync_server, config_dir):
    try:
        return fetch_remote_sync_file(sync_config_filename, facility_id, sync_server, config_dir)
    except requests.exceptions.RequestException:
        return get_sync_config_file_location(sync_config_filename)

def get_sync_params(syncini_file, grade):
    configur = ConfigParser()

    try:
        file = open(syncini_file, 'r')
    except FileNotFoundError:
        logging.info('Facility sync file not available.')

    configur.read(syncini_file)
    sync_params = {}
    sync_params['sync_on'] = configur.getboolean('DEFAULT', 'SYNC_ON')
    sync_params['sync_delay'] = configur.getfloat('DEFAULT', 'SYNC_DELAY')
    sync_params['sync_server'] = configur.get('DEFAULT', 'SYNC_SERVER')
    sync_params['content_server'] = 'http://' + configur.get('DEFAULT', 'SYNC_CONTENT_SERVER', fallback='studio.learningequality.org')
    sync_params['config_dir'] = configur.get('DEFAULT', 'SYNC_CONFIG_DIR')
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

def import_channel(channel_id, content_server):
    pid = os.fork()
    if pid == 0:
        update_progress_message("Intial setup - Importing content channel...")
        main(["manage", "importchannel", "network", channel_id, "--baseurl", content_server])
    else:
        os.waitpid(pid, 0)
        update_progress_message("Importing content channel - Completed.")

def import_content(channel_id, content_node, content_server):
    pid = os.fork()
    if pid == 0:
        update_progress_message("Initial setup - Importing learning resources...")
        main(["manage", "importcontent", "--node_ids", content_node, "network", channel_id, "--baseurl", content_server])
    else:
        os.waitpid(pid, 0)
        update_progress_message("Partial resources imported. Rest shall be imported in the background whenever internet is connected.")
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

def delete_channel(channel_id):
    pid = os.fork()
    if pid == 0:
        main(["manage", "deletechannel", "network", channel_id])
    else:
        os.waitpid(pid, 0)

def import_resources(default_sync_params):
    config_channel_id = default_sync_params['channel']
    content_server = default_sync_params['content_server']

    # Get info of channel on device
    device_channel_list = get_channels_for_data_folder(kolibri_home)
    if device_channel_list:
        device_channel = device_channel_list[0]
        device_channel_id = device_channel['id']
        device_channel_version = device_channel['version']

        # Is the channel on device the same as that in sync config
        if (device_channel_id == config_channel_id):
            resp = requests.get(get_channel_lookup_url(identifier = device_channel_id, baseurl = content_server))
            (remote_channel_info,) =  resp.json()
            remote_channel_version = remote_channel_info.get("version")
            # Update the existing channel
            if (device_channel_version < remote_channel_version):
                import_channel(device_channel_id, content_server)
        else:
            # Replace old channel with new configured channel
            import_channel(config_channel_id, content_server)
            delete_channel(device_channel_id)
            device_channel_id = config_channel_id
    else:
        device_channel_id = config_channel_id
        import_channel(device_channel_id, content_server)

    config_content_nodes = default_sync_params['node_list']
    # Channel import fetches updated channel data when available, hence must be tried everytime
    for content_node in config_content_nodes.split(','):
        import_content(device_channel_id, content_node, content_server)
    update_progress_message('...')

# MSS Cloud sync on user device
def run_sync():
    sync_config_filename = SYNC_CONFIG_FILENAME
    facility_id = FACILITY_ID
    grade = GRADE
    sync_server = DEFAULT_SYNC_SERVER
    config_dir = DEFAULT_CONFIG_DIR
    configur = ConfigParser()
    update_progress_message('...')
    try:
        syncini_file = get_sync_config_file_location(sync_config_filename)
        file = open(syncini_file, 'r')

    except FileNotFoundError:
        syncini_file = fetch_sync_config_file(sync_config_filename, facility_id)
        default_sync_params = get_sync_params(syncini_file, grade)

        from django.core.management import execute_from_command_line
        sys.__stdout__ = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        execute_from_command_line(sys.argv)
        sys.stdout = sys.__stdout__

        try:
            import_facility(default_sync_params, facility_id)
        except requests.exceptions.HTTPError: # raised when unable to connect due to morango certificate unavailability/mismatch due to admin credential change
            # refetch and try to handle credentials change case
            syncini_file = fetch_sync_config_file(sync_config_filename, facility_id)
            default_sync_params = get_sync_params(syncini_file, grade)
            import_facility(default_sync_params, facility_id)

        import_resources(default_sync_params)
        time.sleep(default_sync_params['sync_delay'])
        run_sync()

    default_sync_params = get_sync_params(syncini_file, grade)
    threading.Timer(default_sync_params['sync_delay'], run_sync).start()

    from django.core.management import execute_from_command_line
    sys.__stdout__ = sys.stdout
    sys.stdout = open(os.devnull, 'w')
    execute_from_command_line(sys.argv)
    sys.stdout = sys.__stdout__

    # Try to fetch an updated config file if online else continue with existing file.
    sync_server = default_sync_params['sync_server']
    config_dir = default_sync_params['config_dir']
    syncini_file = update_sync_config_file(sync_config_filename, facility_id, sync_server, config_dir)
    default_sync_params = get_sync_params(syncini_file, grade)
    if (default_sync_params['sync_on']):
        facility_sync(default_sync_params['sync_server'], facility_id)      
        try:
            import_resources(default_sync_params)
        except requests.exceptions.HTTPError:
            logging.info('Will attempt again when connection to server is available')
run_sync()