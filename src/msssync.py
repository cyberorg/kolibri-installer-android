import initialization

import time
import logging
import os
import sys
import threading
import requests

from configparser import ConfigParser
from kolibri.utils.cli import main

def get_sync_config_file_location(sync_config_filename):
    kolibri_home = os.environ.get("KOLIBRI_HOME")
    syncini_file = os.path.join(kolibri_home, sync_config_filename)
    return syncini_file

def fetch_remote_sync_file(sync_config_filename, facility_id):
    try:
        url = 'http://content.myscoolserver.in/configs/' + facility_id + '/' + sync_config_filename
        r = requests.get(url, allow_redirects=True)
        syncini_file = get_sync_config_file_location(sync_config_filename)
        open(syncini_file, 'wb').write(r.content)
        return syncini_file
    except RequestException:
        # Need to inform the user to connect the device to the Internet
        return fetch_remote_sync_file(sync_config_filename, facility_id)

def update_sync_config_file(sync_config_filename, facility_id):
    syncini_file = fetch_remote_sync_file(sync_config_filename, facility_id)
    delete_import_credentials(syncini_file)

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
        main(["manage", "sync", "--baseurl", sync_params['sync_server'], "--facility", facility_id, "--username", sync_params['sync_user'], "--password", sync_params['sync_password'], "--no-push", "--noninteractive"])
    else:
        os.waitpid(pid, 0)

def import_channel(channel_id):
    pid = os.fork()
    if pid == 0:
        main(["manage", "importchannel", "network", channel_id])
    else:
        os.waitpid(pid, 0)

def import_content(channel_id, content_node_list):
    content_nodes = content_node_list.split(',')
    for node in content_nodes:
        pid = os.fork()
        if pid == 0:
            main(["manage", "importcontent", "--node_ids", node, "--import_updates", "network", channel_id])
        else:
            os.waitpid(pid, 0)

def facility_sync(sync_server, facility_id):
    pid = os.fork()
    if pid == 0:
        main(["manage", "sync", "--baseurl", sync_server, "--facility", facility_id, "--verbosity", "3"])
    else:
        os.waitpid(pid, 0)

def import_resources(default_sync_params, import_channel):
    if (import_channel):
        import_channel(default_sync_params['channel'])
    import_content(default_sync_params['channel'], default_sync_params['node_list'])

# MSS Cloud sync for multifacilities on user device
def run_sync():
    logging.basicConfig(level=logging.INFO)
#    logging.disable(logging.INFO)
#    logging.disable(logging.WARNING)
    sync_config_filename = 'syncoptions.ini'
    facility_id = 'bd7acfae2045fa0c09289a2b456cf9ab' # ideally should transfer it to config.py if hardcoded or take as input from user
    grade = 'TEN'
    configur = ConfigParser()

    try:
        syncini_file = get_sync_config_file_location(sync_config_filename)
        file = open(syncini_file, 'r')

    except FileNotFoundError:

        if (facility_id):
            syncini_file = fetch_remote_sync_file(sync_config_filename, facility_id)
            default_sync_params = get_sync_params(syncini_file, grade)
            delete_import_credentials(syncini_file)

            from django.core.management import execute_from_command_line
            sys.__stdout__ = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            execute_from_command_line(sys.argv)
            sys.stdout = sys.__stdout__

            import_facility(default_sync_params, facility_id)
            import_resources(default_sync_params, import_channel=True)

        else: # handling the case of default app or where facility may have been deleted on server side
            configur['DEFAULT'] = { 'SYNC_ON': 'True',
                                    'SYNC_SERVER': 'content.myscoolserver.in',
                                    'SYNC_DELAY': '900.0'
                                    }
            with open(syncini_file, 'w') as config_file:
                configur.write(config_file)

    update_sync_config_file(sync_config_filename, facility_id)
    default_sync_params = get_sync_params(syncini_file, grade)
    import_resources(default_sync_params, import_channel=False)
    
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
