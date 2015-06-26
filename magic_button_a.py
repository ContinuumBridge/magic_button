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
CHECK_INTERVAL      = 30
WATCHDOG_INTERVAL   = 70
MAX_SEND_INTERVAL   = 60*30     # Ensure we have sent a message to client within this time
CID                 = "CID157"  # Client ID
config = {
          "uuids": [ ]
}

def nicetime(timeStamp):
    localtime = time.localtime(timeStamp)
    milliseconds = '%03d' % int((timeStamp - int(timeStamp)) * 1000)
    now = time.strftime('%H:%M:%S, %d-%m-%Y', localtime)
    return now

class App(CbApp):
    def __init__(self, argv):
        self.state = "stopped"
        self.devices = []
        self.idToName = {} 
        self.buttonStates = {}
        self.beaconAdaptor = None
        self.lastSent = 0  # When a message was last sent to the client
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
                #self.cbLog("debug", "checkConnected, buttonStates: " + str(self.buttonStates) + ", b: " + str(b))
                if now - self.buttonStates[b]["connectTime"] > WATCHDOG_INTERVAL:
                    self.buttonStates[b]["rssi"] = -200
                    toClient = {"b": b,
                                "p": self.buttonStates[b]["rssi"],
                                "c": False
                               }
                    self.client.send(toClient)
                    self.cbLog("debug", "checkConnected, button no longer connected: " + str(json.dumps(toClient, indent=4)))
                    self.lastSent = now
                    delkeys.append(b)
                    self.cbLog("debug", "checkConnected, buttonStates after del: " + str(self.buttonStates))
                #self.cbLog("debug", "checkConnected, buttonStates after del: " + str(self.buttonStates))
            for d in delkeys:
                del self.buttonStates[d]
        if now - self.lastSent > MAX_SEND_INTERVAL:
            self.cbLog("debug", "Exceeded MAX_SEND_INTERVAL")
            self.lastSent = now
            toClient = {"status": "init"}
            self.client.send(toClient)

    def onClientMessage(self, message):
        self.cbLog("debug", "onClientMessage, message: " + str(json.dumps(message, indent=4)))
        global config
        if "uuids" in message:
            config["uuids"] = message["uuids"]
            #self.cbLog("debug", "onClientMessage, updated UUIDs: " + str(json.dumps(config, indent=4)))
            try:
                with open(configFile, 'w') as f:
                    json.dump(config, f)
            except Exception as ex:
                self.cbLog("warning", "onClientMessage, could not write to file. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))
            self.readLocalConfig()
            self.requestUUIDs(self.beaconAdaptor)

    def requestUUIDs(self, adaptor):
        req = {"id": self.id,
               "request": "service",
               "service": [
                           {"characteristic": "ble_beacon",
                            "interval": 1.0,
                            "uuids": config["uuids"]
                           }
                          ]
              }
        self.sendMessage(req, adaptor)

    def onAdaptorService(self, message):
        #self.cbLog("debug", "onAdaptorService, message: " + str(message))
        for p in message["service"]:
            if p["characteristic"] == "ble_beacon":
                self.beaconAdaptor = message["id"]
                self.requestUUIDs(self.beaconAdaptor)

    def onAdaptorData(self, message):
        #self.cbLog("debug", "onAdaptorData, message: " + str(json.dumps(message, indent=4)))
        try:
            if self.state != "running":
                self.setState("running")
            if message["characteristic"] == "ble_beacon":
                if message["data"]["uuid"] in config["uuids"]:
                    changed = False
                    buttonID = message["data"]["major"]
                    buttonState = message["data"]["minor"] & 0x01
                    if buttonID in self.buttonStates:
                        self.buttonStates[buttonID]["connectTime"] = time.time()
                        self.cbLog("debug", "Button " + str(buttonID) + " seen at time " + nicetime(time.time()))
                    else:
                        self.buttonStates[buttonID] = {
                            "connectTime": time.time(),
                            "state": -1
                        }
                        self.cbLog("info", "New button: " + str(buttonID))
                    if buttonState != self.buttonStates[buttonID]["state"]:
                        self.buttonStates[buttonID]["state"] = buttonState
                        self.buttonStates[buttonID]["rssi"] = message["data"]["rx_power"]
                        self.buttonStates[buttonID]["rssi_time"] = time.time()
                        changed = True
                    elif abs(self.buttonStates[buttonID]["rssi"] - message["data"]["rx_power"]) > 10:
                        self.buttonStates[buttonID]["rssi"] = message["data"]["rx_power"]
                        self.buttonStates[buttonID]["rssi_time"] = time.time()
                        changed = True
                    elif abs(self.buttonStates[buttonID]["rssi"] - message["data"]["rx_power"]) > 3:
                        if time.time() - self.buttonStates[buttonID]["rssi_time"] > 60 * 15:
                            self.buttonStates[buttonID]["rssi"] = message["data"]["rx_power"]
                            self.buttonStates[buttonID]["rssi_time"] = time.time()
                            changed = True
                    if changed:
                        toClient = {"b": buttonID,
                                    "s": self.buttonStates[buttonID]["state"],
                                    "p": self.buttonStates[buttonID]["rssi"],
                                    "c": True
                                   }
                        self.client.send(toClient)
                        self.cbLog("debug", "Sent to client: " + str(json.dumps(toClient, indent=4)))
        except Exception as ex:
            self.cbLog("warning", "onAdaptorData problem. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))

    def readLocalConfig(self):
        global config
        try:
            with open(configFile, 'r') as f:
                newConfig = json.load(f)
                self.cbLog("debug", "Read local config")
                config.update(newConfig)
        except Exception as ex:
            self.cbLog("warning", "Problem reading magic_button.config. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))
        for c in config:
            if c.lower in ("true", "t", "1"):
                config[c] = True
            elif c.lower in ("false", "f", "0"):
                config[c] = False
        try:
            config["uuids"] = [u.upper() for u in config["uuids"]]
        except Exception as ex:
            self.cbLog("warning", "Problem upper-casing uuids. Type: " + str(type(ex)) + ", exception: " +  str(ex.args))
        self.cbLog("debug", "Config: " + str(json.dumps(config, indent=4)))

    def onConfigureMessage(self, managerConfig):
        self.readLocalConfig()
        now = time.time()
        for adaptor in managerConfig["adaptors"]:
            adtID = adaptor["id"]
            if adtID not in self.devices:
                # Because managerConfigure may be re-called if devices are added
                name = adaptor["name"]
                friendly_name = adaptor["friendly_name"]
                self.idToName[adtID] = friendly_name.replace(" ", "_")
                self.devices.append(adtID)
        self.client = CbClient(self.id, CID, 3)
        self.client.onClientMessage = self.onClientMessage
        self.client.sendMessage = self.sendMessage
        self.client.cbLog = self.cbLog
        l = task.LoopingCall(self.checkConnected)
        l.start(CHECK_INTERVAL)
        self.setState("starting")

if __name__ == '__main__':
    App(sys.argv)
