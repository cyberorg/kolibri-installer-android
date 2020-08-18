import initialization  # keep this first, to ensure we're set up for other imports

import flask
import logging
import os
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

# MSS Cloud sync for primary facility on user device
def run_sync():
    import threading
    from kolibri.utils.cli import main
    from configparser import ConfigParser
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)

    from kolibri.core.auth.models import Facility

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
    syncuser = configur.get('DEFAULT', 'SYNC_USER')
    syncon = configur.getboolean('DEFAULT', 'SYNC_ON')

    if (syncon):    
        syncfacility = Facility.get_default_facility()
        
        if (syncfacility is not None):
            syncfacilityid = syncfacility.id
            syncpass = "sync" + syncfacilityid
            syncserver = configur.get('DEFAULT', 'SYNC_SERVER')
            syncdelay = configur.getfloat('DEFAULT', 'SYNC_DELAY')
            threading.Timer(syncdelay, run_sync).start()
            main(["manage", "sync", "--baseurl", syncserver, "--username", syncuser, "--password", syncpass, "--facility", syncfacilityid, "--verbosity", "3"])

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

