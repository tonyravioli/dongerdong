#!/usr/bin/env python3

from irc import client
from peewee import peewee
import sys
try:
    from pyfiglet import Figlet
except:
    print("FOR FUCKS SAKE INSTALL PYFIGLET https://github.com/pwaller/pyfiglet")
    sys.exit(1)
import json
import base64
import time
import logging
import random
import copy
import _thread
import moduoli

# This is for debugging. It vomits on the screen all the irc stuff
logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

class Donger(object):
    def __init__(self):
        # For future usage
        self.pending = {} # pending['Polsaker'] = 'ravioli'
        self.health = {} # health['ravioli'] = 69
        self.gamerunning = False
        self.verbose = False
        self.turn = ""
        self._turnleft = []
        self._paccept = {}
        self.aliveplayers = []
        self.maxheal = {} # maxheal['Polsaker'] = -6
        self.roundstart = 0
        self.haspraised = []
        self.lastheardfrom = {}
        self.sourcehistory = []
        
        # thread for timeouts
        _thread.start_new_thread(self._timeouts, ())
        
        # Load the config..
        self.config = json.loads(open("config.json").read())
        
        # We will use this a lot, and I hate long variables
        self.primarychan = self.config['channel']
        self.auxchans = self.config['auxchans']

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
        self.irc.addhandler("join", self._join) # For custom messages on join
        
        # Connect to the IRC
        self.irc.connect()
    
    def _pubmsg(self, cli, ev):
        # Processing commands here

        if ev.splitd[0].startswith("!") or ev.arguments[0].startswith(cli.nickname):
            try:
                if ev.target != self.primarychan and ev.source == self.sourcehistory[-2] and ev.source == self.sourcehistory[-1] and time.time() - self.lastheardfrom[ev.source] < 10:
                    return #If the user was the last two users to speak and the last msg was within 10 seconds, don't do anything. Flood control.
            except IndexError:
                pass
            finally:
                self.lastheardfrom[ev.source] = time.time()
                self.sourcehistory.append(ev.source)

        if ev.splitd[0] == "!fight":
            if ev.target in self.auxchans:
                return
 
            if self.gamerunning:
                cli.privmsg(self.primarychan, "There's already a fight in progress.")
                return
                
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.primarychan, "Can you read? It's !fight <nick> [othernick] ...")
                return
            
            if "--verbose" in ev.splitd:
                ev.splitd.remove("--verbose")
                self.verbose = True
                cli.privmsg(self.primarychan, "Verbose mode activated (Will deactivate when a game ends)")

            
            players = copy.copy(ev.splitd)
            del players[0]
            pplayers = []
            for i in players:
                try: # Check if the challenged user is on the channel..
                    cli.channels[self.primarychan].users[i.lower()]
                except:
                    cli.privmsg(self.primarychan, "There's no one named {0} on this channel".format(i))
                    return
            
                if cli.channels[self.primarychan].users[i.lower()].host == ev.source2.host:
                    cli.privmsg(self.primarychan, "Stop hitting yourself.")
                    return 
                
                pplayers.append(cli.channels[self.primarychan].users[i.lower()].nick)
            pplayers.append(ev.source)
            self.pending[ev.source.lower()] = pplayers
            self._paccept[ev.source2.nick.lower()] = copy.copy(pplayers)
            self._paccept[ev.source2.nick.lower()].remove(ev.source)
            if cli.nickname.lower() in players:
                cli.privmsg(self.primarychan, "YOU WILL SEE")
                self._paccept[ev.source2.nick.lower()].remove(cli.nickname)
                if self._paccept[ev.source2.nick.lower()] == []:
                    self.fight(cli, pplayers)
                    return
            
            cli.privmsg(self.primarychan, "{1}: \002{0}\002 has challenged you. To accept, use '!accept {0}'".format(ev.source, ", ".join(self._paccept[ev.source2.nick.lower()])))
        elif ev.splitd[0] == "!accept":
            if self.gamerunning:
                cli.privmsg(self.primarychan, "WAIT TILL THIS FUCKING GAME ENDS")
                return
                
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.primarychan, "Can you read? It's !accept <nick>")
                return
            ev.splitd[1] = ev.splitd[1].lower()
            try:
                if ev.source not in self.pending[ev.splitd[1]]:
                    raise  # two in one
            except:
                cli.privmsg(self.primarychan, "Err... Maybe you meant to say \002!fight {0}\002? They never challenged you.".format(ev.splitd[1]))
                return
            try: # Check if the challenged user is on the channel..
                cli.channels[self.primarychan].users[ev.splitd[1]]
            except:
                cli.privmsg(self.primarychan, "They're not here anymore - maybe they were intimidated by your massive donger.")
                del self.pending[ev.splitd[1]]
                return
            
            self._paccept[ev.splitd[1].lower()].remove(ev.source)
            if self._paccept[ev.splitd[1].lower()] == []:
                # Start the fight!!!
                self.fight(cli, self.pending[ev.splitd[1]])
                del self.pending[ev.splitd[1]]
                del self._paccept[ev.splitd[1].lower()]
        elif ev.splitd[0] == "!hit":
            if not self.gamerunning:
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Wait your fucking turn or I'll kill you.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
            
            if len(ev.splitd) != 1 and ev.splitd[1] != "":
                if ev.splitd[1].lower() not in self.aliveplayers and ev.splitd[1].lower() in list(self.health):
                    cli.privmsg(self.primarychan, "WHAT?! Do you REALLY want to hit a corpse?!")
                    return
                elif ev.splitd[1].lower() not in self.aliveplayers:
                    cli.privmsg(self.primarychan, "WHA?! \002{0}\002 is not playing!".format(ev.splitd[1]))
                    return
                nick = ev.splitd[1]
            else:
                allplayers = copy.deepcopy(self.aliveplayers)
                allplayers.remove(ev.source.lower())
                nick = random.choice(list(allplayers))
                
            self.hit(ev.source.lower(), nick)
        elif ev.splitd[0] == "!heal":
            if not self.gamerunning:
                #cli.privmsg(self.primarychan, "THE FUCKING GAME IS NOT RUNNING")
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Wait your fucking turn or I'll kill you.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
            
            self.heal(ev.source)
        elif ev.splitd[0] == "!praise":
            if not self.gamerunning:
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Wait your fucking turn or I'll kill you.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
                return

            if ev.source.lower() in self.haspraised:
                cli.privmsg(self.primarychan, "Your praises bore me.")
                return
            
            if len(ev.splitd) != 1 and ev.splitd[1] != "":
                nick = ev.splitd[1]
                if ev.splitd[1].lower() not in self.aliveplayers and ev.splitd[1].lower() in list(self.health):
                    cli.privmsg(self.primarychan, "WHAT?! Do you REALLY want to hit a corpse?!")
                    return
                if ev.splitd[1].lower() not in self.aliveplayers:
                    cli.privmsg(self.primarychan, "WHA?! \002{0}\002 is not playing!".format(ev.splitd[1]))
                    return
            else:
                nick = ev.source

            praiseroll=random.randint(1, 3)
            self.haspraised.append(ev.source.lower())
            if nick.lower() == cli.nickname.lower():
                praiseroll = 2
                cli.privmsg(self.primarychan, "You try and suckle my donger while fighting me?")
                nick = ev.source
            if praiseroll == 1: #Heal
                self.heal(nick, "praise")
            elif praiseroll == 2: #Hit
                self.hit(cli.nickname.lower(), nick, "praise")
            elif praiseroll == 3:
                self.ascii("NOPE NOPE NOPE")
                self.getturn()
        elif ev.splitd[0] == "!cancel":
            try:
                self.pending[ev.source.lower()]
            except:
                cli.privmsg(self.primarychan, "You can only use !cancel if you started a !fight")
                return
            if self.gamerunning:
                cli.privmsg(self.primarychan, "THE FIGHT WAS ALREADY STARTED, IF YOU'RE A COWARD USE !QUIT")
                return
            del self.pending[ev.source.lower()]
            del self._paccept[ev.source.lower()]
            cli.privmsg(self.primarychan, "{0}'s fight cancelled".format(ev.source))
        elif ev.splitd[0] == "!reject":
            if self.gamerunning:
                return
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.primarychan, "Can you read? It's !reject <nick>")
                return
            try:
                if ev.source not in self.pending[ev.splitd[1].lower()]:
                    raise  # two in one
            except:
                cli.privmsg(self.primarychan, "But... {0} never challenged you!".format(ev.splitd[1]))
                return
            
            self.pending[ev.splitd[1].lower()].remove(ev.source)
            if len(self.pending[ev.splitd[1].lower()]) == 2 and cli.nickname in self.pending[ev.splitd[1].lower()]:
                self.pending[ev.splitd[1].lower()].remove(cli.nickname)
            self._paccept[ev.splitd[1].lower()].remove(ev.source)
            cli.privmsg(self.primarychan, "{0} fled out of the fight".format(ev.source))
            if len(self.pending[ev.splitd[1].lower()]) == 1:
                del self.pending[ev.splitd[1].lower()]
                del self._paccept[ev.splitd[1].lower()]
                cli.privmsg(self.primarychan, "Fight cancelled")
                return
            
            if self._paccept[ev.splitd[1].lower()] == []:
                # Start the fight!!!
                self.fight(cli, self.pending[ev.splitd[1].lower()])
                del self.pending[ev.splitd[1]]
                del self._paccept[ev.splitd[1].lower()]
        elif ev.arguments[0].startswith(cli.nickname):
            if len(ev.splitd) > 1 and ev.splitd[1].lower().startswith("you"):
                cli.privmsg(ev.target, "No, {0}".format(ev.source)+ ev.arguments[0].replace(cli.nickname, ""))
            else:
                cli.privmsg(ev.target, ev.arguments[0].replace(cli.nickname, ev.source))

        elif ev.splitd[0] == "!help":
            cli.privmsg(ev.target, "PM'd you my commands.")
            cli.privmsg(ev.source, "Commands available only in {0}:".format(self.primarychan))
            cli.privmsg(ev.source, "  !fight <nickname> [othernicknames]: Challenge another player")
            cli.privmsg(ev.source, "  !ascii <text>: Turns any text 13 characters or less into ascii art")
            cli.privmsg(ev.source, "  !cancel: Cancels a !fight")
            cli.privmsg(ev.source, "  !reject <nick>: Cowardly rejects a !fight")
            cli.privmsg(ev.source, "Commands available everywhere:")
            cli.privmsg(ev.source, "  !raise: Commands users to raise their dongers")
            cli.privmsg(ev.source, "  !excuse: Outputs random BOFH excuse")
            cli.privmsg(ev.source, "  !jaden: Outputs random Jaden Smith tweet")
        elif ev.splitd[0] == "!excuse":
            cli.privmsg(ev.target, self.randomLine("excuse"))
        elif ev.splitd[0] == "!jaden":
            cli.privmsg(ev.target, self.randomLine("jaden"))
        elif ev.splitd[0] == "!raise":
            cli.privmsg(ev.target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")
        elif ev.splitd[0] == "!ascii":
            if ev.target in self.auxchans:
                return
            if len(ev.splitd) > 1 and len(' '.join(ev.splitd[1:])) < 14:
                cli.privmsg(ev.target, Figlet("smslant").renderText(' '.join(ev.splitd[1:])))
            elif len(ev.splitd) > 1:
                cli.privmsg(ev.target, "Text must be 13 characters or less (that was {0} characters). Syntax: !ascii Fuck You".format(len(' '.join(ev.splitd[1:]))))
        elif ev.splitd[0] == "!health":
            if not self.gamerunning:
                #cli.privmsg(ev.target, "THE FUCKING GAME IS NOT RUNNING")
                return
            if len(ev.splitd[0]) > 1 or ev.splitd[1] == "":
                ev.splitd[1] = ev.source
            cli.privmsg(ev.target, "\002{0}\002's has \002{1}\002HP".format(ev.splitd[1], self.health[ev.splitd[1].lower()]))
        elif ev.splitd[0] == "!quit":
            if not self.gamerunning:
                #cli.privmsg(ev.target, "THE FUCKING GAME IS NOT RUNNING")
                return
            cli.mode(ev.target, "-v " + ev.source)
            self._coward(cli, ev)
        elif ev.splitd[0] == "!leaderboard" or ev.splitd[0] == "!top":
            players = Stats.select().order_by(Stats.wins.desc()).limit(3)
            c = 1
            for player in players:
                cli.privmsg(ev.target, "{0} - \002{1}\002 (\002{2}\002)".format(c, player.nick.upper(), player.wins))
                c += 1
        elif ev.splitd[0] == "!mystats" or ev.splitd[0] == "!stats":
            if len(ev.splitd) != 1:
                nick = ev.splitd[1]
            else:
                nick = ev.source
            try:
                player = Stats.get(Stats.nick == nick.lower())
                cli.privmsg(ev.target, "\002{0}\002's stats: \002{1}\002 wins, \002{2}\002 losses, and \002{3}\002 coward quits".format(
                                        player.realnick, player.wins, player.losses, player.quits))
            except:
                cli.privmsg(ev.target, "There are no registered stats for \002{0}\002".format(nick))   

        elif ev.splitd[0].startswith("!") and 1 == 0: #Disabling this cause it's dumb.
            try:
                command = ev.splitd[0].replace("!", "").lower()
                stringtosend=getattr(moduoli.Module, command)()
                cli.privmsg(ev.target, stringtosend)
            except:
                raise

    def hit(self, hfrom, to, modifier="none"):
        try:
            self.maxheal[hfrom.lower()]
        except:
            self.maxheal[hfrom.lower()] = 44

        damage = random.randint(18, 35)
        criticalroll = random.randint(1, 12)

        if modifier == "praise":
            criticalroll = 1

        instaroll = random.randint(1, 50)
        if self.verbose:
            self.irc.privmsg(self.primarychan, "Verbose: instaroll is {0}/50 (1 for instakill)".format(instaroll))
            self.irc.privmsg(self.primarychan, "Verbose: criticalroll is {0}/12 (1 for critical)".format(criticalroll))
            self.irc.privmsg(self.primarychan, "Verbose: Regular damage is {0}/35".format(damage))
            
        if instaroll == 1:
            self.ascii("instakill")
            self.ascii("rekt")
            self.irc.privmsg(self.primarychan, "\002{0}\002 REKT {1}!".format(self.irc.channels[self.primarychan].users[hfrom.lower()].nick, self.irc.channels[self.primarychan].users[to.lower()].nick))
            #self.win(ev.source, self.health)
            self.health[to.lower()] = -1
            self.aliveplayers.remove(to.lower())
            try:
                self._turnleft.remove(to.lower())
            except:
                pass
            self.getturn()
            self.countstat(self.irc.channels[self.primarychan].users[to.lower()].nick, "loss")
            if to.lower() != self.irc.nickname.lower():
                self.irc.kick(self.primarychan, to, "REKT")
            return
        elif criticalroll == 1:
            if self.verbose:
                self.irc.privmsg(self.primarychan, "Verbose: Critical hit, duplicating damage: {0}/70".format(damage*2))
            if modifier == "praise":
                self.ascii("FUCK YOU")
            else:
                self.ascii("critical")
            damage = damage * 2
        
        self.health[to.lower()] -= damage
        if hfrom.lower() == self.irc.nickname.lower() and hfrom.lower() not in self.health:
            fromhp = "999999999"
        else:
            fromhp = self.health[hfrom.lower()]
        self.irc.privmsg(self.primarychan, "\002{0}\002 (\002{1}\002HP) deals \002{2}\002 to \002{3}\002 (\002{4}\002HP)".format(hfrom,
                                    str(fromhp), str(damage), self.irc.channels[self.primarychan].users[to.lower()].nick, str(self.health[to.lower()])))

        if self.health[to.lower()] <= 0:
            self.ascii("rekt")
            self.irc.privmsg(self.primarychan, "\002{0}\002 REKT {1}!".format(self.irc.channels[self.primarychan].users[hfrom.lower()].nick, self.irc.channels[self.primarychan].users[to.lower()].nick))
            self.aliveplayers.remove(to.lower())
            try:
                self._turnleft.remove(to.lower())
            except:
                pass
            self.countstat(self.irc.channels[self.primarychan].users[to.lower()].nick, "loss")
            if to.lower() != self.irc.nickname.lower():
                self.irc.kick(self.primarychan, to, "REKT")
            
        
        self.getturn()
    
    def heal(self, nick, modifier="none"):
        try:
            self.maxheal[nick.lower()]
        except:
            self.maxheal[nick.lower()] = 44
        if self.maxheal[nick.lower()] <= 23:
            self.irc.privmsg(self.primarychan, "Sorry, bro. We don't have enough chopsticks to heal you.")
            return
        healing = random.randint(22, self.maxheal[nick.lower()])
        if modifier == "praise":
            healing = healing * 2
            self.ascii("whatever")
        
        self.health[nick.lower()] += healing
        self.maxheal[nick.lower()] = self.maxheal[nick.lower()] - 5
        if self.verbose:
            self.irc.privmsg(self.primarychan, "Verbose: Regular healing is {0}/{1}".format(healing, self.maxheal[nick.lower()]))
        if self.health[nick.lower()] > 100:
            self.health[nick.lower()] = 100
            self.irc.privmsg(self.primarychan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002100HP\002".format(nick, healing))
        else:
            self.irc.privmsg(self.primarychan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002{2}HP\002".format(nick, healing, self.health[nick.lower()]))
        self.getturn()

    
    # Here we handle ragequits
    def _coward(self, cli, ev):
        if self.gamerunning:
            if ev.source2.nick.lower() in self.aliveplayers:
                self.ascii("coward")
                self.irc.privmsg(self.primarychan, "The coward is dead!")
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
        cli.mode(self.primarychan, "+m")
        self.ascii("fight")
        cli.privmsg(self.primarychan, " V. ".join(fighters).upper())
        cli.privmsg(self.primarychan, "RULES:")
        cli.privmsg(self.primarychan, "1. Wait your turn. One person at a time.")
        cli.privmsg(self.primarychan, "2. Be a dick about it.")
        cli.privmsg(self.primarychan, ".")
        cli.privmsg(self.primarychan, "Use !hit [nick] to strike.")
        cli.privmsg(self.primarychan, "Use !heal to heal yourself.")
        cli.privmsg(self.primarychan, "Use !praise [nick] to praise to the donger gods (once per game).")
        for i in fighters:
            cli.mode(self.primarychan, "+v " + i)
            self.health[i.lower()] = 100
            self.aliveplayers.append(i.lower())
        self.haspraised = []
        self.gamerunning = True
        self.getturn()
        
    def getturn(self):
        if self.verbose:
            self.irc.privmsg(self.primarychan, "Verbose: Getting turns")
            
        if len(self._turnleft) == 0:
            if self.verbose:
                self.irc.privmsg(self.primarychan, "Verbose: No turns left, refreshing list")
            self._turnleft = copy.copy(self.aliveplayers)
        
        if len(self.aliveplayers) == 1:
            if self.verbose:
                self.irc.privmsg(self.primarychan, "Verbose: Only one player left, ending the game")
            self.win(self.aliveplayers[0])
            return
        
        self.newturn = random.choice(self._turnleft)
        if self.verbose:
            self.irc.privmsg(self.primarychan, "Verbose: Got turn: {0}".format(self.newturn))
        while self.turn == self.newturn or self.newturn not in self.aliveplayers:
            self.newturn = random.choice(self._turnleft)
            if self.verbose:
                self.irc.privmsg(self.primarychan, "Verbose: Getting turns again (last turn was dead or turned recently): {0}".format(self.newturn))
                
        self.turn = self.newturn
        self._turnleft.remove(self.turn)
        self.roundstart = time.time()
        self.irc.privmsg(self.primarychan, "It is \002{0}\002's turn".format(self.irc.channels[self.primarychan].users[self.turn].nick))
        
        # AI
        if self.turn.lower() == self.irc.nickname.lower():
            time.sleep(random.randint(2, 4))
            playerstohit = copy.copy(self.aliveplayers)
            playerstohit.remove(self.irc.nickname.lower())
            tohit = random.choice(playerstohit)
            if self.health[self.irc.nickname.lower()] < 45 and self.health[tohit] > 29:
                if self.verbose:
                    self.irc.privmsg(self.primarychan, "Verbose: AI: Less than 45 HP, opponent more than 30. Healing.")
                self.irc.privmsg(self.primarychan, "!heal") 
                self.heal(self.irc.nickname.lower())
            else:
                if self.verbose:
                    self.irc.privmsg(self.primarychan, "Verbose: AI: More than 45 HP, opponent less than 30. Attacking.")
                self.irc.privmsg(self.primarychan, "!hit " + tohit) 
                self.hit(self.irc.nickname.lower(), tohit)
    
    def win(self, winner, stats=True):
        self.verbose = False
        self.irc.mode(self.primarychan, "-m")
        self.irc.mode(self.primarychan, "-v " + winner)
        if len(list(self.health)) > 2:
            self.irc.privmsg(self.primarychan, "{0} REKT {1}!".format(self.irc.channels[self.primarychan].users[winner.lower()].nick, self._dusers(winner)))
        self.aliveplayers = []
        self.health = {}
        self._turnleft = []
        self.gamerunning = False
        self.turn = 0
        self.roundstart = 0
        if stats is True:
            self.countstat(self.irc.channels[self.primarychan].users[winner.lower()].nick, "win")
    
    def ascii(self, key, fancy=False): #Only used in fights
        if not fancy:
            self.irc.privmsg(self.primarychan, Figlet("smslant").renderText(key.upper()))
        else:
            self.irc.privmsg(self.primarychan, Figlet(random.choice(['slant', 'smslant'])).renderText(key.upper()))
    
    def randomLine(self, type):
        if type == "excuse":
            file = "excuse_list.txt"
        elif type == "jaden":
            file = "jaden_list.txt"
        try:
            return random.choice(list(open(file)))
        except:
            return "Error getting file {0}".format(file)

    # For the record: cli = client and ev = event
    def _connect(self, cli, ev):
        # Starting with the SASL authentication
        # Note: If services are down, the bot won't connect
        cli.send("CAP REQ :sasl")
        cli.send("AUTHENTICATE PLAIN")

    def _join(self, cli, ev):
        if ev.source2.nick == cli.nickname and ev.target == self.primarychan:
            self.irc.privmsg(ev.target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")

    def _dusers(self, skip):
        players = self.health
        del players[skip]
        pplayers = []
        for i in players:
            pplayers.append(i.lower())
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
        for channel in self.auxchans:
           time.sleep(2)
           cli.join(channel)

    def _timeouts(self):
        while True:
            time.sleep(5)
            if self.gamerunning and self.turn != "":
                if time.time() - self.roundstart > 60:
                    self.irc.privmsg(self.primarychan, "\002{0}\002 forfeits due to idle.".format(self.turn))
                    self.irc.mode(self.primarychan, "-v " + self.turn)
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

while dongerdong.irc.connected == True and dongerdong.irc.imayreconnect == True:
    try:
        time.sleep(1) # Infinite loop of awesomeness
    except KeyboardInterrupt:
        excuse=dongerdong.randomLine("excuse")
        #excuse=random.choice(list(open("excuse_list.txt"))) #Parsing an excuse list from BOFH
        # Sending stuff manually and assigning it the fucking top priority (no queue)
        # dongerdong.irc.send("PRIVMSG {0} :ERROR - {1}".format(dongerdong.chan, excuse), True)
        dongerdong.irc.send("QUIT :{0}".format(excuse.upper()), True)
        print("exit due to keyboard interrupt")
        break  # >:D PURE EVIL
