#!/usr/bin/env python
# magic_button_.py
"""
Copyright (c) 2015 ContinuumBridge Limited
Written by Peter Claydon
"""

import sys
import os.path
import time
import json
from twisted.internet import task
from cbcommslib import CbApp, CbClient
from cbconfig import *

configFile          = CB_CONFIG_DIR + "magic_button.config"
CHECK_INTERVAL      = 120
WATCHDOG_INTERVAL   = 120
config = {
          "uuids": [ ],
          "cid": "undefined"
}

class App(CbApp):
    def __init__(self, argv):
        self.state = "stopped"
        self.devices = []
        self.idToName = {} 
        self.buttonStates = {}
        # Super-class init must be called
        CbApp.__init__(self, argv)

    def setState(self, action):
        self.state = action
        msg = {"id": self.id,
               "status": "state",
               "state": self.state}
        self.sendManagerMessage(msg)

    def onConcMessage(self, message):
        self.client.receive(message)

    def checkConnected(self):
        # Called every CHECK_INTERVAL
        now = time.time()
        if self.buttonStates != {}:
            delkeys = []
            for b in self.buttonStates:
                self.cbLog("debug", "checkConnected, buttonStates: " + str(self.buttonStates) + ", b: " + str(b))
                if now - self.buttonStates[b]["connectTime"] > WATCHDOG_INTERVAL:
                    toClient = {"b": b,
                                "p": self.buttonStates[b]["rssi"],
                                "c": False
                               }
                    self.client.send(toClient)
                    delkeys.append(b)
                elif self.buttonStates[b]["rssi_changed"]:
                    toClient = {"b": b,
                                "p": self.buttonStates[b]["rssi"],
                                "c": True
                               }
                    self.client.send(toClient)
                    self.buttonStates[b]["rssi_changed"] = False
                self.cbLog("debug", "checkConnected, buttonStates after del: " + str(self.buttonStates))
            for d in delkeys:
                del self.buttonStates[d]

    def onClientMessage(self, message):
        self.cbLog("debug", "onClientMessage, message: " + str(json.dumps(message, indent=4)))
        global config
        if "uuids" in message:
            config["uuids"] = message["uuids"]
            self.cbLog("debug", "onClientMessage, updated UUIDs: " + str(json.dumps(config, indent=4)))
            try:
                with open(configFile, 'w') as f:
                    json.dump(config, f)
            except Exception as ex:
                self.cbLog("warning", "onClientMessage, could not write to file. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))

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
        #self.cbLog("debug", "onAdaptorData, message: " + str(json.dumps(message, indent=4)))
        try:
            if self.state != "running":
                self.setState("running")
            if message["characteristic"] == "ble_beacon":
                if message["data"]["uuid"] in config["uuids"]:
                    buttonID = message["data"]["major"]
                    buttonState = message["data"]["minor"] & 0x01
                    if buttonID in self.buttonStates:
                        self.buttonStates[buttonID]["connectTime"] = time.time()
                        if abs(self.buttonStates[buttonID]["rssi"] - message["data"]["rx_power"]) > 3:
                            self.buttonStates[buttonID]["rssi"] = message["data"]["rx_power"]
                            self.buttonStates[buttonID]["rssi_changed"] = True
                        self.buttonStates[buttonID]["rssi"] = message["data"]["rx_power"]
                    else:
                        self.buttonStates[buttonID] = {
                            "connectTime": time.time(),
                            "rssi":  message["data"]["rx_power"],
                            "rssi_changed": True,
                            "state": -1
                        }
                    if buttonState != self.buttonStates[buttonID]["state"]:
                        self.buttonStates[buttonID]["state"] = buttonState
                        toClient = {"b": message["data"]["major"],
                                    "s": buttonState,
                                    "p": message["data"]["rx_power"],
                                    "c": True
                                   }
                        self.client.send(toClient)
                        self.buttonStates[buttonID]["rssi_changed"] = False
        except Exception as ex:
            self.cbLog("warning", "onAdaptorData problem. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))

    def onConfigureMessage(self, managerConfig):
        global config
        try:
            with open(configFile, 'r') as f:
                newConfig = json.load(f)
                self.cbLog("debug", "Read simple_beacon_app.config")
                config.update(newConfig)
        except Exception as ex:
            self.cbLog("warning", "Problem reading magic_button.config. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))
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
        self.client = CbClient(self.id, config["cid"])
        self.client.onClientMessage = self.onClientMessage
        self.client.sendMessage = self.sendMessage
        self.client.cbLog = self.cbLog
        l = task.LoopingCall(self.checkConnected)
        l.start(CHECK_INTERVAL)
        self.setState("starting")

if __name__ == '__main__':
    App(sys.argv)
