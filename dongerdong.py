#!/usr/bin/env python3
# -*- coding: utf-8
import pydle
import json
import logging
import threading
import random
import time
from pyfiglet import Figlet
import copy
import operator
import peewee
import importlib
import subprocess
import datetime

loggingFormat = '%(asctime)s %(levelname)s:%(name)s: %(message)s'
logging.basicConfig(level=logging.DEBUG, format=loggingFormat)

config = json.load(open("config.json"))

BaseClient = pydle.featurize(pydle.features.RFC1459Support, pydle.features.WHOXSupport,
                             pydle.features.AccountSupport, pydle.features.TLSSupport, 
                             pydle.features.IRCv3_1Support)

class Donger(BaseClient):
    def __init__(self, nick, *args, **kwargs):
        super().__init__(nick, *args, **kwargs)
        
        # This is to remember the millions of misc variable names
        self.pendingFights = {} # Pending (not !accepted) fights. ({'player': {'ts': 123, 'deathmatch': False, 'versusone': False, 'players': [...], 'pendingaccept': [...]}, ...}
        
        # Game vars (Reset these in self.win)
        self.deathmatch = False
        self.gameRunning = False
        self.turnStart = 0
        self.players = {} # Players. {'polsaker': {'hp': 100, 'heals': 5, 'zombie': False, 'praised': False, 'gdr': 1}, ...}
        self.gdrmodifier = 1 #Modifier for damage reduction adjustment, increase for higher defense, decrease for lower defense
        self.turnlist = [] # Same as self.players, but only the player nicks. Shuffled when the game starts (used to decide turn orders)
        self.accountlist = []  # list of accounts of every player that joined the current fight
        self.currentTurn = -1 # current turn = turnlist[currentTurn]
        
        self.channel = config['channel'] # Main fight channel
        self.currentchannels = [] # List of current channels the bot is in
        self.lastheardfrom = {} # lastheardfrom['Polsaker'] = time.time()
        self.sourcehistory = [] # sourcehistory.append(source)
        self.lastbotfight = time.time()-15 # Last time the bot was in a fight.
        
        self.poke = False  # True if we poked somebody
        
        timeout_checker = threading.Thread(target = self._timeout)
        timeout_checker.daemon = True
        timeout_checker.start()

        self.import_extcmds()

    def on_connect(self):
        super().on_connect()
        self.join(self.channel)
        self.currentchannels.append(self.channel)
        for chan in config['auxchans']:
            self.join(chan)
            self.currentchannels.append(chan)

    @pydle.coroutine
    def on_message(self, target, source, message):
        if message.startswith("!"):
            command = message[1:].split(" ")[0].lower()
            args = message.rstrip().split(" ")[1:]
            
            if target == self.channel: # Dongerdong command
                if (command == "fight" or command == "deathmatch" or command == "duel") and not self.gameRunning:
                    # Check for proper command usage
                    if not args:
                        self.message(target, "Can you read? It is !{0} <nick> [othernick] ...".format(command))
                        return
                    
                    if not self.users[source]['account']:
                        self.message(target, "You're not identified with NickServ!")
                        return
                    
                    if source in args:
                        self.message(target, "You're trying to fight yourself?")
                        return
                       
                    if command == "deathmatch" and len(args) > 1:
                        self.message(target, "Deathmatches are 1v1 only.")
                        return
                    
                    if command == "duel" and len(args) > 1:
                        self.message(target, "Challenges are 1v1 only.")
                        return
                        
                    self.fight([source] + args, True if command == "deathmatch" else False, True if (command == "deathmatch" or command == "duel") else False)
                elif command == "accept" and not self.gameRunning:
                    if not args:
                        self.message(target, "Can you read? It is !accept <nick>")
                        return
                    
                    if not self.users[source]['account']:
                        self.message(target, "You're not identified with NickServ!")
                        return
                    
                    challenger = args[0].lower()
                    opportunist = False
                    
                    # Check if the user was challenged
                    try:
                        if source.lower() not in self.pendingFights[challenger]['pendingaccept']:
                            if "*" in self.pendingFights[challenger]['pendingaccept']:
                                if source.lower() == challenger:
                                    self.message(target, "You're trying to fight yourself?")
                                    return

                                opportunist = True
                            else:
                                self.message(target, "Err... Maybe you meant to say \002!fight {0}\002? They never challenged you.".format(args[0]))
                                return
                    except KeyError: # self.pendingFights[x] doesn't exist
                        self.message(target, "Err... Maybe you meant to say \002!fight {0}\002? They never challenged you.".format(args[0]))
                        return
                    
                    # Check if the challenger is here
                    if args[0].lower() not in map(str.lower, self.channels[self.channel]['users']):
                        self.message(target, "They're not here anymore - maybe they were intimidated by your donger.")
                        del self.pendingFights[challenger] # remove fight.
                        return
                    
                    # OK! This player accepted the fight.
                    self.pendingFights[challenger]['players'].append(source)
                    if not opportunist:
                        self.pendingFights[challenger]['pendingaccept'].remove(source.lower())
                    else:
                        self.pendingFights[challenger]['pendingaccept'].remove('*')
                    
                    # Check if everybody accepted
                    if not self.pendingFights[challenger]['pendingaccept']:
                        # Start the game!
                        self.start(self.pendingFights[challenger])
                elif command == "hit" and self.gameRunning:
                    if source != self.turnlist[self.currentTurn]:
                        self.message(self.channel, "It's not your fucking turn!")
                        return
                    
                    if not args: # pick a random living thing
                        livingThings = [self.players[player]['nick'] for player in self.players if self.players[player]['hp'] > 0 and player != source.lower()]
                        self.hit(source, random.choice(livingThings))
                    else: # The user picked a thing. Check if it is alive
                        if args[0].lower() not in self.players:
                            self.message(self.channel, "You should hit something that is actually playing...")
                            return
                        if args[0].lower() == source.lower():
                            self.message(self.channel, "Stop hitting yourself!")
                            return
                        if self.players[args[0].lower()]['hp'] <= 0:
                            self.message(self.channel, "Do you REALLY want to hit a corpse?")
                            return
                        
                        self.hit(source, self.players[args[0].lower()]['nick'])
                elif command == "heal" and self.gameRunning:
                    if source != self.turnlist[self.currentTurn]:
                        self.message(self.channel, "It's not your fucking turn!")
                        return
                    
                    self.heal(source)
                elif command == "ascii" and not self.gameRunning:
                    if not args:
                        return self.message(self.channel, "Please use some text, like !ascii fuck you")
                    if args and len(' '.join(args)) < 16:
                        self.message(target, self.ascii(' '.join(args)))
                    else:
                        self.message(target, "Text must be 15 characters or less (that was {0} characters). Syntax: !ascii Fuck You".format(len(' '.join(args))))
                elif command == "praise" and self.gameRunning:
                    if source != self.turnlist[self.currentTurn]:
                        self.message(self.channel, "It's not your fucking turn!")
                        return
                    
                    if self.deathmatch:
                        self.message(target, "You can't praise during deathmatches. It's still your turn.")
                        return
                    
                    if self.players[source.lower()]['praised']:
                        self.message(target, "You can only praise once per game. It's still your turn.")
                        return
                    
                    if not args:
                        ptarget = source
                    else:
                        try:
                            ptarget = self.players[args[0].lower()]['nick']
                        except KeyError:
                            self.message(target, "Player not found.")
                            return
                    praiseroll = random.randint(1, 3)
                    self.players[source.lower()]['praised'] = True
                    
                    if config['nick'] in self.turnlist:
                        self.message(target, "You DARE try and suckle my donger while fighting me?!")
                        praiseroll = 2
                        ptarget = self.players[source.lower()]['nick']

                    if praiseroll == 1:
                        self.ascii("WHATEVER")
                        self.heal(ptarget, True) # Critical heal
                    elif praiseroll == 2:
                        self.ascii("FUCK YOU")
                        self.hit(source, ptarget, True)
                    else:
                        self.ascii("NOPE")
                        self.getTurn()
                    self.countStat(source, "praises")

                elif command == "cancel" and not self.gameRunning:
                    try:
                        del self.pendingFights[source.lower()]
                        self.message(target, "Fight cancelled.")
                    except KeyError:
                        self.message(target, "You can only !cancel if you started a fight.")
                        return
                elif command == "reject" and not self.gameRunning:
                    if not args:
                        self.message(target, "Can you read? It's !reject <nick>")
                        return
                        
                    try: # I could just use a try.. except in the .remove(), but I am too lazy to remove this chunk of code
                        if source.lower() not in self.pendingFights[args[0].lower()]['pendingaccept']:
                            self.message(target, "{0} didn't challenge you.".format(args[0]))
                            return
                    except KeyError: # if self.pendingFights[args[0].lower()] doesn't exist.
                        self.message(target, "{0} didn't challenge you.".format(args[0]))
                        return
                    
                    self.pendingFights[args[0].lower()]['pendingaccept'].remove(source.lower())
                    self.countStat(source, "rejects")
                    self.message(target, "\002{0}\002 fled the fight".format(source))
                    
                    if not self.pendingFights[args[0].lower()]['pendingaccept']:
                        if len(self.pendingFights[args[0].lower()]['players']) == 1: #only the challenger
                            self.message(target, "Fight cancelled.")
                            del self.pendingFights[args[0].lower()]
                        else:
                            self.start(self.pendingFights[args[0].lower()])
                elif command == "quit" and self.gameRunning:
                    self.cowardQuit(source)
                elif command == "stats" and not self.gameRunning:
                    if args:
                        nick = args[0]
                    else:
                        nick = source
                    try:
                        nick = self.users[nick]['account']
                    except KeyError:
                        pass
                    
                    stats = self.getStats(nick)
                    
                    if not stats:
                        return self.message(target, "No stats for \002{0}\002.".format(nick))
                    
                    balance = stats.wins - (stats.losses + stats.idleouts + (stats.quits*2))
                    score = balance + (stats.fights + stats.accepts + stats.joins) * config['topmodifier']
                    score +=  (stats.savage + stats.brutal) * 0.15
                    score = round(score, 2)

                    balance = ("+" if balance > 0 else "") + str(balance)
                    
                    
                    top = self.top_dongers()
                    try:
                        ranking = [i for i,x in enumerate(top) if x[0] == stats.nick][0] + 1
                    except IndexError:
                        ranking = 0
                    
                    if ranking == 0:
                        ranking = "Not ranked."
                    elif ranking == 1:
                        ranking = "\003071st\003"
                    elif ranking == 2:
                        ranking = "\003142nd\003"
                    elif ranking == 3:
                        ranking = "\003063rd\003"
                    else:
                        ranking = "{}th".format(ranking)
                    
                    self.message(target, "\002{0}\002's stats: \002{1}\002 wins, \002{2}\002 losses, \002{4}\002 coward quits, \002{5}\002 idle-outs (\002{3}\002), \002{11}\002 kills,"\
                                 " \002{6}\002 !praises, \002{7}\002 fights started, accepted \002{8}\002 fights,"\
                                 " !joined \002{9}\002 fights (\002{10}\002 total fights). Ranked \002{13}\002 (\002{12}\002 points)".format(stats.nick, stats.wins, 
                                    stats.losses, balance, stats.quits, stats.idleouts, stats.praises, 
                                    stats.fights, stats.accepts, stats.joins, 
                                    (stats.fights + stats.accepts + stats.joins), stats.kills, score, ranking))
                elif command in ("top", "shame") and not self.gameRunning:
                    p = self.top_dongers((command == "shame")) # If command == shame, then we're passing "True" into the top_dongers function below (in the "bottom" argument), overriding the default False
                    if not p:
                        return self.message(target, "No top dongers.")
                    c = 1
                    for player in p:
                        score = round(player[1][1] + player[1][0], 2)
                        balance = ("+" if score > 0 else "") + str(score)
                        playernick = "{0}\u200b{1}".format(player[0][0], player[0][1:])

                        self.message(target, "{0} - \002{1}\002 (\002{2}\002)".format(c, playernick.upper(), balance))
                        c += 1
                        if c == 6:
                            break
                    try:
                        self.message(target, "Full stats at {}".format(config['stats-url']))
                    except:
                        pass

            elif target == config['nick']: # private message
                if command == "join" and self.gameRunning and not self.versusone:
                    try:
                        self.users[source]['account']
                    except KeyError:  # ????
                        return self.notice(source, "You don't exist. Try leaving and joining the channel again.")
                    if self.users[source]['account'] in self.accountlist:
                        self.notice(source, "You already played in this game.")
                        return
                    
                    self.accountlist.append(self.users[source]['account'])
                    alivePlayers = [self.players[player]['hp'] for player in self.players if self.players[player]['hp'] > 0]
                    health = int(sum(alivePlayers) / len(alivePlayers))
                    self.countStat(source, "joins")
                    self.turnlist.append(source)
                    self.players[source.lower()] = {'hp': health, 'heals': 4, 'zombie': False, 'nick': source, 'praised': False, 'gdr': 1}
                    self.message(self.channel, "\002{0}\002 JOINS THE FIGHT (\002{1}\002HP)".format(source.upper(), health))
                    self.set_mode(self.channel, "+v", source)
                elif command == "join" and self.versusone:
                    self.notice(source, "You can't join this fight")
                    return

            #Rate limiting
            try:
                if (target != self.channel and # If the command is happening in a place besides the primary channel...
                    (time.time() - self.lastheardfrom[source] < 7) and # And it's been seven seconds since this person has made a command...
                    (source == self.sourcehistory[-2] and source == self.sourcehistory[-1]) and # And they made the last two commands...
                    source not in config['admins']): # And the person is not an administrator...
                    return # Ignore it
            except KeyError:
                pass
            finally:
                self.lastheardfrom[source] = time.time()
                self.sourcehistory.append(source)

            # Regular commands
            if command == "raise":
                self.message(target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")
            elif command == "lower":
                self.message(target, "┌༼ຈل͜ຈ༽┐ ʟᴏᴡᴇʀ ʏᴏᴜʀ ᴅᴏɴɢᴇʀs ┌༼ຈل͜ຈ༽┐")
            elif command == "help":
                self.message(target, "PM'd you my commands.")
                self.message(source, "  More commands available at http://bit.ly/1pG2Hay")
                self.message(source, "Commands available only in {0}:".format(self.channel))
                self.message(source, "  !fight <nickname> [othernicknames]: Challenge another player, or multiple players.")
                self.message(source, "  !duel <nickname>: Same as fight, but only 1v1.")
                self.message(source, "  !deathmatch <nickname>: Same as duel, but the loser is bant for 20 minutes.")
                self.message(source, "  !ascii <text>: Turns any text 15 characters or less into ascii art")
                self.message(source, "  !cancel: Cancels a !fight")
                self.message(source, "  !reject <nick>: Rejects a !fight")
                self.message(source, "  !stats [player]: Outputs player's game stats (or your own stats)")
                self.message(source, "  !top, !shame: Lists the best, or the worst, players")
                self.message(source, "Commands available everywhere:")
                for ch in self.cmdhelp.keys(): #Extended commands help
                    self.message(source, "  !{}: {}".format(ch, self.cmdhelp[ch]))
            elif command == "version":
                try:
                    ver = subprocess.check_output(["git", "describe", "--tags"]).decode().strip()
                    self.message(target, "I am running {} ({})".format(ver,'http://bit.ly/1pG2Hay'))
                except:
                    self.message(target, "I have no idea.")
            elif command == "part" and self.users[source]['account'] in config['admins']:
                if not args:
                    return self.message(target, "You need to list the channel you want me to leave.")
                if args[0] not in self.currentchannels:
                    return self.message(target, "I'm pretty sure I'm not currently in {0}.".format(args[0]))
                if args[0] == self.channel:
                    return self.message(target, "I can't part my primary channel.")
                self.message(target, "Attempting to part {}...".format(args[0]))
                try:
                    self.part(args[0],"NOT ALL THOSE WHO DONGER ARE LOST")
                    self.currentchannels.remove(args[0])
                except:
                    pass
            elif command == "join" and self.users[source]['account'] in config['admins']:
                if not args:
                    return self.message(target, "You need to list the channel you want me to join.")
                if args[0] in self.currentchannels:
                    return self.message(target, "I'm pretty sure I'm already in {0}.".format(args[0]))
                self.message(target, "Attempting to join {}...".format(args[0]))
                try:
                    self.join(args[0])
                    self.currentchannels.append(args[0])
                except:
                    pass
            elif command in self.extcmds: #Extended commands support
                try:
                    if self.cmds[command].adminonly and self.users[source]['account'] not in config['admins']:
                        return
                except AttributeError:
                    pass
                self.cmds[command].doit(self, target, source)

    
    def on_quit(self, user, message=None):
        if self.gameRunning:
            self.cowardQuit(user)
    
    def on_part(self, channel, user, message=None):
        if self.gameRunning and channel == self.channel:
            self.cowardQuit(user)
    
    def top_dongers(self, bottom=False):
        players = Statsv2.select()
        p = {}

        for player in players:
            if (player.fights + player.accepts + player.joins) < 5:
                continue
            if (player.nick == config['nickserv_username']):
                continue
            
            p[player.nick] = [player.wins - (player.losses + player.idleouts + (player.quits*2)), 0]
            
            if 'topmodifier' in config:
                p[player.nick][1] = (player.fights + player.accepts + player.joins) * config['topmodifier']
                p[player.nick][1] += (player.brutal + player.savage) * 0.15
                p[player.nick][1] = round(p[player.nick][1], 2)
        p = sorted(p.items(), key=lambda x: x[1][0] + x[1][1])
        if not bottom:
            p.reverse()
        return p

    
    #def on_nick(self, *args):
    #    print(args)
    
    def cowardQuit(self, coward):
        # check if it's playing
        if coward not in self.turnlist:
            return
        if self.players[coward.lower()]['hp'] <= 0: # check if it is alive
            return
        
        self.ascii("COWARD")
        self.message(self.channel, "The coward is dead!")
        
        self.players[coward.lower()]['hp'] = -1
        
        self.kick(self.channel, coward, "COWARD")
        self.countStat(coward, "quits")

        if self.deathmatch:
            self.akick(coward)
        
        if self.turnlist[self.currentTurn].lower() == coward.lower():
            self.getTurn()
        else:
            aliveplayers = 0
            # TODO: Do this in a neater way
            for p in self.players:
                if self.players[p]['hp'] > 0:
                    aliveplayers += 1
                    survivor = p
            
            if aliveplayers == 1:
                self.win(survivor, False)
    
    def akick(self, user, time=20, message="FUCKING REKT"):
        # Resolve user account
        user = self.users[user]['account']
        self.message("ChanServ", "AKICK {0} ADD {1} !T {2} {3}".format(self.channel, user, time, message))
    
    def heal(self, target, critical=False):
        if not self.players[target.lower()]['heals'] and not critical:
            self.message(self.channel, "You can't heal this turn (but it's still your turn)")
            return
        
        # The max amount of HP you can recover in a single turn depends on how many times you've
        # healed since !hitting. The max number goes down, until you're forced to hit.
        healing = random.randint(22, 44 - (5-self.players[target.lower()]['heals'])*4)
        
        if critical: # If critical heal, override upper healing limit (re roll)
            healing = random.randint(44, 88) # (regular healing*2)
        
        if (healing + self.players[target.lower()]['hp']) > 100: # If healing would bring the player over 100 HP, just set it to 100 HP
            self.players[target.lower()]['hp'] = 100
        else:
            self.players[target.lower()]['hp'] += healing
        
        if not critical:
            self.players[target.lower()]['heals'] -= 1
            
        self.message(self.channel, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002{2}HP\002".format(
                    target, healing, self.players[target.lower()]['hp']))
        self.getTurn()
    
    def hit(self, source, target, critical=False):
        # Rolls.
        instaroll = random.randint(1, 75) if not self.versusone else 666
        critroll = random.randint(1, 12) if not critical else 1
        
        damage = random.randint(18, 35)

        if instaroll == 1:
            self.ascii("INSTAKILL", lineformat="\00304")
            # remove player
            self.death(target, source)
            self.getTurn()
            return
        if critroll == 1:
            damage *= 2 
            if not critical: # If it's not a forced critical hit (via !praise), then announce the critical
                self.ascii("CRITICAL")
        else:
             if not self.players[target.lower()]['gdr'] == 1:
                 damage = int(damage/(self.players[target.lower()]['gdr'] * self.gdrmodifier))
        
        # In case player is hitting themselves
        sourcehealth = self.players[source.lower()]['hp']
        
        self.players[source.lower()]['heals'] = 5
        self.players[target.lower()]['hp'] -= damage
        self.players[target.lower()]['gdr'] += 1

        self.message(self.channel, "\002{0}\002 (\002{1}\002HP) deals \002{2}\002 damage to \002{3}\002 (\002{4}\002HP)".format(
                    source, sourcehealth, damage, target, self.players[target.lower()]['hp']))
        
        if self.players[target.lower()]['hp'] <= 0:
            self.death(target, source)
        
        self.getTurn()
        
    def death(self, victim, slayer):
        self.set_mode(self.channel, "-v", victim)

        if self.players[victim.lower()]['hp'] <= -50:
            self.ascii("BRUTAL")
            self.countStat(slayer, "brutal")
        if self.players[victim.lower()]['hp'] <= -40:
            self.ascii("SAVAGE")
            self.countStat(slayer, "savage")

        self.ascii("REKT" if random.randint(0, 39) else "RELT") # Because 0 is false. The most beautiful line ever written.

        self.players[victim.lower()]['hp'] = -1
        self.message(self.channel, "\002{0}\002 REKT {1}".format(slayer, victim))
        
        if slayer != config['nick']:
            self.countStat(victim, "losses")
        self.countStat(slayer, "kills")
        
        if self.deathmatch:
            self.akick(victim)
        
        if victim != config['nick']:
            self.kick(self.channel, victim, "REKT")
    
    def start(self, pendingFight):
        self.gameRunning = True
        self.pendingFights = {}
        self.deathmatch = pendingFight['deathmatch']
        self.versusone = pendingFight['versusone']
        
        self.set_mode(self.channel, "+m")
        if self.deathmatch:
            self.ascii("DEATHMATCH", font="fire_font-s", lineformat="\00304")
            
        if len(pendingFight['players']) == 2:
            self.ascii(" VS ".join(pendingFight['players']).upper(), "straight")
        
        self.message(self.channel, "RULES:")
        self.message(self.channel, "1. Wait your turn. One person at a time.")
        self.message(self.channel, "2. Be a dick about it.")
        self.message(self.channel, " ")
        self.message(self.channel, "Use !hit [nick] to strike.")
        self.message(self.channel, "Use !heal to heal yourself.")
        if not self.versusone: # Users can't join a fight if it's versusone (duel or deathmatch)
            self.message(self.channel, "Use '/msg {0} !join' to join a game mid-fight.".format(config['nick']))
        if not self.deathmatch: # Users can't praise if it's a deathmatch
            if config['nick'] not in pendingFight['players'] or len(pendingFight['players']) > 2:
                self.message(self.channel, "Use !praise [nick] to praise the donger gods (once per game).")

        self.message(self.channel, " ")
        if not (pendingFight['players'][1] == config['nick'] and len(pendingFight['players']) == 2):
            self.countStat(pendingFight['players'][0], "fights")
        [self.countStat(pl, "accepts") for pl in pendingFight['players'][1:]]
        
        # Set up the fight
        for player in pendingFight['players']:
            if self.deathmatch:
                self.countStat(player, "deathmatches")
            self.accountlist.append(self.users[player.lower()]['account'])
            self.players[player.lower()] = {'hp': 100, 'heals': 5, 'zombie': False, 'nick': player, 'praised': False, 'gdr': 1}
            self.turnlist.append(player)
        
        random.shuffle(self.turnlist)
        self.ascii("FIGHT")
        
        chunky = self.chunks(self.turnlist, 4)
        for chunk in chunky:
            self.set_mode(self.channel, "+" + "v"*len(chunk), *chunk)
        
        # Get the first turn!
        self.getTurn()
    
    def getTurn(self):
        # Step 1: Check for alive players.
        aliveplayers = 0
        # TODO: Do this in a neater way
        for p in self.players:
            if self.players[p]['hp'] > 0:
                aliveplayers += 1
                survivor = p
        
        if aliveplayers == 1: # one survivor, end game.
            self.win(survivor)
            return
        
        # Step 2: next turn
        self.currentTurn += 1
        # Check if that player exists.
        if len(self.turnlist) <= self.currentTurn:
            self.currentTurn = 0
        
        if self.players[self.turnlist[self.currentTurn].lower()]['hp'] > 0: # it's alive!
            self.turnStart = time.time()
            self.poke = False
            self.message(self.channel, "It's \002{0}\002's turn.".format(self.turnlist[self.currentTurn]))
            self.players[self.turnlist[self.currentTurn].lower()]['gdr'] = 1
            if self.turnlist[self.currentTurn] == config['nick']:
                self.processAI()
        else: # It's dead, try again.
            self.getTurn()
    
    def processAI(self):
        myself = self.players[config['nick'].lower()]
        # 1 - We will always hit a player with LESS than 25 HP.
        for i in self.players:
            if i == config['nick'].lower():
                continue
            if self.players[i]['hp'] > 0 and self.players[i]['hp'] < 25:
                self.message(self.channel, "!hit {0}".format(self.players[i]['nick']))
                self.hit(config['nick'], self.players[i]['nick'])
                return
        
        if myself['hp'] < 44 and myself['heals']:
            self.message(self.channel, "!heal")
            self.heal(config['nick'])
        else:
            players = self.turnlist[:]
            players.remove(config['nick'])
            victim = {}
            while not victim: # !!!
                hitting = self.players[random.choice(players).lower()]
                if hitting['hp'] > 0:
                    victim = hitting
            self.message(self.channel, "!hit {0}".format(victim['nick']))
            self.hit(config['nick'], victim['nick'])
    
    def win(self, winner, realwin=True):
        losers = [self.players[player]['nick'] for player in self.players if self.players[player]['hp'] <= 0]
        
        # Clean everything up.
        self.set_mode(self.channel, "-mv", winner)
        
        if len(self.turnlist) > 2 and realwin:
            self.message(self.channel, "{0} REKT {1}".format(self.players[winner]['nick'], ", ".join(losers)).upper())
        # Realwin is only ever false if there's a coward quit.
        if realwin:
            if losers != [config['nick']]:
                self.countStat(winner, "wins")

        if (config['nick'] in losers and len(losers) == 1) or config['nick'] == self.players[winner]['nick']:
            # Set a time so you have to wait a number of seconds
            # before the bot is available to fight again (to prevent
            # people not being able to play due to someone spamming a
            # fight against the bot).
            self.lastbotfight = time.time()

        # Reset fight-related variables
        self.deathmatch = False
        self.versusone = False
        self.gameRunning = False
        self.turnStart = 0
        self.players = {}
        self.turnlist = []
        self.accountlist = []
        self.currentTurn = -1
    
    def ascii(self, key, font='smslant', lineformat=""):
        try:
            if not config['show-ascii-art-text']:
                self.message(self.channel, key)
                return ''
        except KeyError:
            logging.warning("Plz set the show-ascii-art-text config. kthx")
        lines = [lineformat + name for name in Figlet(font).renderText(key).split("\n")[:-1] if name.strip()]
        self.message(self.channel, "\n".join(lines))

    def _rename_user(self, user, new):
        if user in self.users:
            self.users[new] = copy.copy(self.users[user])
            self.users[new]['nickname'] = new
            del self.users[user]
        else:
            self._create_user(new)
            if new not in self.users:
                return

        for ch in self.channels.values():
            # Rename user in channel list.
            if user in ch['users']:
                ch['users'].discard(user)
                ch['users'].add(new)


    def fight(self, players, deathmatch=False, versusone=False):
        # Check if those users are in the channel, if they're identified, etc
        accounts = []
        openSpots = 0
        for player in players[:]:
            if player == "*":
                openSpots += 1
                continue
            
            if player.lower() not in map(str.lower, self.channels[self.channel]['users']):
                self.message(self.channel, "\002{0}\002 is not in the channel.".format(player))
                return

            if not self.users[player]['account']:
                self.message(self.channel, "\002{0}\002 is not identified with NickServ.".format(player))
                return
                
            if self.users[player]['account'] in accounts:
                players.remove(player)
                continue
                
            accounts.append(self.users[player]['account']) # This is kinda to prevent clones playing
        
        if len(players) <= 1:
            self.message(self.channel, "You need more than one person to fight!")
            return
        
        self.pendingFights[players[0].lower()] = {
                'ts': time.time(), # Used to calculate the expiry time for a fight
                'deathmatch': deathmatch,
                'versusone': versusone,
                'pendingaccept': [x.lower() for x in players[1:]],
                'players': [players[0]],
            }
        
        if config['nick'] in players: # If a user is requesting the bot participate in a fight...
            if versusone: # If it's a duel or deathmatch, refuse
                return self.message(self.channel, "{0} is not available for duels or deathmatches".format(config['nick']))
            if (time.time() - self.lastbotfight < 30): # Prevent the bot from fighting with someone within 30 seconds of its last fight with someone. Trying to stop people from taking over the channel
                return self.message(self.channel, "{0} needs a 30 second break before participating in a fight.".format(config['nick']))
            self.message(self.channel, "YOU WILL SEE")
            self.pendingFights[players[0].lower()]['pendingaccept'].remove(config['nick'].lower())
            self.pendingFights[players[0].lower()]['players'].append(config['nick'])
            if not self.pendingFights[players[0].lower()]['pendingaccept']:
                # Start the game!
                self.start(self.pendingFights[players[0].lower()])
                return
            players.remove(config['nick'])
            
        players[:] = [x for x in players if x != '*'] # This magically makes it so you can issue a wildcard challenge to anyone. No one knows how this works but we stopped asking questions long ago.

        if len(players) > 1:
            if deathmatch:
                self.message(self.channel, "{0}: \002{1}\002 challenged you to a deathmatch. The loser will be bant for 20 minutes. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
            else:
                self.message(self.channel, "{0}: \002{1}\002 challenged you. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
        else:
            self.message(self.channel, "\002{0}\002 has challenged anybody willing to fight{1}. To accept, use '!accept {0}'.".format(players[0]," to the death. The loser will be bant for 20 minutes" if deathmatch else ""))

        if openSpots == 1 and len(players) > 1:
            self.message(self.channel, "This fight has an open spot for anybody to join.")
        elif openSpots > 1:
            self.message(self.channel, "This fight has open spots for {0} players to join.".format(openSpots))
        
    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i+n]
    
    def _timeout(self):
        while True:
            time.sleep(5)
            
            if not self.gameRunning or (self.turnStart == 0):
                for i in copy.copy(self.pendingFights):
                    if (time.time() - self.pendingFights[i]['ts'] > 300):
                        self.message(self.channel, "\002{0}\002's challenge has expired.".format(self.pendingFights[i]['players'][0]))
                        del self.pendingFights[i]
                continue
            
            if (time.time() - self.turnStart > 50) and len(self.turnlist) >= (self.currentTurn + 1):
                self.message(self.channel, "\002{0}\002 forfeits due to idle.".format(self.turnlist[self.currentTurn]))
                self.players[self.turnlist[self.currentTurn].lower()]['hp'] = -1
                self.countStat(self.turnlist[self.currentTurn], "idleouts")
                self.kick(self.channel, self.turnlist[self.currentTurn], "WAKE UP SHEEPLE")
                
                aliveplayers = 0
                # TODO: Do this in a neater way
                for p in self.players:
                    if self.players[p]['hp'] > 0:
                        aliveplayers += 1
                        survivor = p
                
                if aliveplayers == 1:
                    self.win(survivor, False)
                else:
                    self.getTurn()
            elif (time.time() - self.turnStart > 30) and len(self.turnlist) >= (self.currentTurn + 1) and not self.poke:
                self.poke = True
                self.message(self.channel, "Wake up, \002{0}\002!".format(self.turnlist[self.currentTurn]))
    
    def _send(self, input):
        super()._send(input)
        if not isinstance(input, str):
            input = input.decode(self.encoding)
        self.logger.debug('>> %s', input.replace('\r\n', ''))

    def _create_user(self, nickname):
        super()._create_user(nickname)
        
        if not self.is_same_nick(self.nickname, nickname):
            if not 'WHOX' in self._isupport:
                if not '.' in nickname:
                    self.whois(nickname)
    
    # Saves information in the stats database.
    # nick = case-sensitive nick.
    # stype = wins/losses/quits/idleouts/kills
    #         fights/accepts/joins
    #         praises
    def countStat(self, nick, stype):
        try:
            nick = self.users[nick]['account']
        except KeyError: # User vanished from earth
            return
        try:
            stat = Statsv2.get(Statsv2.nick == nick)
        except Statsv2.DoesNotExist:
            stat = Statsv2.create(nick=nick, losses=0, quits=0, wins=0, idleouts=0,
                                           accepts=0, fights=0, joins=0,
                                           praises=0, kills=0, savage=0, brutal=0,
                                           deathmatches=0, rejects=0)

        Statsv2.update(**{stype: getattr(stat, stype) + 1}).where(Statsv2.nick == nick).execute()
    
    def getStats(self, nick):
        try:
            return Statsv2.get(Statsv2.nick ** nick)
        except:
            return False

    def import_extcmds(self):
        self.cmdhelp = {}
        try:
            self.extcmds = config['extendedcommands']
        except KeyError:
            self.extcmds = []
            logging.warning("No extended commands found in config.json")
        logging.info("Beginning extended command tests")
        self.cmds = {}
        for command in self.extcmds:
            try: #Let's test these on start...
                cmd = importlib.import_module('extcmd.{}'.format(command))
                logging.info('Loading extended command: {}'.format(command))
                    
                try: # Handling non-existent helptext
                    self.cmdhelp[command] = cmd.helptext
                except AttributeError:
                    logging.warning('No helptext provided for command {}'.format(command))
                    self.cmdhelp[command] = 'A mystery'
                self.cmds[command] = cmd
            except ImportError:
                logging.warning("Failed to import specified extended command: {}".format(command))
                self.extcmds.remove(command)
                logging.warning("Removed command {} from list of available commands. You should fix config.json to remove it from there, too (or just fix the module).".format(command))
        logging.info('Finished loading all the extended commands')

# Database stuff
database = peewee.SqliteDatabase('dongerdong.db')
database.connect()

class BaseModel(peewee.Model):
    class Meta:
        database = database

class Statsv2(BaseModel):
    nick = peewee.CharField()
    
    wins = peewee.IntegerField()
    losses = peewee.IntegerField()
    kills = peewee.IntegerField()
    quits = peewee.IntegerField()
    idleouts = peewee.IntegerField()

    
    deathmatches = peewee.IntegerField() # Deathmatches played (still counted in fights)
    
    rejects = peewee.IntegerField() # fights rejected
    
    fights = peewee.IntegerField() # Games started
    accepts = peewee.IntegerField() # Games accepted
    joins = peewee.IntegerField() # Games joined
        
    praises = peewee.IntegerField()
    
    savage = peewee.IntegerField()  # savage rekts
    brutal = peewee.IntegerField()  # brutal savage rekts
    
    firstplayed = peewee.DateTimeField(default=datetime.datetime.now)
    lastplayed = peewee.DateTimeField()
    
    def save(self, *args, **kwargs):
        self.lastplayed = datetime.datetime.now()
        return super(Statsv2, self).save(*args, **kwargs)

    @classmethod
    def custom_init(cls):
        database.execute_sql('create unique index if not exists stats_unique '
                       'on stats(nick collate nocase)', {})

Statsv2.create_table(True)
try:
    Statsv2.custom_init()
except:
    pass

        
client = Donger(config['nick'], sasl_username=config['nickserv_username'],
                sasl_password=config['nickserv_password'])
client.connect(config['server'], config['port'], tls=config['tls'])
try:
    client.handle_forever()
except KeyboardInterrupt:
    if client.connected:
        try:
            client.quit(importlib.import_module('extcmd.excuse').doit())
        except:
            client.quit('BRB NAPPING')
