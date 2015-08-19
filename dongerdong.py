#!/usr/bin/env python3

import importlib
import threading
import operator
import logging
import random
import base64
import json
import time
import copy
import os
import re

from irc import client

from peewee import peewee

try:
    from pyfiglet import Figlet
except ImportError:
    print("FOR FUCKS SAKE INSTALL PYFIGLET https://github.com/pwaller/pyfiglet")
    quit()

# This is for debugging. It vomits on the screen all the irc stuff
logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig(format="%(asctime)s: %(name)s: %(levelname)"
                    "s (at %(filename)s:%(funcName)s:%(lineno)d): %(message)s")

class Donger(object):
    def __init__(self):
        # For future usage
        self.pending = {} # pending['Polsaker'] = 'ravioli'
        self.deathmatchpending = {}
        self.health = {} # health['ravioli'] = 69
        self.gamerunning = False
        self.deathmatch = False
        self.verbose = False
        self.turn = ""
        self.turnindex = 0
        self.allplayers = []
        self._turnleft = []
        self._paccept = {}
        self.aliveplayers = []
        self.deadplayers = []
        self.maxheal = {} # maxheal['Polsaker'] = -6
        self.roundstart = 0
        self.haspraised = []
        self.lastheardfrom = {}
        self.sourcehistory = []
        self.zombies = []
        self.lastpingreq = None
        self.accountsseenonthisgame = [] # hi,thisisanextremellylongvariablename

        self.extracommands = {} # Commands declarated by modules

        # thread for timeouts
        self.irc_lock = threading.RLock()
        self.timeouts_thread = threading.Thread(None, self._timeouts)
        self.timeouts_thread.start()

        # Load the config..
        self.config = json.loads(open("config.json").read())

        # We will use this a lot, and I hate long variables
        self.primarychan = self.config["channel"]
        self.auxchans = self.config.get("auxchans", [])
        self.statsurl = self.config.get("stats-url", "")
        self.prefix = self.config.get("prefix", "!")

        # Create the irc object
        self.irc = client.IRCClient("donger")
        self.irc.configure(server = self.config["server"],
                           nick = self.config["nick"],
                           ident = self.config.get("ident", self.config["nick"]),
                           port = 6697,
                           gecos = self.config.get("realname", "The supreme donger"))
        # Create handlers and F U N stuff
        self.irc.addhandler("connect", self._connect) # for SASL
        self.irc.addhandler("authenticate", self._auth) # for SASL!!!1
        self.irc.addhandler("welcome", self._welcome) # For the autojoin
        self.irc.addhandler("pubmsg", self._pubmsg) # For commands
        self.irc.addhandler("privmsg", self._privmsg) # For private commands
        self.irc.addhandler("part", self._coward) # Coward extermination
        self.irc.addhandler("quit", self._coward) # ^
        self.irc.addhandler("join", self._join) # For custom messages on join
        self.irc.addhandler("account", self._account) # account-notify stuff
        self.irc.addhandler("ctcpreply", self._ctcpreply) # ctcp shit

        # Connect to the IRC
        self.irc.connect()

    def verboseoutput(self, stringtoprint): #This is going to replace the if self.verbose crap.
        if self.verbose:
            with self.irc_lock:
                self.irc.privmsg(self.primarychan, stringtoprint)

    def _pubmsg(self, cli, ev):
        # Processing commands here

        message = ev.arguments[0]
        commands = message.split()

        if re.match(r"^{0}[,: ]*$".format(cli.nickname), message):
            msg = message[0].replace(cli.nickname, "", 1)
            msg = msg.rstrip(",").rstrip(":").rstrip(" ")
            if not msg:
                command = commands.pop(1).lower()
                del commands[0]
            else:
                command = commands.pop(0).lower()

        elif commands[0].startswith(self.prefix):
            command = commands.pop(0).lower()[len(self.prefix):]

        else:
            if message.startswith(cli.nickname):
                if commands and commands[0].lower().startswith("you"):
                    cli.privmsg(ev.target, "No, {0}{1}".format(ev.source, message.replace(cli.nickname, "")))
                else:
                    cli.privmsg(ev.target, message.replace(cli.nickname, ev.source))

            if message.lower().startswith("fuck off " + cli.nickname):
                cli.privmsg(ev.target, "\u0001ACTION fucks {0}\u0001".format(ev.source))

        if message.startswith((self.prefix, cli.nickname, "fuck off")):
            try:
                if ev.target != self.primarychan and ev.source == self.sourcehistory[-2] == self.sourcehistory[-1] and time.time() - self.lastheardfrom[ev.source] < 10:
                    return #If the user was the last two users to speak and the last msg was within 10 seconds, don't do anything. Flood control.
            except IndexError:
                pass
            finally:
                self.lastheardfrom[ev.source] = time.time()
                self.sourcehistory.append(ev.source)

        else:
            return # If this works the way I think it will, it won't need to parse anything unless it starts with a ! or the cli.nickname.

        if command in {"fight", "deathmatch"}:
            if ev.target in self.auxchans:
                return

            if self.gamerunning:
                cli.privmsg(self.primarychan, "There's already a fight in progress.")
                return

            if not commands:
                cli.privmsg(self.primarychan, "Can you read? It's '{0}{1} <nick> [othernick]' ...".format(self.prefix, command))
                return

            if cli.channels[ev.target.lower()].users[ev.source.lower()].account is None:
                cli.privmsg(self.primarychan, "You must be identified with NickServ to play!")
                return

            self.deathmatch = False
            self.verbose = False

            if "--verbose" in commands:
                commands.remove("--verbose")
                self.verbose = True
                cli.privmsg(self.primarychan, "Verbose mode activated (Will deactivate when a game ends)")

            if command == "deathmatch":
                if cli.nickname in commands:
                    cli.privmsg(self.primarychan, "Sorry, but {0} is unavailable for a deathmatch.".format(cli.nickname))
                    return
                elif len(commands) > 1:
                    cli.privmsg(self.primarychan, "Deathmatches are 1 v 1 only.")
                    return
                self.deathmatch = True

            players = commands[:]
            pplayers = []
            chan = cli.channels[self.primarychan]
            for player in players:
                if not player.lower() in chan.users:
                    cli.privmsg(self.primarychan, "There's no one named {0} on this channel".format(player))
                    return
                if chan.users[player.lower()].account is None:
                    cli.privmsg(self.primarychan, "\u0002{0}\u0002 is not identified with nickserv!".format(player))
                    return

                if chan.users[player.lower()].host == ev.source2.host:
                    cli.privmsg(self.primarychan, "Stop hitting yourself.")
                    return 

                pplayers.append(chan.users[player.lower()].nick)
            pplayers.append(ev.source)
            self.pending[ev.source.lower()] = pplayers
            if self.deathmatch:
                self.deathmatchpending[ev.source.lower()] = commands[0]
            else:
                self.deathmatchpending.pop(ev.source.lower(), None)

            self._paccept[ev.source2.nick.lower()] = pplayers[:]
            self._paccept[ev.source2.nick.lower()].remove(ev.source)

            if cli.nickname.lower() in players:
                cli.privmsg(self.primarychan, "YOU WILL SEE")
                self._paccept[ev.source2.nick.lower()].remove(cli.nickname)
                if self._paccept[ev.source2.nick.lower()] == []:
                    self.fight(cli, pplayers, ev.source2.nick.lower())
                    return

            if self.deathmatch:
                cli.privmsg(self.primarychan, "{1}: \u0002{0}\u0002 has challenged you to a deathmatch. The loser will be bant for 20 minutes. To accept, use '{2}accept {0}'".format(ev.source, ", ".join(self._paccept[ev.source2.nick.lower()]), self.prefix))
            else:
                cli.privmsg(self.primarychan, "{1}: \u0002{0}\u0002 has challenged you. To accept, use '{2}accept {0}'".format(ev.source, ", ".join(self._paccept[ev.source2.nick.lower()]), self.prefix))

        elif command == "accept":
            self.deathmatch = False #We'll do this and check later if it's a deathmatch.

            if self.gamerunning:
                cli.privmsg(self.primarychan, "WAIT TILL THIS FUCKING GAME ENDS")
                return

            if not commands:
                cli.privmsg(self.primarychan, "Can you read? It's {0}accept <nick>".format(self.prefix))
                return

            player = commands.pop(0)

            if ev.source not in self.pending.get(player.lower(), ()):
                cli.privmsg(self.primarychan, "Err... Maybe you meant to say \u0002{0}fight {1}\u0002? They never challenged you.".format(self.prefix, player))
                return

            if player.lower() not in cli.channels[self.primarychan].users:
                cli.privmsg(self.primarychan, "They're not here anymore - maybe they were intimidated by your donger.")
                del self.pending[player.lower()]
                return

            self._paccept[player.lower()].remove(ev.source)
            if not self._paccept[player.lower()]:
                self.deathmatch = (self.deathmatchpending.get(player) == ev.source)

                # Start the fight!!!
                self.fight(cli, self.pending[player.lower()], player, self.deathmatch)
                del self.pending[player.lower()]
                del self._paccept[player.lower()]

        elif command == "hit":
            if not self.gamerunning:
                return

            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Wait your fucking turn or I'll kill you.")
                return

            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
                return

            if commands:
                player = commands.pop(0)
                if player.lower() not in self.aliveplayers and player.lower() in self.health:
                    cli.privmsg(self.primarychan, "WHAT?! Do you REALLY want to hit a corpse?!")
                    return
                elif player.lower() not in self.aliveplayers:
                    cli.privmsg(self.primarychan, "WHA?! \u0002{0}\u0002 is not playing!".format(player))
                    return

            else:
                self.hit(ev.source.lower(), random.choice(list(self.aliveplayers.keys() - {ev.source.lower()})))

        elif command == "heal":
            if not self.gamerunning:
                return

            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Wait your fucking turn or I'll kill you.")
                return

            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
                return

            if ev.source.lower() in self.zombies:
                cli.privmsg(self.primarychan, "Zombies can't heal")
                return

            self.heal(ev.source)

        elif command == "praise":
            if not self.gamerunning:
                return

            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Wait your fucking turn or I'll kill you.")
                return

            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "GET OUT OR I'LL KILL YOU! INTRUDER INTRUDER INTRUDER")
                return

            if ev.source.lower() in self.haspraised or ev.source.lower() in self.zombies:
                cli.privmsg(self.primarychan, "Your praises bore me.")
                return

            if self.deathmatch:
                cli.privmsg(self.primarychan, "\"A dong's life is the most precious thing in the universe.\" You can't praise in deathmatches.")
                return

            if commands:
                player = commands.pop(0)
                if player.lower() not in self.aliveplayers and player.lower() in self.health:
                    cli.privmsg(self.primarychan, "WHAT?! Do you REALLY want to hit a corpse?!")
                    return

                if player.lower() not in self.aliveplayers:
                    cli.privmsg(self.primarychan, "WHA?! \u0002{0}\u0002 is not playing!".format(player))
                    return
            else:
                player = ev.source

            praiseroll = random.randrange(3)
            self.countstat(ev.source.lower(), "praise")
            self.haspraised.append(ev.source.lower())

            if player.lower() == cli.nickname.lower():
                praiseroll = 2
                cli.privmsg(self.primarychan, "You try and suckle my donger while fighting me?")
                player = ev.source

            if praiseroll == 0: #Heal
                self.heal(player, "praise")
            elif praiseroll == 1: #Hit
                self.hit(cli.nickname.lower(), player, "praise")
            elif praiseroll == 2:
                self.ascii("NOPE NOPE NOPE")
                self.getturn()

        elif command == "cancel":
            if ev.source.lower() not in self.pending:
                cli.privmsg(self.primarychan, "You can only use !cancel if you started a !fight")
                return

            if self.gamerunning:
                cli.privmsg(self.primarychan, "THE FIGHT WAS ALREADY STARTED, IF YOU'RE A COWARD USE !QUIT")
                return

            self.deathmatchpending = {}
            self.deathmatch = False
            del self.pending[ev.source.lower()]
            del self._paccept[ev.source.lower()]
            cli.privmsg(self.primarychan, "{0}'s fight cancelled".format(ev.source))

        elif command == "reject":
            if self.gamerunning:
                return

            if not commands:
                cli.privmsg(self.primarychan, "Can you read? It's {0}reject <nick>".format(self.prefix))
                return

            player = commands.pop(0)

            if ev.source not in self.pending.get(player.lower(), ()):
                cli.privmsg(self.primarychan, "But... {0} never challenged you!".format(player))
                return
            
            self.pending[player.lower()].remove(ev.source)
            if len(self.pending[player.lower()]) == 2 and cli.nickname in self.pending[player.lower()]:
                self.pending[player.lower()].remove(cli.nickname)

            self._paccept[player.lower()].remove(ev.source)
            cli.privmsg(self.primarychan, "{0} fled out of the fight".format(ev.source))
            if len(self.pending[player.lower()]) == 1:
                del self.pending[player.lower()]
                del self._paccept[player.lower()]
                cli.privmsg(self.primarychan, "Fight cancelled")
                return

            if not self._paccept[player.lower()]:
                # Start the fight!!!
                self.fight(cli, self.pending[player.lower()], player)
                del self.pending[player]
                del self._paccept[player.lower()]

        elif command == "help":
            self.commandHelp(cli, ev)

        elif command == "excuse":
            cli.privmsg(ev.target, self.randomLine("excuse"))

        elif command == "jaden":
            cli.privmsg(ev.target, self.randomLine("jaden"))

        elif command == "raise":
            cli.privmsg(ev.target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")

        elif command == "ping":
            current_milli_time = int(time.time() * 1000)
            self.lastpingreq = ev.target
            cli.privmsg(ev.source, "\u0001PING {0}\u0001".format(current_milli_time))

        elif command == "lower":
            cli.privmsg(ev.target, "┌༼ຈل͜ຈ༽┐ ʟᴏᴡᴇʀ ʏᴏᴜʀ ᴅᴏɴɢᴇʀs ┌༼ຈل͜ຈ༽┐")

        elif command == "dong":
            cli.privmsg(ev.target, self.randomLine("donger"))

        elif command == "ascii":
            if ev.target in self.auxchans or self.gamerunning:
                return

            if command and len(" ".join(commands)) < 16:
                cli.privmsg(ev.target, Figlet("smslant").renderText(" ".join(commands)))

            elif commands:
                cli.privmsg(ev.target, "Text must be 15 characters or less (that was {0} characters). Syntax: {1}ascii Fuck You".format(len(" ".join(commands), self.prefix)))

        elif command == "health":
            if not self.gamerunning:
                return
            if not commands:
                commands[0] = ev.source
            cli.privmsg(ev.target, "\u0002{0}\u0002's has \u0002{1}\u0002HP".format(commands[0], self.health[commands[0].lower()]))

        elif command == "quit":
            if not self.gamerunning:
                return

            cli.devoice(ev.target, ev.source)
            self._coward(cli, ev)

        elif command == "top" and ev.target == self.primarychan:
            players = Statsv2.select()
            # K, now we have to make our own arranging of stuff, damnit
            p = {}
            for player in players:
                if (player.fights + player.accepts) < 10:
                    continue # not counting players with less than 10 fights
                
                p[player.nick] = (player.wins - player.losses)
            
            p = sorted(p.items(), key=operator.itemgetter(1), reverse=True)
                
            c = 0
            for player in p:
                cli.privmsg(ev.target, "{0} - \u0002{1}\u0002 (+\u0002{2}\u0002)".format(c, player[0].upper(), player[1]))
                c += 1
                if c == 3:
                    break
            if self.statsurl != "":
                cli.privmsg(ev.target, "More stats are available at {0}".format(self.statsurl))

        elif command in {"mystats", "stats"}:
            if commands:
                nick = commands.pop(0)
            else:
                nick = ev.source

            nick = getattr(cli.channels[ev.target.lower()].users.get(player.lower()), "account", None) or nick

            try:
                player = Statsv2.get(Statsv2.nick == nick.lower())
                totaljoins = (player.wins + player.losses + player.quits + player.easywins) - (player.fights + player.accepts)
                cli.privmsg(ev.target, ("\u0002{p.realnick}\u0002's stats: \u0002{p.wins}\u0002 wins, \u0002{p.easywins}\u0002 easy wins, "
                                        "\u0002{p.losses}\u0002 losses, \u0002{p.quits}\u0002 coward quits, \u0002{p.idleouts}\u0002 idle-outs, "
                                        "\u0002{p.praises}\u0002 {prefix}praises, \u0002{p.fights}\u0002 fights started, accepted \u0002{p.accepts}\u0002 fights, "
                                        "{prefix}joined \u0002{totaljoins}\u0002 fights (\u0002{totalfights}\u0002 total fights), \u0002{p.hits}\u0002 {prefix}hits, "
                                        "\u0002{p.heals}\u0002 {prefix}heals, \u0002{p.dcaused}\u0002HP of damage dealt and \u0002{p.dreceived}\u0002 damage received."
                                        "{url}").format(p=player, prefix=self.prefix, url=" {0}".format(self.stats_url) if self.stats_url else "",
                                                        totaljoins=totaljoins, totalfights=(player.wins + player.losses + player.quits)))

            except Exception:
                cli.privmsg(ev.target, "There are no registered stats for \u0002{0}\u0002".format(nick))
        elif command in self.extracommands:
            self.extracommands[command](self, cli, ev)

    def commandHelp(self, cli, ev):
        cli.privmsg(ev.target, "PM'd you my commands.")
        cli.privmsg(ev.source, "Commands available only in {0}:".format(self.primarychan))
        cli.privmsg(ev.source, "  {0}fight <nickname> [othernicknames]: Challenge another player".format(self.prefix))
        cli.privmsg(ev.source, "  {0}deathmatch <nickname>: Same as fight, but only 1v1, and loser is bant for 20 minutes.".format(self.prefix))
        cli.privmsg(ev.source, "  {0}ascii <text>: Turns any text 13 characters or less into ascii art".format(self.prefix))
        cli.privmsg(ev.source, "  {0}cancel: Cancels a {0}fight".format(self.prefix))
        cli.privmsg(ev.source, "  {0}reject <nick>: Cowardly rejects a {0}fight".format(self.prefix))
        cli.privmsg(ev.source, "Commands available everywhere:")
        cli.privmsg(ev.source, "  {0}raise: Commands users to raise their dongers".format(self.prefix))
        cli.privmsg(ev.source, "  {0}excuse: Outputs random BOFH excuse".format(self.prefix))
        cli.privmsg(ev.source, "  {0}jaden: Outputs random Jaden Smith tweet".format(self.prefix))
        cli.privmsg(ev.source, "  {0}stats [player]: Outputs player's game stats (or your own stats)".format(self.prefix))
        cli.privmsg(ev.source, "  {0}top: Shows the three players with most wins".format(self.prefix))

    def _privmsg(self, cli, ev):
        if ev.splitd[0] == "{0}join".format(self.prefix):
            self.join(cli, ev.source, ev)

    def join(self, cli, fighter, ev):

        message = ev.arguments[0]
        args = message.split()

        if not self.gamerunning:
            cli.privmsg(fighter, "THE FUCKING GAME IS NOT RUNNING")
            return

        if len(args) == 1:
            args.append("")

        figher = fighter if args[1] != "141592" else cli.nickname
        if fighter != cli.nickname:
            if cli.channels[self.primarychan.lower()].users[fighter.lower()].account in self.accountsseenonthisgame and fighter != cli.nickname and args[1] != "zombie":
                cli.privmsg(fighter, "Stop trying to cheat, you dumb shit. To join as a zombie, say {0}join zombie".format(self.prefix))
                return 
        if fighter.lower() in self.aliveplayers:
            cli.privmsg(fighter, "You're already playing, you dumb shit.")
            return
        if fighter.lower() in self.deadplayers and args[1] != "zombie":
            cli.privmsg(fighter, "You can't rejoin a game after you've been killed.")
            return
        if fighter.lower() in self.zombies:
            return
        elif args[1] == "zombie":
            self.zombies.append(fighter.lower())
            if random.randrange(5) > 1:
                cli.privmsg(fighter, "You have no brain and your zombie dies")
                return
        
        if self.deathmatch:
            cli.privmsg(fighter, "You can't join a deathmatch.")
            return
        self.playershealth = []
        for p in self.aliveplayers:
            self.playershealth.append(self.health[p])

        #Set joining player's health to the average health of current players
        self.health[fighter.lower()] = sum(self.playershealth) // len(self.playershealth)
        self.maxheal[fighter.lower()] = 44
        if args[1] == "zombie": # ooo zombie
            self.health[fighter.lower()] = self.health[fighter.lower()] // 1.3
            cli.privmsg(self.primarychan, "\u0002{0}\u0002's ZOMBIE JOINS THE FIGHT (\u0002{1}\u0002HP)".format(fighter.upper(), self.health[fighter.lower()]))
        else:
            cli.privmsg(self.primarychan, "\u0002{0}\u0002 JOINS THE FIGHT (\u0002{1}\u0002HP)".format(fighter.upper(), self.health[fighter.lower()]))
        
        if fighter.lower() not in self.allplayers:
            self.allplayers.append(fighter.lower())

        self.accountsseenonthisgame.append(cli.channels[self.primarychan.lower()].users[fighter.lower()].account)
        self.aliveplayers.append(fighter.lower())
        cli.voice(self.primarychan, fighter)


    def hit(self, hfrom, to, modifier=None):
        if modifier is None and self.turn.lower() != hfrom.lower():
            return
        self.maxheal[hfrom.lower()] = 44

        damage = random.randint(18, 35)
        criticalroll = random.randrange(12) if hfrom.lower() not in self.zombies else 11

        if modifier == "praise":
            self.verboseoutput("Verbose: Praise. Forcing critical")
            criticalroll = 1
        else:
            self.countstat(hfrom, "hit")

        instaroll = random.randrange(50) if not self.deathmatch and hfrom.lower() not in self.zombies else 49

        self.verboseoutput("Verbose: instaroll is {0}/50 (1 for instakill)".format(instaroll))
        self.verboseoutput("Verbose: criticalroll is {0}/12 (1 for critical)".format(criticalroll))
        self.verboseoutput("Verbose: Regular damage is {0}/35".format(damage))

        if instaroll == 1:
            self.verboseoutput("Verbose: Instakill. Removing player.".format(instaroll))
            self.ascii("instakill")

            self.death(hfrom, to)
            self.health[to.lower()] = -1

            if to.lower() != self.irc.nickname.lower():
                self.irc.kick(self.primarychan, to, "REKT")
            else:
                self.irc.devoice(self.primarychan, self.irc.nickname)
            self.getturn()
            self.countstat(self.irc.channels[self.primarychan].users[to.lower()].nick, "loss")
            return
        elif criticalroll == 1:
            self.verboseoutput("Verbose: Critical hit, duplicating damage: {0}/70".format(damage*2))
            if modifier == "praise":
                self.ascii("FUCK YOU")
            else:
                self.ascii("critical")
            damage = damage * 2

        self.countstat(hfrom, "dmg", damage)
        self.countstat(to, "gotdmg", damage)
        self.health[to.lower()] -= damage
        if hfrom.lower() == self.irc.nickname.lower() and hfrom.lower() not in self.health:
            fromhp = "999999999"
        else:
            fromhp = self.health[hfrom.lower()]
        self.irc.privmsg(self.primarychan, "\u0002{0}\u0002 (\u0002{1}\u0002HP) deals \u0002{2}\u0002 to \u0002{3}\u0002 (\u0002{4}\u0002HP)".format(hfrom,
                                           fromhp, damage, self.irc.channels[self.primarychan].users[to.lower()].nick, self.health[to.lower()]))

        if self.health[to.lower()] <= 0:
            self.death(hfrom, to)
            if to.lower() != self.irc.nickname.lower():
                if self.deathmatch:
                    self.verboseoutput("Verbose: Deathmatch lost. Adding akick.")
                    self.irc.privmsg("CHANSERV", "AKICK {0} ADD {1} !T 20 FUCKIN REKT - Lost deathmatch".format(self.primarychan, self.irc.channels[self.primarychan].users[to.lower()].account))
                self.irc.kick(self.primarychan, to, "REKT")
        self.getturn()

    def death(self, slayer, player):
        self.verboseoutput("Verbose: Death. Slayer: {0}, player: {1}".format(slayer, player))
        self.irc.devoice(self.primarychan, player)
        self.ascii("rekt")
        self.irc.privmsg(self.primarychan, "\u0002{0}\u0002 REKT {1}!".format(self.irc.channels[self.primarychan].users[slayer.lower()].nick, self.irc.channels[self.primarychan].users[player.lower()].nick))
        self.verboseoutput("Verbose: Removing dead player.")
        self.aliveplayers.remove(player.lower())
        self.deadplayers.append(player.lower())
        if player.lower() in self._turnleft:
            self._turnleft.remove(player.lower())

        self.countstat(self.irc.channels[self.primarychan].users[player.lower()].nick, "loss")


    def heal(self, nick, modifier=None):
        if modifier is None and self.turn.lower() != nick.lower():
            return
        if self.maxheal[nick.lower()] <= 23 and modifier != "praise":
            self.irc.privmsg(self.primarychan, "Sorry, bro. We don't have enough chopsticks to heal you.")
            return
        healing = random.randrange(22, self.maxheal[nick.lower()] if modifier != "praise" else 41)
        if modifier == "praise":
            healing = healing * 2
            self.verboseoutput("Verbose: Praise. Forcing critical heal.")
            self.ascii("whatever")
        else:
            self.countstat(nick, "heal")

        self.health[nick.lower()] += healing
        self.verboseoutput("Verbose: Regular healing is {0}/{1}(/44)".format(healing, self.maxheal[nick.lower()]))
        self.maxheal[nick.lower()] = self.maxheal[nick.lower()] - 5

        if self.health[nick.lower()] > 100:
            self.health[nick.lower()] = 100

        self.irc.privmsg(self.primarychan, "\u0002{0}\u0002 heals for \u0002{1}HP\u0002, bringing them to \u0002{2}HP\u0002".format(nick, healing, self.health[nick.lower()]))
        self.getturn()


    # Here we handle ragequits
    def _coward(self, cli, ev):
        if self.gamerunning:
            if ev.source2.nick.lower() in self.aliveplayers:
                self.ascii("coward")
                self.irc.privmsg(self.primarychan, "The coward is dead!")
                self.aliveplayers.remove(ev.source2.nick.lower())
                self.deadplayers.append(ev.source2.nick.lower())
                self.health[ev.source2.nick.lower()] = -1
                if ev.source2.nick.lower() in self._turnleft:
                    self._turnleft.remove(ev.source2.nick.lower())

                self.irc.privmsg("CHANSERV", "AKICK {0} ADD {1} !T 30 FUCKIN REKT - Coward quit, 30 minutes".format(self.primarychan, ev.source2.nick.lower()))

                if len(self.aliveplayers) == 1:
                    self.win(self.aliveplayers[0], stats=False)
                elif self.turn == ev.source2.nick.lower():
                    self.getturn()

                self.countstat(ev.source2.nick, "quit")
    
    # Adds something on the stats
    # ctype = win/loss/quit
    def countstat(self, nick, ctype, amt=0):
        try:
            nick = self.irc.channels[self.primarychan.lower()].users[nick.lower()].account
        except Exception:
            return

        try:
            stat = Statsv2.get(Statsv2.nick == nick.lower())
        except Exception:
            stat = Statsv2.create(nick=nick.lower(), losses=0, quits=0, wins=0, idleouts=0, accepts=0,
            dcaused=0, dreceived=0, easywins=0, fights=0, praises=0, realnick=nick, heals=0, hits=0)
        if ctype == "win":
            stat.wins += 1
        elif ctype == "loss":
            stat.losses += 1
        elif ctype == "quit":
            stat.quits += 1
        elif ctype == "idleout":
            stat.idleouts += 1
        elif ctype == "fight":
            stat.fights += 1
        elif ctype == "gotdmg":
            stat.dreceived += amt
        elif ctype == "dmg":
            stat.dcaused += amt
        elif ctype == "easywin":
            stat.easywins += 1
        elif ctype == "accept":
            stat.accepts += 1
        elif ctype == "praise":
            stat.praises += 1
        elif ctype == "heal":
            stat.heals += 1
        elif ctype == "hit":
            stat.hits += 1

        stat.save()

    def fight(self, cli, fighters, starter, deathmatch = False):
        self.prerules()
        self.countstat(starter, "fight")
        cli.mode(self.primarychan, "+m")
        if deathmatch:
            self.ascii("DEATHMATCH")
        if len(fighters) == 2:
            self.ascii(" V. ".join(fighters).upper(), "straight")
        else:
            cli.privmsg(self.primarychan, " V. ".join(fighters).upper())
        cli.privmsg(self.primarychan, "RULES:")
        cli.privmsg(self.primarychan, "1. Wait your turn. One person at a time.")
        cli.privmsg(self.primarychan, "2. Be a dick about it.")
        cli.privmsg(self.primarychan, " ")
        cli.privmsg(self.primarychan, "Use !hit [nick] to strike.")
        cli.privmsg(self.primarychan, "Use !heal to heal yourself.")
        if not deathmatch:
            cli.privmsg(self.primarychan, "Use !praise [nick] to praise to the donger gods (once per game).")
            cli.privmsg(self.primarychan, "Use '/msg {0} {1}join' to join a game mid-fight.".format(cli.nickname, self.prefix))
        cli.privmsg(self.primarychan, " ")
        
        for fighter in fighters:
            if cli.channels[self.primarychan.lower()].users[fighter.lower()].account in self.accountsseenonthisgame:
                cli.privmsg(self.primarychan, "..... WAIT, WHAT?! Looks like somebody tried to play with two clones")
                cli.mode(self.primarychan, "-m")
                self.allplayers = []
                return

            self.accountsseenonthisgame.append(cli.channels[self.primarychan.lower()].users[fighter.lower()].account)

            self.maxheal[fighter.lower()] = 44
            self.health[fighter.lower()] = 100
            self.allplayers.append(fighter.lower())
            self.aliveplayers.append(fighter.lower())
            if fighter.lower() != starter.lower():
                self.countstat(fighter.lower(), "accept")

        self.prefight()
        self.ascii("FIGHT")
        cli.privmsg(self.primarychan, " ")
        random.shuffle(self.allplayers) # randomize turns

        self.fightstart()

        cli.voice(self.primarychan, fighters)
        self.haspraised = []
        self.deadplayers = []
        self.gamerunning = True
        self.getturn()

    def getturn(self):
        self.verboseoutput("Verbose: Getting turns")

        if self.turnindex > (len(self.allplayers) - 1):
            self.verboseoutput("Verbose: turnindex is greater than allplayers length minus 1 (first instance). Resetting turnindex to 0.")
            self.turnindex = 0

        while self.allplayers[self.turnindex] not in self.aliveplayers:
            self.verboseoutput("Verbose: Advancing turnindex by 1")
            self.turnindex += 1
            if self.turnindex > (len(self.allplayers) - 1):
                self.verboseoutput("Verbose: turnindex is greater than allplayers length minus 1 (second instance). Resetting turnindex to 0.")
                self.turnindex = 0

        if len(self.aliveplayers) == 1:
            self.verboseoutput("Verbose: Only one player left, ending the game")
            self.allplayers = []  # adding this twice! WOO!
            self.win(self.aliveplayers[0])
            return

        self.turn = self.allplayers[self.turnindex]
        self.turnindex += 1
        self.roundstart = time.time()
        self.irc.privmsg(self.primarychan, "It is \002{0}\002's turn".format(self.irc.channels[self.primarychan].users[self.turn].nick))

        # AI
        if self.turn.lower() == self.irc.nickname.lower():
            time.sleep(random.randint(2, 4))
            self.processAI()

    def processAI(self):
        playerstohit = copy.copy(self.aliveplayers)
        playerstohit.remove(self.irc.nickname.lower())
        tohit = random.choice(playerstohit)
        requiredbothp = 44
        requiredtohithp = 24
        if self.health[self.irc.nickname.lower()] < requiredbothp and self.health[tohit] > requiredtohithp:
            self.verboseoutput("Verbose: AI: Less than {0} HP, opponent more than {1}. Healing.".format(requiredbothp, requiredtohithp))
            if self.maxheal[self.irc.nickname.lower()] <= 20:
                self.verboseoutput("Verbose: AI: Not enough chopsticks. Hitting.")
                self.irc.privmsg(self.primarychan, "{0}hit {1}".format(self.prefix, tohit))
                self.hit(self.irc.nickname.lower(), tohit)
            else:
                self.irc.privmsg(self.primarychan, "{0}heal".format(self.prefix))
                self.heal(self.irc.nickname.lower())
        else:
            self.verboseoutput("Verbose: AI: More than {0} HP or opponent less than {1}. Attacking.".format(requiredbothp, requiredtohithp))
            self.irc.privmsg(self.primarychan, "{0}hit {1}".format(self.prefix, tohit))
            self.hit(self.irc.nickname.lower(), tohit)

    def win(self, winner, stats=True):
        self.verbose = False
        self.irc.mode(self.primarychan, "-m")
        self.irc.devoice(self.primarychan, winner)
        if len(self.health) > 2:
            self.irc.privmsg(self.primarychan, "{0} REKT {1}!".format(self.irc.channels[self.primarychan].users[winner.lower()].nick, self._dusers(winner)))
        self.reset()
        if stats:
            self.countstat(self.irc.channels[self.primarychan].users[winner.lower()].nick, "win")
        else:
            self.countstat(self.irc.channels[self.primarychan].users[winner.lower()].nick, "easywin")

    def reset(self):
        self.aliveplayers = []
        self.deadplayers = []
        self.allplayers = []
        self.zombies = []
        self.health = {}
        self.accountsseenonthisgame = []
        self._turnleft = []
        self.gamerunning = False
        self.deathmatch = False
        self.deathmatchpending = {}
        self.turn = 0
        self.turnindex = 0
        self.roundstart = 0
        self.verbose = False
        self.nojoin = False

    def ascii(self, key, font="smslant"): #Only used in fights
        if "not gay".lower() in key.lower():
            key = key.upper()
            key = key.replace('NOT', '')
        self.irc.privmsg(self.primarychan, "\n".join(name for name in Figlet(font).renderText(key.upper()).splitlines()[:-1] if name.strip()))

    # god, this is so shitty
    def randomLine(self, type):
        if type == "excuse":
            file = "excuse_list.txt"
        elif type == "jaden":
            file = "jaden_list.txt"
        elif type == "donger":
            file = "listofdongers.txt"
        if os.path.isfile(os.path.join(os.getcwd(), "stuff", file)):
            with open(os.path.join(os.getcwd(), "stuff", file)) as f:
                return random.choice(list(f))
        else:
            return "Error getting file '{0}'".format(os.path.join(os.getcwd(), "stuff", file))

    def prerules(self):
        pass #For modules which do things before the FIGHT has started, before the rules.
    def prefight(self):
        pass #For modules which do things before the FIGHT has started, after the rules.
    def fightstart(self):
        pass #For modules which do things after the FIGHT ascii, but before the fighting starts.
    def postfight(self):
        pass #For modules which do things after the fight is over

    # For the record: cli = client and ev = event
    def _connect(self, cli, ev):
        # Starting with the SASL authentication
        # Note: If services are down, the bot won't connect
        cli.send("CAP REQ :sasl extended-join account-notify")
        cli.send("AUTHENTICATE PLAIN")

    def _ctcpreply(self, cli, ev):
        if ev.arguments[0] == "PING":
            if not self.lastpingreq:
                return

            current_milli_time = int(time.time() * 1000)
            diff = current_milli_time - int(ev.arguments[1])
            secs = diff / 1000
            cli.privmsg(self.lastpingreq, "{0}: {1} seconds".format(ev.source, secs))
            self.lastpingreq = None

    def _join(self, cli, ev):
        if ev.source2.nick == cli.nickname and ev.target == self.primarychan:
            self.irc.privmsg(ev.target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")

    def _dusers(self, skip):
        players = self.health
        del players[skip]
        pplayers = []
        for player in players:
            pplayers.append(player.lower())
        last = pplayers.pop()
        return "{0} and {1}".format(", ".join(pplayers), last)
        
    def _auth(self, cli, ev):
        cli.send("AUTHENTICATE {0}".format(
        base64.b64encode("{0}\0{0}\0{1}".format(self.config["nickserv-user"],
                                                self.config["nickserv-pass"])
                                                .encode()).decode()))
        cli.send("CAP END")

    def _account(self, cli, ev):
        if ev.target == "*":
            ev.target = None
        for channel in cli.channels.values():
            if ev.source.nick.lower() in channel.users:
                channel.users[ev.source.nick.lower()].account = ev.target

    def _welcome(self, cli, ev):
        cli.join(self.config["channel"])
        cli.join(",".join(*self.auxchans))

    def _timeouts(self):
        while True:
            with self.irc_lock:
                if self.gamerunning and self.turn != "":
                    if time.time() - self.roundstart > 60:
                        self.irc.privmsg(self.primarychan, "\002{0}\002 forfeits due to idle.".format(self.turn))
                        self.irc.devoice(self.primarychan, self.turn)
                        self.countstat(self.turn, "idleout")
                        self.aliveplayers.remove(self.turn)
                        self.deadplayers.append(self.turn)
                        self.health[self.turn] = -1
                        if len(self.aliveplayers) == 1:
                            self.countstat(self.aliveplayers[0], "easywin")
                        self.getturn()
            time.sleep(5)

# Database stuff
database = peewee.SqliteDatabase('dongerdong.db')
database.connect()

class BaseModel(peewee.Model):
    class Meta:
        database = database

# NEW Stats table
class Statsv2(BaseModel):
    nick = peewee.CharField()  # NickServ account of the player
    realnick = peewee.CharField()  # Nickname of the player (not lowercased :P)
    wins = peewee.IntegerField() # Number of REKTs
    losses = peewee.IntegerField() # Number of loses
    quits = peewee.IntegerField() # Number of coward quits
    easywins = peewee.IntegerField() # Number of easy wins (player leaving, etc)
    fights = peewee.IntegerField() # !fight usage [only counted if it started a game]
    accepts = peewee.IntegerField() # !accept usage [only counted if the fight was started] (Total = !fight + !accept)
    dcaused = peewee.IntegerField() # Total amount of damage caused
    dreceived = peewee.IntegerField() # Total amount of damage received
    praises = peewee.IntegerField() # !praise usage
    idleouts = peewee.IntegerField() # >:(
    heals = peewee.IntegerField() # !heal usage
    hits = peewee.IntegerField() # !hit usage

Statsv2.create_table(True) # Here we create the table

# Start donging
dongerdong = Donger()

# Load modules
for module in dongerdong.config["modules"]:
    # get tha modulah
    mod = getattr(importlib.import_module("modules.{0}".format(module)), module)

    # execute tah modulah functioh
    mod.loadModule(dongerdong) # and that's all

while dongerdong.irc.connected and dongerdong.irc.imayreconnect:
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

