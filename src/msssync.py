import initialization

import time
import logging
import os
import sys
import threading
import requests

from configparser import ConfigParser
from kolibri.utils.cli import main

sync_config_filename = 'syncoptions.ini'

def get_sync_config_file_location():
    kolibri_home = os.environ.get("KOLIBRI_HOME")
    syncini_file = os.path.join(kolibri_home, sync_config_filename)
    return syncini_file

def fetch_remote_sync_file(facility_id):
    url = 'http://content.myscoolserver.in/configs/' + facility_id + '/' + sync_config_filename
    r = requests.get(url, allow_redirects=True)

    syncini_file = get_sync_config_file_location()

    open(syncini_file, 'wb').write(r.content)
    return syncini_file

def get_sync_params(syncini_file):
    configur = ConfigParser()

    try:
        file = open(syncini_file, 'r')
    except IOError:
        logging.info("Facility sync file not available")

    configur.read(syncini_file)
    syncparams = {}
    syncparams['syncserver'] = configur.get('DEFAULT', 'SYNC_SERVER')
    syncparams['syncuser'] = configur.get('DEFAULT', 'SYNC_ADMIN')
    syncparams['syncpassword'] = configur.get('DEFAULT', 'SYNC_ADMIN_PASSWORD')

    return syncparams

def do_sync(syncparams, facility_id):
    from django.core.management import execute_from_command_line
    sys.__stdout__ = sys.stdout
    sys.stdout = open(os.devnull, 'w')
    execute_from_command_line(sys.argv)
    sys.stdout = sys.__stdout__

    main(["manage", "sync", "--baseurl", syncparams['syncserver'], "--facility", facility_id, "--verbosity", "3", "--username", syncparams['syncuser'], "--password", syncparams['syncpassword'], "--no-push", "--noninteractive"])

def delete_import_credentials(syncini_file):
    configur = ConfigParser()

    try:
        file = open(syncini_file, 'r')
        configur.read(syncini_file)
        configur.remove_option('DEFAULT', 'SYNC_ADMIN')
        configur.remove_option('DEFAULT', 'SYNC_ADMIN_PASSWORD')
        with open(syncini_file,"w") as configfile:
            configur.write(configfile)
    except IOError:
        logging.info("Facility sync file not available")

def import_facility(facility_id):
    syncini_file = fetch_remote_sync_file(facility_id)
    syncparams = get_sync_params(syncini_file)
    delete_import_credentials(syncini_file)
    do_sync(syncparams, facility_id)

def import_content():
    pass

def facility_sync(syncserver, syncfacilityid):
    pid = os.fork()
    if pid == 0:
        main(["manage", "sync", "--baseurl", syncserver, "--facility", syncfacilityid, "--verbosity", "3"])
    else:
        os.waitpid(pid, 0)

# MSS Cloud sync for multifacilities on user device
def run_sync():
#    logging.basicConfig(level=logging.INFO)
#    logging.disable(logging.INFO)
#    logging.disable(logging.WARNING)

    configur = ConfigParser()

    try:
        syncini_file = get_sync_config_file_location()
        file = open(syncini_file, 'r')
    except IOError:

        facility_id = 'bd7acfae2045fa0c09289a2b456cf9ab' # ideally should transfer it to config.py if hardcoded or take as input from user
        
        if (facility_id):
            import_facility(facility_id)
        else: # handling the case of default app or where facility may have been deleted on server side
            configur['DEFAULT'] = { 'SYNC_ON': 'True',
                                'SYNC_SERVER': 'content.myscoolserver.in',
                                'SYNC_DELAY': '900.0'
                                }
            with open(syncini_file, 'w') as configfile:
                configur.write(configfile)

    configur.read(syncini_file)
    syncon = configur.getboolean('DEFAULT', 'SYNC_ON')
    syncdelay = configur.getfloat('DEFAULT', 'SYNC_DELAY')
    if (syncon):
        threading.Timer(syncdelay, run_sync).start()
        from django.core.management import execute_from_command_line
        sys.__stdout__ = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        execute_from_command_line(sys.argv)
        sys.stdout = sys.__stdout__
        from kolibri.core.auth.models import Facility
        syncfacilities = Facility.objects.filter()
        syncserver = configur.get('DEFAULT', 'SYNC_SERVER')
        if syncfacilities:
            logging.info(syncfacilities)
            for syncfacility in syncfacilities:
                syncfacilityid = syncfacility.id
                if syncfacilityid in configur:
                    syncserver = configur.get(syncfacilityid, 'SYNC_SERVER')
                facility_sync(syncserver, syncfacilityid)