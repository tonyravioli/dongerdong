#!/usr/bin/env python3

import pydle
import json
import logging
import threading
import random
import time
from pyfiglet import Figlet

logging.basicConfig(level=logging.DEBUG)

config = json.load(open("config.json"))

BaseClient = pydle.featurize(pydle.features.RFC1459Support, pydle.features.WHOXSupport,
                             pydle.features.AccountSupport, pydle.features.TLSSupport, 
                             pydle.features.IRCv3_1Support)

class Donger(BaseClient):
    def __init__(self, nick, *args, **kwargs):
        super().__init__(nick, *args, **kwargs)
        
        # This is to remember the millions of misc variable names
        self.pendingFights = {} # Pending (not !accepted) fights. ({'player': {'ts': 123, 'deathmatch': False, 'players': [...], 'pendingaccept': [...]}, ...}
        
        # Game vars (Reset these in self.win)
        self.deathmatch = False
        self.gameRunning = False
        self.turnStart = 0
        self.players = {} # Players. {'polsaker': {'hp': 100, 'heals': 5, 'zombie': False, 'praised': False}, ...}
        self.turnlist = [] # Same as self.players, but only the player nicks. Shuffled when the game starts (used to decide turn orders)
        self.currentTurn = -1 # current turn = turnlist[currentTurn]
        
        self.channel = config['channel'] # Main fight channel
        
        timeout_checker = threading.Thread(target = self._timeout)
        timeout_checker.daemon = True
        timeout_checker.start()
        
        # Load ancient wisdom
        self.jaden = json.load(open("wisdom/jaden.json"))
        self.excuses = json.load(open("wisdom/excuses.json"))
        self.dongers = json.load(open("wisdom/dongers.json"))
        
    def on_connect(self):
        super().on_connect()
        self.join(self.channel)
        for chan in config['auxchans']:
            self.join(chan)
    
    @pydle.coroutine
    def on_message(self, target, source, message):
        if message.startswith("!"):
            command = message[1:].split(" ")[0]
            args = message.rstrip().split(" ")[1:]
            
            if target == self.channel: # Dongerdong command
                if command == "fight" and not self.gameRunning:
                    # Check for proper command usage
                    if not args:
                        self.message(target, "Can you read? It is !fight <nick> [othernick] ...")
                        return
                    
                    if not self.users[source]['account']:
                        self.message(target, "You're not identified with NickServ!")
                        return
                    
                    if source in args:
                        self.message(target, "You're trying to fight yourself?")
                        return
                        
                    self.fight([source] + args)
                elif command == "accept" and not self.gameRunning:
                    if not args:
                        self.message(target, "Can you read? It is !accept <nick>")
                        return
                    
                    if not self.users[source]['account']:
                        self.message(target, "You're not identified with NickServ!")
                        return
                    
                    challenger = args[0].lower()
                    
                    # Check if the user was challenged
                    try:
                        if source.lower() not in self.pendingFights[challenger]['pendingaccept']:
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
                    self.pendingFights[challenger]['pendingaccept'].remove(source.lower())
                    
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
                        self.message(target, Figlet("smslant").renderText(' '.join(args)))
                    else:
                        self.message(target, "Text must be 15 characters or less (that was {0} characters). Syntax: !ascii Fuck You".format(len(' '.join(args))))
                elif command == "praise" and self.gameRunning:
                    if source != self.turnlist[self.currentTurn]:
                        self.message(self.channel, "It's not your fucking turn!")
                        return
                    
                    if self.deathmatch:
                        self.message(target, "You can't praise during deathmatches.")
                        return
                    
                    if self.players[source.lower()]['praised']:
                        self.message(target, "You can only praise once per game.")
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
                        self.ascii("whatever")
                        self.heal(ptarget, True) # Critical heal
                    elif praiseroll == 2:
                        self.ascii("fuck you")
                        self.hit(source, ptarget, True)
                    else:
                        self.ascii("NOPE")
                        self.getTurn()
                elif command == "cancel" and not self.gameRunning:
                    self.message(target, "Fight cancelled.")
                    try:
                        del self.pendingFights[args[0].lower()]
                    except KeyError:
                        self.message(target, "You can only !cancel if you started a fight.")
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
                    self.message(target, "\002{0}\002 flew out of the fight".format(source))
                    
                    if not self.pendingFights[args[0].lower()]['pendingaccept']:
                        if len(self.pendingFights[args[0].lower()]['players']) == 1: #only the challenger
                            self.message(target, "Fight cancelled.")
                            del self.pendingFights[args[0].lower()]
                        else:
                            self.start(self.pendingFights[args[0].lower()])
                elif command == "quit" and self.gameRunning:
                    self.cowardQuit(source)
            elif target == config['nick']: # private message
                if command == "join" and self.gameRunning and not self.deathmatch:
                    if source in self.turnlist:
                        self.notice(source, "You already played in this game.")
                        return
                    
                    alivePlayers = [self.players[player]['hp'] for player in self.players if self.players[player]['hp'] > 0]
                    health = sum(alivePlayers) / len(alivePlayers)
                    
                    self.turnlist.append(source)
                    self.players[source.lower()] = {'hp': health, 'heals': 4, 'zombie': False, 'nick': source, 'praised': False}
                    self.message(self.channel, "\002{0}\002 JOINS THE FIGHT (\002{1}\002HP)".format(source.upper(), health))
                    
            # Regular commands
            if command == "dong":
                self.message(target, random.choice(self.dongers))
            elif command == "excuse":
                self.message(target, random.choice(self.excuses))
            elif command == "jaden":
                self.message(target, random.choice(self.jaden))
            elif command == "raise":
                self.message(target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")
            elif command == "lower":
                self.message(target, "┌༼ຈل͜ຈ༽┐ ʟᴏᴡᴇʀ ʏᴏᴜʀ ᴅᴏɴɢᴇʀs ┌༼ຈل͜ຈ༽┐")
    
    def on_quit(self, user, message=None):
        if self.gameRunning:
            self.cowardQuit(user)
    
    def on_part(self, channel, user, message=None):
        if self.gameRunning and channel == self.channel:
            self.cowardQuit(user)
    
    def cowardQuit(self, coward):
        # check if it's playing
        if coward not in self.turnlist:
            return
        if self.players[coward.lower()]['hp'] <= 0: # check if it is alive
            return
        
        self.ascii("coward")
        self.message(self.channel, "The coward is dead!")
        
        self.players[coward.lower()]['hp'] = -1
        
        self.kick(self.channel, coward, "COWARD")
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
    
    def akick(self, user, time=30, message="FUCKING REKT"):
        self.message("ChanServ", "AKICK {0} ADD {1} !T {2} {3}".format(self.channel, user, time, message))
    
    def heal(self, target, critical=False):
        if not self.players[target.lower()]['heals'] and not critical:
            self.message(self.channel, "You can't heal.")
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
        instaroll = random.randint(1, 50) if not self.deathmatch else 666
        critroll = random.randint(1, 12) if not critical else 1
        
        damage = random.randint(18, 35)
        
        if instaroll == 1:
            self.ascii("instakill")
            # remove player
            self.death(target, source)
            self.getTurn()
            return
        if critroll == 1:
            damage *= 2 
            if not critical: # if it isn't an artificial crit, shout
                self.ascii("critical")
        
        self.players[source.lower()]['heals'] = 5
        self.players[target.lower()]['hp'] -= damage
        
        self.message(self.channel, "\002{0}\002 (\002{1}\002HP) deals \002{2}\002 to \002{3}\002 (\002{4}\002HP)".format(
                    source, self.players[source.lower()]['hp'], damage, target, self.players[target.lower()]['hp']))
        
        if self.players[target.lower()]['hp'] <= 0:
            self.death(target, source)
        
        self.getTurn()
        
    def death(self, victim, slayer):
        self.players[victim.lower()]['hp'] = -1
        
        self.set_mode(self.channel, "-v", victim)
        self.ascii("rekt")
        self.message(self.channel, "\002{0}\002 REKT {1}".format(slayer, victim))
        if victim != config['nick']:
            self.kick(self.channel, victim, "REKT")
    
    def start(self, pendingFight):
        self.gameRunning = True
        self.deathmatch = pendingFight['deathmatch']
        self.set_mode(self.channel, "+m")
        if self.deathmatch:
            self.ascii("DEATHMATCH")
            
        if len(pendingFight['players']) == 2:
            self.ascii(" V. ".join(pendingFight['players']), "straight")
        
        self.message(self.channel, "RULES:")
        self.message(self.channel, "1. Wait your turn. One person at a time.")
        self.message(self.channel, "2. Be a dick about it.")
        self.message(self.channel, " ")
        self.message(self.channel, "Use !hit [nick] to strike.")
        self.message(self.channel, "Use !heal to heal yourself.")
        if not self.deathmatch:
            self.message(self.channel, "Use !praise [nick] to praise to the donger gods (once per game).")
            self.message(self.channel, "Use '/msg {0} !join' to join a game mid-fight.".format(config['nick']))
        self.message(self.channel, " ")
        
        # Set up the fight
        for player in pendingFight['players']:
            self.players[player.lower()] = {'hp': 100, 'heals': 4, 'zombie': False, 'nick': player, 'praised': False}
            self.turnlist.append(player)
        
        random.shuffle(self.turnlist)
        self.ascii("FIGHT")
        
        chunky = self.chunks(self.turnlist, 4)
        for chunk in chunky:
            self.set_mode(self.channel, "+" + "v"*len(chunk), *chunk)
            print("+" + "v"*len(chunk), " ".join(chunk))
        
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
        # TODO: stats and stuff
        
        losers = [self.players[player]['nick'] for player in self.players if self.players[player]['hp'] <= 0]
        
        # Clean everything up.
        self.set_mode(self.channel, "-mv", winner)
        
        if len(self.turnlist) > 2 and realwin:
            self.message(self.channel, "{0} REKT {1}".format(self.players[winner]['nick'], ", ".join(losers)).upper())
            
        self.deathmatch = False
        self.gameRunning = False
        self.turnStart = 0
        self.players = {}
        self.turnlist = []
        self.currentTurn = -1
    
    def ascii(self, key, font='smslant'):
        self.message(self.channel, "\n".join([name for name in Figlet(font).renderText(key.upper()).split("\n")[:-1] if name.strip()]))
    
    def fight(self, players, deathmatch=False):
        # Check if those users are in the channel, if they're identified, etc
        accounts = []
        for player in players[:]:
            
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
        
        print(players)

        if len(players) <= 1:
            self.message(self.channel, "You need more than one person to fight!")
            return
        
        self.pendingFights[players[0].lower()] = {
                'ts': time.time(), # Used to calculate the expiry time for a fight
                'deathmatch': deathmatch,
                'pendingaccept': [x.lower() for x in players[1:]],
                'players': [players[0]]
            }
        
        if config['nick'] in players:
            if deathmatch:
                self.message(self.channel, "{0} is not available for a deathmatch".format(config['nick']))
            self.message(self.channel, "YOU WILL SEE")
            self.pendingFights[players[0].lower()]['pendingaccept'].remove(config['nick'].lower())
            self.pendingFights[players[0].lower()]['players'].append(config['nick'])
            if not self.pendingFights[players[0].lower()]['pendingaccept']:
                # Start the game!
                self.start(self.pendingFights[players[0].lower()])
                return
            players.remove(config['nick'])
            
        
        if deathmatch:
            self.message(self.channel, "{0}: \002{1}\002 challenged you to a deathmatch. The loser will be bant for 20 minutes. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
        else:
            self.message(self.channel, "{0}: \002{1}\002 challenged you. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
        
    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i+n]
    
    def _timeout(self):
        while True:
            time.sleep(5)
            if not self.gameRunning and not self.turnStart:
                continue
            
            if time.time() - self.turnStart > 60:
                self.message(self.channel, "\002{0}\002 forfeits due to idle.".format(self.turnlist[self.currentTurn]))
                self.set_mode(self.channel, "-v", self.turnlist[self.currentTurn])
                self.players[self.turnlist[self.currentTurn].lower()]['hp'] = -1
                self.getTurn()

        
client = Donger(config['nick'], sasl_username=config['nickserv_username'],
                sasl_password=config['nickserv_password'])
client.connect(config['server'], config['port'], tls=config['tls'])
try:
    client.handle_forever()
except KeyboardInterrupt:
    if client.connected:
        client.quit(random.choice(client.excuses))
