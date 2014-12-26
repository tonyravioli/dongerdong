#!/usr/bin/env python3

from irc import client
import json
import base64
import time
import logging

# This is for debugging. It vomits on the screen all the irc stuff
logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

# TODO: Command processing
# TODO: Commands
# TODO: Fights
# TODO: Fight commands
# TODO: Ascii art
# TODO: Fight stats

class Donger(object):
    def __init__(self):
        # Load the config..
        self.config = json.loads(open("config.json").read())
        # Create the irc object
        self.irc = client.IRCClient("donger")
        self.irc.configure(server = self.config['server'],
                           nick = self.config['nick'],
                           ident = self.config['nick'],
                           gecos = "The supreme donger")
        # Create handlers and F U N stuff
        self.irc.addhandler("connect", self._connect) # for SASL
        self.irc.addhandler("authenticate", self._auth) # for SASL!!!1
        self.irc.addhandler("welcome", self._welcome) # For the autojoin
        
        # Connect to the IRC
        self.irc.connect()
    
    # For the record: cli = client and ev = event
    def _connect(self, cli, ev):
        # Starting with the SASL authentication
        # Note: If services are down, the bot won't connect
        cli.send("CAP REQ :sasl")
        cli.send("AUTHENTICATE PLAIN")
        
    def _auth(self, cli, ev):
        cli.send("AUTHENTICATE {0}".format(
        base64.b64encode("{0}\0{0}\0{1}".format(self.config['nickserv-user'],
                                                self.config['nickserv-pass'])
                                                .encode()).decode()))
        cli.send("CAP END")
    
    def _welcome(self, cli, ev):
        cli.join(self.config['channel'])
        

# Start donging
dongerdong = Donger()

while dongerdong.irc.connected == True:
    time.sleep(1) # Infinite loop of awesomeness
