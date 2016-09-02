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

logging.basicConfig(level=logging.DEBUG)

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
        self.players = {} # Players. {'polsaker': {'hp': 100, 'heals': 5, 'zombie': False, 'praised': False}, ...}
        self.turnlist = [] # Same as self.players, but only the player nicks. Shuffled when the game starts (used to decide turn orders)
        self.currentTurn = -1 # current turn = turnlist[currentTurn]
        
        self.channel = config['channel'] # Main fight channel

        self.lastheardfrom = {} #lastheardfrom['Polsaker'] = time.time()
        
        timeout_checker = threading.Thread(target = self._timeout)
        timeout_checker.daemon = True
        timeout_checker.start()

        self.import_extcmds()

    def on_connect(self):
        super().on_connect()
        self.join(self.channel)
        for chan in config['auxchans']:
            self.join(chan)

    @pydle.coroutine
    def on_message(self, target, source, message):
        if message.startswith(config['nick']):
            args = message.rstrip().split(" ")
            
            if len(args) > 1 and args[1].lower().startswith("you"):
                self.message(target, "No, {0}{1}".format(source, message.replace(config['nick'], '')))
            else:
                self.message(target, message.replace(config['nick'], source))
            
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
                    
                    if ptarget.lower() == config['nick'].lower():
                        self.message(target, "You try and suckle my donger while fighting me?")
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
                    self.message(target, "Fight cancelled.")
                    try:
                        del self.pendingFights[source.lower()]
                    except KeyError:
                        self.message(target, "You can only !cancel if you started a fight.")
                    except IndexError:
                        self.message(target, "You can only !cancel if you started a fight (Index error).")
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
                elif command == "top" and not self.gameRunning:
                    p = self.top_dongers()
                    
                    if not p:
                        return self.message(target, "No top dongers.")
                    c = 1
                    for player in p:
                        score = round(player[1][1] + player[1][0], 2)
                        balance = ("+" if score > 0 else "") + str(score)
                        self.message(target, "{0} - \002{1}\002 (\002{2}\002)".format(c, player[0].upper(), balance))
                        c += 1
                        if c == 6:
                            break
                    try:
                        self.message(target, "Full stats at {}".format(config['stats-url']))
                    except:
                        pass

                elif command == "version" and not self.gameRunning:
                    try:
                        ver = subprocess.check_output(["git", "describe"]).decode().strip()
                        self.message(target, "I am running {} ({})".format(ver,'http://bit.ly/1pG2Hay'))
                    except:
                        self.message(target, "I have no idea.")

            elif target == config['nick']: # private message
                if command == "join" and self.gameRunning and not self.deathmatch:
                    if source in self.turnlist:
                        self.notice(source, "You already played in this game.")
                        return
                    
                    if self.versusone:
                        self.notice(source, "You can't join this fight")
                        return
                    
                    alivePlayers = [self.players[player]['hp'] for player in self.players if self.players[player]['hp'] > 0]
                    health = int(sum(alivePlayers) / len(alivePlayers))
                    self.countStat(source, "joins")
                    self.turnlist.append(source)
                    self.players[source.lower()] = {'hp': health, 'heals': 4, 'zombie': False, 'nick': source, 'praised': False}
                    self.message(self.channel, "\002{0}\002 JOINS THE FIGHT (\002{1}\002HP)".format(source.upper(), health))
                    self.set_mode(self.channel, "+v", source)

            #Rate limiting
            try:
                if target != self.channel and time.time() - self.lastheardfrom[source] < 7:
                    return
            except KeyError:
                pass
            finally:
                self.lastheardfrom[source] = time.time()

            # Regular commands
            if command == "raise":
                self.message(target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")
            elif command == "lower":
                self.message(target, "┌༼ຈل͜ຈ༽┐ ʟᴏᴡᴇʀ ʏᴏᴜʀ ᴅᴏɴɢᴇʀs ┌༼ຈل͜ຈ༽┐")
            elif command == "help":
                self.message(target, "PM'd you my commands.")
                self.message(source, "Commands available only in {0}:".format(self.channel))
                self.message(source, "  !fight <nickname> [othernicknames]: Challenge another player")
                self.message(source, "  !deathmatch <nickname>: Same as fight, but only 1v1, and loser is bant for 20 minutes.")
                self.message(source, "  !ascii <text>: Turns any text 13 characters or less into ascii art")
                self.message(source, "  !cancel: Cancels a !fight")
                self.message(source, "  !reject <nick>: Cowardly rejects a !fight")
                self.message(source, "  !stats [player]: Outputs player's game stats (or your own stats)")
                self.message(source, "  !top: Shows the three players with most wins")
                self.message(source, "Commands available everywhere:")
                for ch in self.cmdhelp.keys(): #Extended commands help
                    self.message(source, "  !{}: {}".format(ch, self.cmdhelp[ch]))
            elif command in self.extcmds: #Extended commands support
                try:
                    self.message(target,importlib.import_module('extcmd.{}'.format(command)).doit())
                except:
                    raise

    
    def on_quit(self, user, message=None):
        if self.gameRunning:
            self.cowardQuit(user)
    
    def on_part(self, channel, user, message=None):
        if self.gameRunning and channel == self.channel:
            self.cowardQuit(user)
    
    def top_dongers(self):
        players = Stats.select()
        p = {}

        for player in players:
            if (player.fights + player.accepts + player.joins) < 5:
                continue
            if (player.nick == config['nickserv_username']):
                continue
            
            p[player.nick] = [player.wins - (player.losses + player.idleouts + (player.quits*2)), 0]
            
            if 'topmodifier' in config:
                p[player.nick][1] = (player.fights + player.accepts + player.joins) * config['topmodifier']
                p[player.nick][1] = round(p[player.nick][1], 2)
        
        p = sorted(p.items(), key=lambda x: x[1][0] + x[1][1])
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
        
        if self.turnlist[self.currentTurn].lower() == coward:
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
        
        healing = random.randint(22, 44 - (5-self.players[target.lower()]['heals'])*4)
        
        if critical: # If critical heal, override upper healing limit (re roll)
            healing = random.randint(44, 88) # (regular healing*2)
        
        if (healing + self.players[target.lower()]['hp']) > 100:
            self.players[target.lower()]['hp'] = 100
        else:
            self.players[target.lower()]['hp'] += healing
        
        self.players[target.lower()]['heals'] -= 1
            
        self.message(self.channel, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002{2}HP\002".format(
                    target, healing, self.players[target.lower()]['hp']))
        self.getTurn()
    
    def hit(self, source, target, critical=False):
        # Rolls.
        instaroll = random.randint(1, 50) if not self.versusone else 666
        critroll = random.randint(1, 12) if not critical else 1
        
        damage = random.randint(18, 35)
        
        if instaroll == 1:
            self.ascii("INSTAKILL")
            # remove player
            self.death(target, source)
            self.getTurn()
            return
        if critroll == 1:
            damage *= 2 
            if not critical: # if it isn't an artificial crit, shout
                self.ascii("CRITICAL")
        
        self.players[source.lower()]['heals'] = 5
        self.players[target.lower()]['hp'] -= damage

        self.message(self.channel, "\002{0}\002 (\002{1}\002HP) deals \002{2}\002 damage to \002{3}\002 (\002{4}\002HP)".format(
                    source, self.players[source.lower()]['hp'], damage, target, self.players[target.lower()]['hp']))
        
        if self.players[target.lower()]['hp'] <= 0:
            self.death(target, source)
        
        self.getTurn()
        
    def death(self, victim, slayer):
        self.set_mode(self.channel, "-v", victim)

        if self.players[victim.lower()]['hp'] <= -40:
            self.ascii("SAVAGE REKT")
        else:
            self.ascii("REKT")
        
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
        self.deathmatch = pendingFight['deathmatch']
        self.versusone = pendingFight['versusone']
        self.set_mode(self.channel, "+m")
        if self.deathmatch:
            self.ascii("DEATHMATCH")
            
        if len(pendingFight['players']) == 2:
            self.ascii(" V. ".join(pendingFight['players']).upper(), "straight")
        
        self.message(self.channel, "RULES:")
        self.message(self.channel, "1. Wait your turn. One person at a time.")
        self.message(self.channel, "2. Be a dick about it.")
        self.message(self.channel, " ")
        self.message(self.channel, "Use !hit [nick] to strike.")
        self.message(self.channel, "Use !heal to heal yourself.")
        if not self.deathmatch:
            self.message(self.channel, "Use '/msg {0} !join' to join a game mid-fight.".format(config['nick']))
            self.message(self.channel, "Use !praise [nick] to praise to the donger gods (once per game).")

        self.message(self.channel, " ")
        
        self.countStat(pendingFight['players'][0], "fights")
        [self.countStat(pl, "accepts") for pl in pendingFight['players'][1:]]
        
        # Set up the fight
        for player in pendingFight['players']:
            self.players[player.lower()] = {'hp': 100, 'heals': 4, 'zombie': False, 'nick': player, 'praised': False}
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
            self.message(self.channel, "It's \002{0}\002's turn.".format(self.turnlist[self.currentTurn]))
            if self.turnlist[self.currentTurn] == config['nick']:
                self.processAI()
        else: # It's dead, try again.
            self.getTurn()
    
    def processAI(self):
        myself = self.players[config['nick']]
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
            players.remove(config['nick'].lower())
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
        #Realwin is only ever false if there's a coward quit.
        if realwin:
            if losers != [config['nick']]:
                self.countStat(winner, "wins")

        self.deathmatch = False
        self.versusone = False
        self.gameRunning = False
        self.turnStart = 0
        self.players = {}
        self.turnlist = []
        self.currentTurn = -1
    
    def ascii(self, key, font='smslant'):
        lines = [name for name in Figlet(font).renderText(key).split("\n")[:-1] if name.strip()]
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
            
            if player not in self.channels[self.channel]['users']:
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
                'players': [players[0]]
            }
        
        if config['nick'] in players:
            if versusone:
                return self.message(self.channel, "{0} is not available for duels or deathmatches".format(config['nick']))
            self.message(self.channel, "YOU WILL SEE")
            self.pendingFights[players[0].lower()]['pendingaccept'].remove(config['nick'].lower())
            self.pendingFights[players[0].lower()]['players'].append(config['nick'])
            if not self.pendingFights[players[0].lower()]['pendingaccept']:
                # Start the game!
                self.start(self.pendingFights[players[0].lower()])
                return
            players.remove(config['nick'])
            
        players[:] = [x for x in players if x != '*']
        if len(players) > 1:
            if deathmatch:
                self.message(self.channel, "{0}: \002{1}\002 challenged you to a deathmatch. The loser will be bant for 20 minutes. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
            else:
                self.message(self.channel, "{0}: \002{1}\002 challenged you. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
        else:
            if deathmatch:
                self.message(self.channel, "\002{0}\002 has challenged anybody willing to a deathmatch. The loser will be bant for 20 minutes. To accept, use '!accept {0}'.".format(players[0]))
            else:
                self.message(self.channel, "\002{0}\002 has challenged anybody willing to fight. To accept, use '!accept {0}'.".format(players[0]))


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
                continue
            
            if (time.time() - self.turnStart > 60) and len(self.turnlist) >= (self.currentTurn + 1):
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


    def _create_user(self, nickname):
        super()._create_user(nickname)
        
        if not self.is_same_nick(self.nickname, nickname):
            if not 'WHOX' in self._isupport:
                self.whois(nickname)
    
    # Saves information in the stats database.
    # nick = case-sensitive nick.
    # stype = wins/losses/quits/idleouts/kills
    #         fights/accepts/joins
    #         praises
    def countStat(self, nick, stype):
        nick = self.users[nick]['account']
        try:
            stat = Stats.get(Stats.nick == nick)
        except:
            stat = Stats.create(nick=nick, losses=0, quits=0, wins=0, idleouts=0,
                                           accepts=0, fights=0, joins=0,
                                           praises=0, kills=0)

        Stats.update(**{stype: getattr(stat, stype) + 1}).where(Stats.nick == nick).execute()
        #Stats.update(**{stype: getattr(stat, stype) + 1, 'lastedit': int(time.time())}).where(Stats.nick == nick).execute()
    
    def getStats(self, nick):
        try:
            return Stats.get(Stats.nick == nick)
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
        for command in self.extcmds:
            try: #Let's test these on start...
                logging.info('Begin command test: {}'.format(command))
                logging.info(importlib.import_module('extcmd.{}'.format(command)).doit())
                try: # Handling non-existent helptext
                    self.cmdhelp[command] = importlib.import_module('extcmd.{}'.format(command)).helptext
                except AttributeError:
                    logging.warning('No helptext provided for command {}'.format(command))
                    self.cmdhelp[command] = 'A mystery'
                logging.debug('End command test: {}'.format(command))
            except ImportError:
                logging.warning("Failed to import specified extended command: {}".format(command))
                self.extcmds.remove(command)
                logging.warning("Removed command {} from list of available commands. You should fix config.json to remove it from there, too (or just fix the module).".format(command))
        logging.info('Finished all the extended command tests')

# Database stuff
database = peewee.SqliteDatabase('dongerdong.db')
database.connect()

class BaseModel(peewee.Model):
    class Meta:
        database = database

class Stats(BaseModel):
    nick = peewee.CharField()
    
    wins = peewee.IntegerField()
    losses = peewee.IntegerField()
    kills = peewee.IntegerField()
    quits = peewee.IntegerField()
    idleouts = peewee.IntegerField()

    
    fights = peewee.IntegerField() # Games started
    accepts = peewee.IntegerField() # Games accepted
    joins = peewee.IntegerField() # Games joined
        
    praises = peewee.IntegerField()
    
    #lastedit = peewee.IntegerField()
    
    @classmethod
    def custom_init(cls):
        database.execute_sql('create unique index if not exists stats_unique '
                       'on stats(nick collate nocase)', {})

Stats.create_table(True)
try:
    Stats.custom_init()
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
