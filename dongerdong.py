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
        # For future usage™
        self.pending = {} # pending['Polsaker'] = 'ravioli'
        
        # Load the config..
        self.config = json.loads(open("config.json").read())
        
        # We will use this a lot, and I hate long variables
        self.chan = self.config['channel']
        
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
        self.irc.addhandler("pubmsg", self._pubmsg) # For commands
        
        # Connect to the IRC
        self.irc.connect()
    
    def _pubmsg(self, cli, ev):
        # Processing commands here
        if ev.splitd[0] == "!fight":
            if len(ev.splitd) == 1: # I hate you
                cli.privmsg(self.chan, "Sorry, bro... But the right syntax is !fight <nick>")
                return
            ev.splitd[1] = ev.splitd[1].lower()
            if ev.splitd[1] == cli.nickname.lower():
                cli.privmsg(self.chan, "DON'T FUCK WITH ME")
                return
                        
            try: # Check if the challenged user is on the channel..
                cli.channels[self.chan].users[ev.splitd[1]]
            except:
                cli.privmsg(self.chan, "You're high? Because that guy is not on this channel")
                return
            
            if cli.channels[self.chan].users[ev.splitd[1]].host == ev.source2.host:
                cli.privmsg(self.chan, "I THINK YOU'RE TRYING TO HIT YOURSELF")
                return
            
            # All checks OK, put this fight with the pending ones
            self.pending[ev.source2.host] = cli.channels[self.chan].users[ev.splitd[1]].host
            cli.privmsg(self.chan, "{1}: {0} has challenged you. To accept, use '!accept {0}'".format(ev.source, cli.channels[self.chan].users[ev.splitd[1]].nick))
        elif ev.splitd[0] == "!accept":
            cli.privmsg(self.chan, "NOT DONE YET")

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
