#!/usr/bin/env python3

from irc import client
import json
import base64
import time
import logging
import random
import copy

# This is for debugging. It vomits on the screen all the irc stuff
logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

class Donger(object):
    def __init__(self):
        # For future usage™
        self.pending = {} # pending['Polsaker'] = 'ravioli'
        self.health = {} # health['ravioli'] = 69
        self.gamerunning = False
        self.turn = ""
        self._turnleft = []
        self.aliveplayers = []
        
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
        self.irc.addhandler("part", self._coward) # Coward extermination
        self.irc.addhandler("quit", self._coward) # ^
        
        # Connect to the IRC
        self.irc.connect()
    
    def _pubmsg(self, cli, ev):
        # Processing commands here
        if ev.splitd[0] == "!fight":
            if self.gamerunning:
                cli.privmsg(self.chan, "WAIT TILL THIS FUCKING GAME ENDS")
                return
                
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.chan, "Sorry, bro... But the right syntax is !fight <nick>")
                return
            ev.splitd[1] = ev.splitd[1].lower()
            
            # TODO: #2, fight with the bot
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
            self.pending[ev.source.lower()] = cli.channels[self.chan].users[ev.splitd[1]].nick
            cli.privmsg(self.chan, "{1}: {0} has challenged you. To accept, use '!accept {0}'".format(ev.source, cli.channels[self.chan].users[ev.splitd[1]].nick))
        elif ev.splitd[0] == "!accept":
            if self.gamerunning:
                cli.privmsg(self.chan, "WAIT TILL THIS FUCKING GAME ENDS")
                return
                
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.chan, "Sorry, bro... But the right syntax is !accept <nick>")
                return
            ev.splitd[1] = ev.splitd[1].lower()
            
            try:
                if self.pending[ev.splitd[1]] != ev.source:
                    raise  # two in one
            except:
                cli.privmsg(self.chan, "Err... Maybe you meant to say !fight {0} ? They never challenged you.".format(ev.splitd[1]))
                
            try: # Check if the challenged user is on the channel..
                cli.channels[self.chan].users[ev.splitd[1]]
            except:
                cli.privmsg(self.chan, "Well... They were cowards... YOU WIN")
                del self.pending[ev.splitd[1]]
                return
            
            # Start the fight!!!
            self.fight(cli, [self.pending[ev.splitd[1]], cli.channels[self.chan].users[ev.splitd[1]].nick])
            del self.pending[ev.splitd[1]]
        elif ev.splitd[0] == "!hit":
            if not self.gamerunning:
                cli.privmsg(self.chan, "THE FUCKING GAME IS NOT RUNNING")
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.chan, "Wait your fucking turn or I'll kill you.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.chan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
            
            if len(ev.splitd) != 1 and ev.splitd[1] != "":
                if ev.splitd[1] not in self.aliveplayers and ev.splitd[1] in list(self.health):
                    cli.privmsg(self.chan, "WHAT?! Do you REALLY want to hit a corpse?!")
                    return
                elif ev.splitd[1] not in self.aliveplayers:
                    cli.privmsg(self.chan, "WHA?! \002{0}\002 is not playing!".format(ev.splitd[1]))
                    return
                nick = ev.splitd[1]
            else:
                allplayers = copy.deepcopy(self.health)
                del allplayers[ev.source.lower()]
                nick = random.choice(list(allplayers))
            damage = random.randint(18, 35)
            criticalroll = random.randint(1, 16)
            instaroll = random.randint(1, 50)
            if instaroll == 1:
                cli.privmsg(self.chan, "INSTAKILL")
                self.ascii("rekt")
                cli.privmsg(self.chan, "{0} REKT {1}!".format(ev.source, nick))
                #self.win(ev.source, self.health)
                self.health[nick.lower()] = -1
                self.aliveplayers.remove(nick.lower())
                self.getturn()
                return
            elif criticalroll == 1:
                self.ascii("critical")
                damage = damage * 2
            
            self.health[nick.lower()] -= damage
            cli.privmsg(self.chan, "{0} ({1}HP) deals {2} to {3} ({4}HP)".format(ev.source, str(self.health[ev.source.lower()]), str(damage), nick, str(self.health[nick.lower()])))

            if self.health[nick] <= 0:
                self.ascii("rekt")
                cli.privmsg(self.chan, "{0} REKT {1}!".format(ev.source, nick))
                self.aliveplayers.remove(nick.lower())
                cli.mode(self.chan, "-v " + nick)
            
            self.getturn()
        elif ev.splitd[0] == "!heal":
            if not self.gamerunning:
                cli.privmsg(self.chan, "THE FUCKING GAME IS NOT RUNNING")
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.chan, "Wait your fucking turn or I'll kill you.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.chan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
            
            healing = random.randint(22, 44)
            self.health[ev.source.lower()] += healing
            if self.health[ev.source.lower()] > 100:
                self.health[ev.source.lower()] = 100
                cli.privmsg(self.chan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002100HP\002".format(ev.source, healing))
            else:
                cli.privmsg(self.chan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002{2}HP\002".format(ev.source, healing, self.health[ev.source.lower()]))
            self.getturn()
        elif ev.splitd[0] == cli.nickname + "!":
            cli.privmsg(self.chan, ev.source + "!")
        elif ev.splitd[0] == "!help":
            cli.privmsg(self.chan, "!fight <nick> to initiate fight; !quit to bail out of a fight; !hit to hit, !heal to heal.")
        elif ev.splitd[0] == "!ping":
            cli.privmsg(self.chan, "pong!")
        elif ev.splitd[0] == "!health":
            if not self.gamerunning:
                cli.privmsg(self.chan, "THE FUCKING GAME IS NOT RUNNING")
                return
            if len(ev.splitd[0]) > 1 or ev.splitd[1] == "":
                ev.splitd[1] = ev.source
            cli.privmsg(self.chan, "\002{0}\002's has \002{1}\002HP".format(ev.splitd[1], self.health[ev.splitd[1].lower()]))
        elif ev.splitd[0] == "!quit":
            self._coward(cli, ev)
            
    def _coward(self, cli, ev):
        if self.gamerunning:
            if ev.source2.nick.lower() in self.aliveplayers:
                self.ascii("coward")
                self.irc.privmsg(self.chan, "The coward is dead!")
                self.aliveplayers.remove(ev.source2.nick.lower())
                self.health[ev.source2.nick.lower()] = -1
                try:
                    self._turnleft.remove(ev.source2.nick.lower())
                except:
                    pass
                    
                if len(self.aliveplayers) == 1:
                    self.win(self.aliveplayers[0], stats=False)
                elif self.turn == ev.source2.nick.lower():
                    self.getturn()
    
    def fight(self, cli, fighters):
        cli.mode(self.chan, "+m")
        self.ascii("fight")
        cli.privmsg(self.chan, " V. ".join(fighters).upper())
        cli.privmsg(self.chan, "RULES:")
        cli.privmsg(self.chan, "1. Wait your turn. One person at a time.")
        cli.privmsg(self.chan, "2. That's it")
        cli.privmsg(self.chan, ".")
        cli.privmsg(self.chan, "Use !hit to strike the other player.")
        cli.privmsg(self.chan, "Use !heal to heal yourself.")
        for i in fighters:
            cli.mode(self.chan, "+v " + i)
            self.health[i.lower()] = 100
            self.aliveplayers.append(i.lower())
        self.gamerunning = True
        self.getturn()
        
    def getturn(self):
        if self._turnleft == []:
            self._turnleft = copy.copy(self.aliveplayers)
        
        if len(self.aliveplayers) == 1:
            self.win(self.aliveplayers[0])
            return
            
        self.turn = random.choice(self._turnleft)
        self._turnleft.remove(self.turn)
        self.irc.privmsg(self.chan, "It is \002{0}\002's turn".format(self.turn))
    
    def win(self, winner, stats=True):
        self.irc.mode(self.chan, "-m")
        self.irc.mode(self.chan, "-v " + winner)
        if len(list(self.health)) > 2:
            self.irc.privmsg(self.chan, "{0} REKT {1}!".format(winner, self._dusers(winner)))
        self.aliveplayers = []
        self.health = {}
        self._turnleft = []
        self.gamerunning = False
        if stats is True:
            pass # TODO: stats
    
    def ascii(self, key):
        cli = self.irc # >_>
        if key=="rekt":
            cli.privmsg(self.chan, "   ___  ______ ________")
            cli.privmsg(self.chan, "  / _ \/ __/ //_/_  __/")
            cli.privmsg(self.chan, " / , _/ _// ,<   / /   ")
            cli.privmsg(self.chan, "/_/|_/___/_/|_| /_/    ")
        elif key=="fight":
            cli.privmsg(self.chan, "   _______________ ________")
            cli.privmsg(self.chan, "  / __/  _/ ___/ // /_  __/")
            cli.privmsg(self.chan, " / _/_/ // (_ / _  / / /   ")
            cli.privmsg(self.chan, "/_/ /___/\___/_//_/ /_/    ")
        elif key=="critical":
            cli.privmsg(self.chan, "  ________  ______________________   __ ")
            cli.privmsg(self.chan, " / ___/ _ \/  _/_  __/  _/ ___/ _ | / / ")
            cli.privmsg(self.chan, "/ /__/ , _// /  / / _/ // /__/ __ |/ /__")
            cli.privmsg(self.chan, "\___/_/|_/___/ /_/ /___/\___/_/ |_/____/")
        elif key == "coward":
            cli.privmsg(self.chan, "   __________ _       _____    ____  ____ ")
            cli.privmsg(self.chan, "  / ____/ __ \ |     / /   |  / __ \/ __ \\") 
            cli.privmsg(self.chan, " / /   / / / / | /| / / /| | / /_/ / / / /")
            cli.privmsg(self.chan, "/ /___/ /_/ /| |/ |/ / ___ |/ _, _/ /_/ / ")
            cli.privmsg(self.chan, "\____/\____/ |__/|__/_/  |_/_/ |_/_____/  ")
                                          
        else:
            cli.privmsg(self.chan, "ascii "+ key +"!")
    
    # For the record: cli = client and ev = event
    def _connect(self, cli, ev):
        # Starting with the SASL authentication
        # Note: If services are down, the bot won't connect
        cli.send("CAP REQ :sasl")
        cli.send("AUTHENTICATE PLAIN")
    
    def _dusers(self, skip):
        players = self.health
        del players[skip]
        players = list(self.health)
        last = players[-1]
        del players[-1]
        return ", ".join(players) + " and " + last
        
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
