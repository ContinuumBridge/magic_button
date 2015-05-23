#!/usr/bin/env python
# magic_button_.py
"""
Copyright (c) 2015 ContinuumBridge Limited
Written by Peter Claydon
"""

# Default values:
config = {
          "uuids": [ ]
}

import sys
import os.path
import time
import json
from cbcommslib import CbApp
from cbconfig import *

class App(CbApp):
    def __init__(self, argv):
        self.state = "stopped"
        self.devices = []
        self.idToName = {} 
        # Super-class init must be called
        CbApp.__init__(self, argv)

    def setState(self, action):
        self.state = action
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.sendManagerMessage(msg)

    def reportBeacon(self, name, state):
        # Node doesn't like being bombarded with manager messages
        now = time.time()

    def onAdaptorService(self, message):
        #self.cbLog("debug", "onAdaptorService, message: " + str(message))
        for p in message["service"]:
            if p["characteristic"] == "ble_beacon":
                req = {"id": self.id,
                       "request": "service",
                       "service": [
                                   {"characteristic": "ble_beacon",
                                    "interval": 1.0,
                                    "uuids": config["uuids"]
                                   }
                                  ]
                      }
                self.sendMessage(req, message["id"])

    def onAdaptorData(self, message):
        self.cbLog("debug", "onAdaptorData, message: " + str(json.dumps(message, indent=4)))
        try:
            if message["characteristic"] == "ble_beacon":
                for b in config["uuids"]:
                    pass
        except Exception as ex:
            self.cbLog("warning", "onAdaptorData problem, Exception: " + str(type(ex)) + str(ex.args))

    def onConfigureMessage(self, managerConfig):
        global config
        configFile = CB_CONFIG_DIR + "magic_button.config"
        try:
            with open(configFile, 'r') as f:
                newConfig = json.load(f)
                self.cbLog("debug", "Read simple_beacon_app.config")
                config.update(newConfig)
        except Exception as ex:
            self.cbLog("warning", "Problem reading magic_button.config. Exception: " + str(type(ex)) + str(ex.args))
        for c in config:
            if c.lower in ("true", "t", "1"):
                config[c] = True
            elif c.lower in ("false", "f", "0"):
                config[c] = False
        self.cbLog("debug", "Config: " + str(json.dumps(config, indent=4)))
        now = time.time()
        for adaptor in managerConfig["adaptors"]:
            adtID = adaptor["id"]
            if adtID not in self.devices:
                # Because managerConfigure may be re-called if devices are added
                name = adaptor["name"]
                friendly_name = adaptor["friendly_name"]
                self.idToName[adtID] = friendly_name.replace(" ", "_")
                self.devices.append(adtID)
        self.setState("starting")

if __name__ == '__main__':
    App(sys.argv)
