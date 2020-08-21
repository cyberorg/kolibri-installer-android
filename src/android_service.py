import initialization  # keep this first, to ensure we're set up for other imports

import flask
import logging
import os
import threading
import sys
import pew.ui
import shutil
import time

from config import FLASK_PORT

from android_utils import share_by_intent
from kolibri_utils import get_content_file_path

# initialize logging before loading any third-party modules, as they may cause logging to get configured.
logging.basicConfig(level=logging.DEBUG)


logging.info("Entering android_service.py...")

from android_utils import get_service_args, make_service_foreground
from kolibri_utils import start_kolibri_server

# load the arguments passed into the service into environment variables
args = get_service_args()
for arg, val in args.items():
    print("setting envvar '{}' to '{}'".format(arg, val))
    os.environ[arg] = str(val)

# move in a templated Kolibri data directory, including pre-migrated DB, to speed up startup
HOME_TEMPLATE_PATH = "preseeded_kolibri_home"
HOME_PATH = os.environ["KOLIBRI_HOME"]
if not os.path.exists(HOME_PATH) and os.path.exists(HOME_TEMPLATE_PATH):
    shutil.move(HOME_TEMPLATE_PATH, HOME_PATH)

# ensure the service stays running by "foregrounding" it with a persistent notification
make_service_foreground("Kolibri is running...", "Click here to resume.")

def facility_sync(syncdelay, syncserver, syncuser, syncpass, syncfacilityid):
    pid = os.fork()
    if pid == 0:
        main(["manage", "sync", "--baseurl", syncserver, "--username", syncuser, "--password", syncpass, "--facility", syncfacilityid, "--verbosity", "3"])
    else:
        os.waitpid(pid, 0)

def run_sync():
    from kolibri.utils.cli import main
    f = open(os.devnull, 'w')
    sys.stdout = f
#    logging.basicConfig(level=logging.INFO)
#    logging.disable(logging.INFO)
#    logging.disable(logging.WARNING)
    from configparser import ConfigParser
    KOLIBRI_HOME = os.environ.get("KOLIBRI_HOME")
    syncini_file = os.path.join(KOLIBRI_HOME, "syncoptions.ini")
    configur = ConfigParser()
    try:
        file = open(syncini_file, 'r')
    except IOError:
        configur['DEFAULT'] = { 'SYNC_ON': 'True',
                                'SYNC_SERVER': 'content.myscoolserver.in',
                                'SYNC_USER': 'syncuser',
                                'SYNC_DELAY': '900.0'
                                }
        with open(syncini_file, 'w') as configfile:
            configur.write(configfile)
        return
    configur.read(syncini_file)
    syncon = configur.getboolean('DEFAULT', 'SYNC_ON')
    if (syncon):
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)
        from kolibri.core.auth.models import Facility
        syncfacilities = Facility.objects.filter()
        syncuser = configur.get('DEFAULT', 'SYNC_USER')
        syncdelay = configur.getfloat('DEFAULT', 'SYNC_DELAY')
        syncserver = configur.get('DEFAULT', 'SYNC_SERVER')
        if syncfacilities:
            for syncfacility in syncfacilities:
                syncfacilityid = syncfacility.id
                syncpass = "sync" + syncfacilityid
                if syncfacilityid in configur:
                    syncuser = configur.get(syncfacilityid, 'SYNC_USER')
                    syncpass = configur.get(syncfacilityid, 'SYNC_PASS')
                    syncdelay = configur.getfloat(syncfacilityid, 'SYNC_DELAY')
                    syncserver = configur.get(syncfacilityid, 'SYNC_SERVER')
                pid = os.fork()
                if pid == 0:
                    main(["manage", "sync", "--baseurl", syncserver, "--username", syncuser, "--password", syncpass, "--facility", syncfacilityid, "--verbosity", "3"])
                else:
                    os.waitpid(pid, 0)
        threading.Timer(syncdelay, run_sync).start()

# start the kolibri server as a thread
thread = pew.ui.PEWThread(target=start_kolibri_server)
thread.daemon = True
thread.start()
run_sync()

# start a parallel Flask server as a backchannel for triggering events
flaskapp = flask.Flask(__name__)

@flaskapp.route('/share_by_intent')
def do_share_by_intent():

    args = flask.request.args
    allowed_args = ["filename", "path", "msg", "app", "mimetype"]
    kwargs = {key: args[key] for key in args if key in allowed_args}

    if "filename" in kwargs:
        kwargs["path"] = get_content_file_path(kwargs.pop("filename"))

    logging.error("Sharing: {}".format(kwargs))

    share_by_intent(**kwargs)

    return "<html><body style='background: white;'>OK, boomer</body></html>"


if __name__ == "__main__":
    flaskapp.run(host="localhost", port=FLASK_PORT)
