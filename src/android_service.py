import initialization  # keep this first, to ensure we're set up for other imports

import flask
import logging
import os
import pew.ui
import shutil
import time
import threading

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

#MSS sync
def run_sync():
    threading.Timer(60.0, run_sync).start()
    from kolibri.utils.cli import main
    from configparser import ConfigParser
    KOLIBRI_HOME=os.environ.get("KOLIBRI_HOME")
    syncini_path = os.path.join(KOLIBRI_HOME, "syncoptions.ini")
    try:
        file = open(syncini_path, 'r')
    except IOError:
        return
    configur = ConfigParser()
    configur.read(syncini_path)
    syncuser=configur.get('MSS','SYNC_USER')
    syncpass=configur.get('MSS','SYNC_PASS')
    syncfacility=configur.get('MSS','SYNC_FACILITY')
    main(["manage", "sync", "--baseurl", "http://content.myscoolserver.in/", "--username", syncuser, "--password", syncpass, "--facility", syncfacility, "--verbosity", "3"])

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
