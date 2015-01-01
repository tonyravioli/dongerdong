#!/usr/bin/env python3

from irc import client
from peewee import peewee
import json
import base64
import time
import logging
import random
import copy
import _thread

# This is for debugging. It vomits on the screen all the irc stuff
logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

class Donger(object):
    def __init__(self):
        # For future usageâ„¢
        self.pending = {} # pending['Polsaker'] = 'ravioli'
        self.health = {} # health['ravioli'] = 69
        self.gamerunning = False
        self.turn = ""
        self._turnleft = []
        self._paccept = []
        self.aliveplayers = []
        self.roundstart = 0
        
        # thread for timeouts
        _thread.start_new_thread(self._timeouts, ())
        
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
                cli.privmsg(self.chan, "Sorry, bro... But the right syntax is !fight <nick> [othernick] ...")
                return
            #ev.splitd[1] = ev.splitd[1].lower()
            
            #if ev.splitd[1] == cli.nickname.lower():
            #    cli.privmsg(self.chan, "YOU WILL SEE")
            #    self.fight(cli, [ev.source.lower(), cli.nickname])
            #    return
            
            players = copy.copy(ev.splitd)
            del players[0]
            pplayers = []
            for i in players:
                try: # Check if the challenged user is on the channel..
                    cli.channels[self.chan].users[i.lower()]
                except:
                    cli.privmsg(self.chan, "You're high? Because {0} is not on this channel".format(i))
                    return
            
                if cli.channels[self.chan].users[i.lower()].host == ev.source2.host:
                    cli.privmsg(self.chan, "I THINK YOU'RE TRYING TO HIT YOURSELF")
                    return 
                
                pplayers.append(cli.channels[self.chan].users[i.lower()].nick)
            pplayers.append(ev.source)
            self.pending[ev.source.lower()] = pplayers
            self._paccept = copy.copy(pplayers)
            self._paccept.remove(ev.source)
            if cli.nickname.lower() in players:
                cli.privmsg(self.chan, "YOU WILL SEE")
                self._paccept.remove(cli.nickname)
                if self._paccept == []:
                    self.fight(cli, pplayers)
                    return
            
            cli.privmsg(self.chan, "{1}: \002{0}\002 has challenged you. To accept, use '!accept {0}'".format(ev.source, ", ".join(self._paccept)))
        elif ev.splitd[0] == "!accept":
            if self.gamerunning:
                cli.privmsg(self.chan, "WAIT TILL THIS FUCKING GAME ENDS")
                return
                
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.chan, "Sorry, bro... But the right syntax is !accept <nick>")
                return
            ev.splitd[1] = ev.splitd[1].lower()
            try:
                if ev.source not in self.pending[ev.splitd[1]]:
                    raise  # two in one
            except:
                cli.privmsg(self.chan, "Err... Maybe you meant to say \002!fight {0}\002? They never challenged you.".format(ev.splitd[1]))
                
            try: # Check if the challenged user is on the channel..
                cli.channels[self.chan].users[ev.splitd[1]]
            except:
                cli.privmsg(self.chan, "Well... They were cowards... YOU WIN")
                del self.pending[ev.splitd[1]]
                return
            
            self._paccept.remove(ev.source)
            if self._paccept == []:
                # Start the fight!!!
                self.fight(cli, self.pending[ev.splitd[1]])
                del self.pending[ev.splitd[1]]
                self._paccept = []
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
                if ev.splitd[1].lower() not in self.aliveplayers and ev.splitd[1].lower() in list(self.health):
                    cli.privmsg(self.chan, "WHAT?! Do you REALLY want to hit a corpse?!")
                    return
                elif ev.splitd[1].lower() not in self.aliveplayers:
                    cli.privmsg(self.chan, "WHA?! \002{0}\002 is not playing!".format(ev.splitd[1]))
                    return
                nick = ev.splitd[1]
            else:
                allplayers = copy.deepcopy(self.aliveplayers)
                allplayers.remove(ev.source.lower())
                nick = random.choice(list(allplayers))
                
            self.hit(ev.source.lower(), nick)
        elif ev.splitd[0] == "!heal":
            if not self.gamerunning:
                cli.privmsg(self.chan, "THE FUCKING GAME IS NOT RUNNING")
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.chan, "Wait your fucking turn or I'll kill you.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.chan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
            
            self.heal(ev.source)
            
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
            cli.mode(self.channel, "-v " + ev.source)
        elif ev.splitd[0] == "!leaderboard" or ev.splitd[0] == "!top":
            players = Stats.select().order_by(Stats.wins.desc()).limit(3)
            c = 1
            for player in players:
                cli.privmsg(self.chan, "{0} - \002{1}\002 (\002{2}\002)".format(c, player.nick.upper(), player.wins))
                c += 1
        elif ev.splitd[0] == "!mystats" or ev.splitd[0] == "!stats":
            if len(ev.splitd) != 1:
                nick = ev.splitd[1]
            else:
                nick = ev.source
            try:
                player = Stats.get(Stats.nick == nick.lower())
                cli.privmsg(self.chan, "\002{0}\002's stats: \002{1}\002 wins, \002{2}\002 losses, and \002{3}\002 coward quits".format(
                                        player.realnick, player.wins, player.losses, player.quits))
            except:
                cli.privmsg(self.chan, "There are no registered stats for \002{0}\002".format(nick))   
    
    def hit(self, hfrom, to):
        damage = random.randint(18, 35)
        criticalroll = random.randint(1, 12)
        instaroll = random.randint(1, 50)
        if instaroll == 1:
            self.irc.privmsg(self.chan, "\002INSTAKILL\002")
            self.ascii("rekt")
            self.irc.privmsg(self.chan, "\002{0}\002 REKT {1}!".format(self.irc.channels[self.chan].users[hfrom.lower()].nick, self.irc.channels[self.chan].users[to.lower()].nick))
            #self.win(ev.source, self.health)
            self.health[to.lower()] = -1
            self.aliveplayers.remove(to.lower())
            self.getturn()
            self.countstat(self.irc.channels[self.chan].users[to.lower()].nick, "loss")
            self.irc.mode(self.chan, "-v " + to)
            return
        elif criticalroll == 1:
            self.ascii("critical")
            damage = damage * 2
        
        self.health[to.lower()] -= damage
        self.irc.privmsg(self.chan, "\002{0}\002 (\002{1}\002HP) deals \002{2}\002 to \002{3}\002 (\002{4}\002HP)".format(hfrom,
                                    str(self.health[hfrom.lower()]), str(damage), self.irc.channels[self.chan].users[to.lower()].nick, str(self.health[to.lower()])))

        if self.health[to.lower()] <= 0:
            self.ascii("rekt")
            self.irc.privmsg(self.chan, "\002{0}\002 REKT {1}!".format(self.irc.channels[self.chan].users[hfrom.lower()].nick, self.irc.channels[self.chan].users[to.lower()].nick))
            self.aliveplayers.remove(to.lower())
            self.countstat(self.irc.channels[self.chan].users[to.lower()].nick, "loss")
            self.irc.mode(self.chan, "-v " + to)
        
        self.getturn()
    
    def heal(self, nick):
        healing = random.randint(22, 44)
        self.health[nick.lower()] += healing
        if self.health[nick.lower()] > 100:
            self.health[nick.lower()] = 100
            self.irc.privmsg(self.chan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002100HP\002".format(nick, healing))
        else:
            self.irc.privmsg(self.chan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002{2}HP\002".format(nick, healing, self.health[nick.lower()]))
        self.getturn()

    
    # Here we handle ragequits
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
                
                self.countstat(ev.source2.nick, "quit")
    
    # Adds something on the stats
    # ctype = win/loss/quit
    def countstat(self, nick, ctype):
        try:
            stat = Stats.get(Stats.nick == nick.lower())
        except:
            stat = Stats.create(nick=nick.lower(), losses=0, quits=0, wins=0, realnick=nick)
        if ctype == "win":
            stat.wins += 1
        elif ctype == "loss":
            stat.losses += 1
        elif ctype == "quit":
            stat.quits += 1
        stat.save()
    
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
            
        self.newturn = random.choice(self._turnleft)
        while self.turn == self.newturn or self.newturn not in self.aliveplayers:
            self.newturn = random.choice(self._turnleft)
        self.turn = self.newturn
        self._turnleft.remove(self.turn)
        self.roundstart = time.time()
        self.irc.privmsg(self.chan, "It is \002{0}\002's turn".format(self.irc.channels[self.chan].users[self.turn].nick))
        
        # AI
        if self.turn.lower() == self.irc.nickname.lower():
            time.sleep(random.randint(2, 5))
            if self.health[self.irc.nickname.lower()] < 45:
                self.irc.privmsg(self.chan, "!heal") 
                self.heal(self.irc.nickname.lower())
            else:
                playerstohit = copy.copy(self.aliveplayers)
                playerstohit.remove(self.irc.nickname.lower())
                tohit = random.choice(playerstohit)
                self.irc.privmsg(self.chan, "!hit " + tohit) 
                self.hit(self.irc.nickname.lower(), tohit)
    
    def win(self, winner, stats=True):
        
        self.irc.mode(self.chan, "-m")
        self.irc.mode(self.chan, "-v " + winner)
        if len(list(self.health)) > 2:
            self.irc.privmsg(self.chan, "{0} REKT {1}!".format(self.irc.channels[self.chan].users[winner.lower()].nick, self._dusers(winner)))
        self.aliveplayers = []
        self.health = {}
        self._turnleft = []
        self.gamerunning = False
        self.turn = 0
        self.roundstart = 0
        if stats is True:
            self.countstat(self.irc.channels[self.chan].users[winner.lower()].nick, "win")
    
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
        pplayers = []
        for i in players:
            pplayers.append(self.irc.channels[self.chan].users[i.lower()].nick)
        ṕplayers = list(self.health)
        last = pplayers[-1]
        del pplayers[-1]
        return ", ".join(pplayers) + " and " + last
        
    def _auth(self, cli, ev):
        cli.send("AUTHENTICATE {0}".format(
        base64.b64encode("{0}\0{0}\0{1}".format(self.config['nickserv-user'],
                                                self.config['nickserv-pass'])
                                                .encode()).decode()))
        cli.send("CAP END")
    
    def _welcome(self, cli, ev):
        cli.join(self.config['channel'])
    
    def _timeouts(self):
        while True:
            time.sleep(5)
            if self.gamerunning and self.turn != "":
                if time.time() - self.roundstart > 60:
                    self.irc.privmsg(self.chan, "Looks like \002{0}\002 is a dirty idler. DIE DIE DIEEEEE".format(self.turn))
                    self.irc.mode(self.chan, "-v " + self.turn)
                    self.aliveplayers.remove(self.turn)
                    self.health[self.turn] = -1
                    self.getturn()
        

# Database stuff
database = peewee.SqliteDatabase('dongerdong.db')
database.connect()

class BaseModel(peewee.Model):
    class Meta:
        database = database

# Stats table
class Stats(BaseModel):
    nick = peewee.CharField()  # Nickname of the player
    realnick = peewee.CharField()  # Nickname of the player (not lowercased :P)
    wins = peewee.IntegerField() # Number of REKTs
    losses = peewee.IntegerField() # Number of loses
    quits = peewee.IntegerField() # Number of coward quits
    
Stats.create_table(True) # Here we create the table

# Start donging
dongerdong = Donger()

while dongerdong.irc.connected == True:
    try:
        time.sleep(1) # Infinite loop of awesomeness
    except KeyboardInterrupt:
        # Sending stuff manually and assigning it the fucking top priority (no queue)
        dongerdong.irc.send("PRIVMSG {0} :FUCK YOU ALL".format(dongerdong.chan), True)
        dongerdong.irc.send("QUIT :I'LL KILL YOU ALL", True)
        print("exit due to keyboard interrupt")
        break  # >:D PURE EVIL
