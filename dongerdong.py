#!/usr/bin/env python3
# -*- coding: utf-8
import asyncio
import pydle
import json
import logging
import threading
import random
import time
from pyfiglet import Figlet
import copy
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
        self.pendingFights = {}  # Pending (not !accepted) fights. ({'player': {'ts': 123, 'deathmatch': False, 'versusone': False, 'players': [...], 'pendingaccept': [...]}, ...}

        # Game vars (Reset these in self.win)
        self.deathmatch = False
        self.gameRunning = False
        self.turnStart = 0
        self.players = {}  # Players. {'polsaker': {'hp': 100, 'heals': 5, 'zombie': False, 'praised': False, 'gdr': 1}, ...}
        self.gdrmodifier = 1  # Modifier for damage reduction adjustment, increase for higher defense, decrease for lower defense
        self.turnlist = []  # Same as self.players, but only the player nicks. Shuffled when the game starts (used to decide turn orders)
        self.accountlist = []  # list of accounts of every player that joined the current fight
        self.currentTurn = -1  # current turn = turnlist[currentTurn]

        self.channel = config['channel']  # Main fight channel
        self.currentchannels = []  # List of current channels the bot is in
        self.lastheardfrom = {}  # lastheardfrom['Polsaker'] = time.time()
        self.sourcehistory = []  # sourcehistory.append(source)
        self.lastbotfight = time.time() - 15  # Last time the bot was in a fight.

        self.poke = False  # True if we poked somebody

        self.currgamerecord = None  # GameStats object for current game

        self.eventloop.create_task(self._timeout())

        self.import_extcmds()

    async def on_connect(self):
        await super().on_connect()
        await self.join(self.channel)
        self.currentchannels.append(self.channel)
        for chan in config.get('auxchans', []):
            await self.join(chan)
            self.currentchannels.append(chan)

    async def on_message(self, target, source, message):
        if message.startswith("!"):
            command = message[1:].split(" ")[0].lower()
            args = message.rstrip().split(" ")[1:]

            if target == self.channel:  # Dongerdong command
                if (command == "fight" or command == "deathmatch" or command == "duel") and not self.gameRunning:
                    # Check for proper command usage
                    if not args:
                        await self.message(target, "Can you read? It is !{0} <nick>{1}".format(command, " [othernick] [...] " if command == "fight" else ""))
                        return

                    if not self.users[source]['account']:
                        await self.message(target, "You're not identified with NickServ!")
                        return

                    if source in args:
                        await self.message(target, "You're trying to fight yourself?")
                        return

                    if command == "deathmatch" and len(args) > 1:
                        await self.message(target, "Deathmatches are 1v1 only.")
                        return

                    if command == "duel" and len(args) > 1:
                        await self.message(target, "Challenges are 1v1 only.")
                        return

                    await self.fight([source] + args, True if command == "deathmatch" else False, True if (command == "deathmatch" or command == "duel") else False)
                elif command == "accept" and not self.gameRunning:
                    if not args:
                        await self.message(target, "Can you read? It is !accept <nick>")
                        return

                    if not self.users[source]['account']:
                        await self.message(target, "You're not identified with NickServ!")
                        return

                    challenger = args[0].lower()
                    opportunist = False

                    # Check if the user was challenged
                    try:
                        if source.lower() not in self.pendingFights[challenger]['pendingaccept']:
                            if "*" in self.pendingFights[challenger]['pendingaccept']:
                                if source.lower() == challenger:
                                    await self.message(target, "You're trying to fight yourself?")
                                    return

                                opportunist = True
                            else:
                                await self.message(target, "Err... Maybe you meant to say \002!fight {0}\002? They never challenged you.".format(args[0]))
                                return
                    except KeyError:  # self.pendingFights[x] doesn't exist
                        await self.message(target, "Err... Maybe you meant to say \002!fight {0}\002? They never challenged you.".format(args[0]))
                        return

                    # Check if the challenger is here
                    if args[0].lower() not in map(str.lower, self.channels[self.channel]['users']):
                        await self.message(target, "They're not here anymore - maybe they were intimidated by your donger.")
                        del self.pendingFights[challenger]  # remove fight.
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
                        await self.start(self.pendingFights[challenger])
                elif command == "hit" and self.gameRunning:
                    if source != self.turnlist[self.currentTurn]:
                        await self.message(self.channel, "It's not your fucking turn!")
                        return

                    if not args:  # pick a random living thing
                        livingThings = [self.players[player]['nick'] for player in self.players if self.players[player]['hp'] > 0 and player != source.lower()]
                        await self.hit(source, random.choice(livingThings))
                    else:  # The user picked a thing. Check if it is alive
                        if args[0].lower() not in self.players:
                            await self.message(self.channel, "You should hit something that is actually playing...")
                            return
                        if args[0].lower() == source.lower():
                            await self.message(self.channel, "Stop hitting yourself!")
                            return
                        if self.players[args[0].lower()]['hp'] <= 0:
                            await self.message(self.channel, "Do you REALLY want to hit a corpse?")
                            return

                        await self.hit(source, self.players[args[0].lower()]['nick'])
                elif command == "heal" and self.gameRunning:
                    if source != self.turnlist[self.currentTurn]:
                        await self.message(self.channel, "It's not your fucking turn!")
                        return

                    await self.heal(source)
                elif command == "ascii" and not self.gameRunning:
                    if not args:
                        return await self.message(self.channel, "Please use some text, like !ascii fuck you")
                    if args and len(' '.join(args)) < 16:
                        await self.message(target, await self.ascii(' '.join(args)))
                    else:
                        await self.message(target, "Text must be 15 characters or less (that was {0} characters). Syntax: !ascii Fuck You".format(len(' '.join(args))))
                elif command == "praise" and self.gameRunning:
                    if source != self.turnlist[self.currentTurn]:
                        await self.message(self.channel, "It's not your fucking turn!")
                        return

                    if self.deathmatch:
                        await self.message(target, "You can't praise during deathmatches. It's still your turn.")
                        return

                    if self.players[source.lower()]['praised']:
                        await self.message(target, "You can only praise once per game. It's still your turn.")
                        return

                    if not args:
                        ptarget = source
                    else:
                        try:
                            ptarget = self.players[args[0].lower()]['nick']
                        except KeyError:
                            await self.message(target, "Player not found.")
                            return
                    praiseroll = random.randint(1, 3)
                    self.players[source.lower()]['praised'] = True
                    if self.deathmatch or self.versusone:
                        if source.lower() == self.currgamerecord.player1:
                            self.currgamerecord.player1_praiseroll = praiseroll
                        else:
                            self.currgamerecord.player2_praiseroll = praiseroll

                    if config['nick'] in self.turnlist:
                        await self.message(target, "You DARE try and suckle my donger while fighting me?!")
                        praiseroll = 2
                        ptarget = self.players[source.lower()]['nick']

                    if praiseroll == 1:
                        await self.ascii("WHATEVER")
                        await self.heal(ptarget, True)  # Critical heal
                    elif praiseroll == 2:
                        await self.ascii("FUCK YOU")
                        await self.hit(source, ptarget, True)
                    else:
                        await self.ascii("NOPE")
                        await self.getTurn()
                    self.countStat(source, "praises")

                elif command == "cancel" and not self.gameRunning:
                    try:
                        del self.pendingFights[source.lower()]
                        await self.message(target, "Fight cancelled.")
                    except KeyError:
                        await self.message(target, "You can only !cancel if you started a fight.")
                        return
                elif command == "reject" and not self.gameRunning:
                    if not args:
                        await self.message(target, "Can you read? It's !reject <nick>")
                        return

                    try:  # I could just use a try.. except in the .remove(), but I am too lazy to remove this chunk of code
                        if source.lower() not in self.pendingFights[args[0].lower()]['pendingaccept']:
                            await self.message(target, "{0} didn't challenge you.".format(args[0]))
                            return
                    except KeyError:  # if self.pendingFights[args[0].lower()] doesn't exist.
                        await self.message(target, "{0} didn't challenge you.".format(args[0]))
                        return

                    self.pendingFights[args[0].lower()]['pendingaccept'].remove(source.lower())
                    await self.message(target, "\002{0}\002 fled the fight".format(source))

                    if not self.pendingFights[args[0].lower()]['pendingaccept']:
                        if len(self.pendingFights[args[0].lower()]['players']) == 1:  # only the challenger
                            await self.message(target, "Fight cancelled.")
                            del self.pendingFights[args[0].lower()]
                        else:
                            await self.start(self.pendingFights[args[0].lower()])
                elif command == "quit" and self.gameRunning:
                    await self.cowardQuit(source)
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
                        return await self.message(target, "No stats for \002{0}\002.".format(nick))

                    balance = stats.wins - (stats.losses + stats.idleouts + (stats.quits * 2))

                    balance = ("+" if balance > 0 else "") + str(balance)

                    top = self.top_dongers().dicts()
                    ranking = next((index for (index, d) in enumerate(top) if d['name'].lower() == stats.name.lower()), -1) + 1

                    if ranking == 0:
                        ranking = "\002Not ranked\002."
                    elif ranking == 1:
                        ranking = "Ranked \002\003071st\003\002"
                    elif ranking == 2:
                        ranking = "Ranked \002\003142nd\003\002"
                    elif ranking == 3:
                        ranking = "Ranked \002\003063rd\003\002"
                    else:
                        ranking = "Ranked \002{}th\002".format(ranking)
                    #try:
                    #    d0 = stats.lastplayed.date()
                    #    today = datetime.datetime.now().date()
                    #    delta = today - d0
                    #    aelo = stats.elo - (int(delta.days)*2) #aelo (adjusted ELO) is equal to normal ELO minus (days since last played times two)
                    #except:
                    #    await self.message(target, "You activated the special secret 1331589151jvlhjv feature!")

                    await self.message(target, "\002{0}\002's stats: \002{1}\002 wins, \002{2}\002 losses, \002{4}\002 coward quits, \002{5}\002 idle-outs (\002{3}\002), "
                                         "\002{6}\002 !praises, \002{7}\002 matches, \002{8}\002 deathmatches (\002{9}\002 total). "
                                         "{11} (\002{10}\002 points)"
                                         .format(stats.name, stats.wins, stats.losses, balance, stats.quits, stats.idleouts, stats.praises,
                                                 stats.matches, stats.deathmatches, (stats.matches + stats.deathmatches), stats.elo, ranking))
                elif command in ("top", "shame") and not self.gameRunning:
                    p = self.top_dongers((command == "shame")).limit(5)  # If command == shame, then we're passing "True" into the top_dongers function below (in the "bottom" argument), overriding the default False
                    if not p:
                        return await self.message(target, "No top dongers.")
                    c = 1
                    for player in p:
                        playernick = "{0}\u200b{1}".format(player.name[0], player.name[1:])

                        await self.message(target, "{0} - \002{1}\002 (\002{2}\002)".format(c, playernick.upper(), player.elo))
                        c += 1

                    if config.get('stats-url'):
                        await self.message(target, "Full stats at {}".format(config['stats-url']))

            elif target == config['nick']:  # private message
                if command == "join" and self.gameRunning and not self.versusone:
                    try:
                        self.users[source]['account']
                    except KeyError:  # ????
                        return await self.notice(source, "You don't exist. Try leaving and joining the channel again.")
                    if self.users[source]['account'] in self.accountlist:
                        await self.notice(source, "You already played in this game.")
                        return

                    self.accountlist.append(self.users[source]['account'])
                    alivePlayers = [self.players[player]['hp'] for player in self.players if self.players[player]['hp'] > 0]
                    health = int(sum(alivePlayers) / len(alivePlayers))
                    self.turnlist.append(source)
                    self.players[source.lower()] = {'hp': health, 'heals': 4, 'zombie': False, 'nick': source, 'praised': False, 'gdr': 1}
                    await self.message(self.channel, "\002{0}\002 JOINS THE FIGHT (\002{1}\002HP)".format(source.upper(), health))
                    await self.set_mode(self.channel, "+v", source)
                elif command == "join" and self.versusone:
                    await self.notice(source, "You can't join this fight")
                    return

            # Rate limiting
            try:
                if target != self.channel:  # If the command is happening in a place besides the primary channel...
                    if time.time() - self.lastheardfrom[source] < 7:  # And it's been seven seconds since this person has made a command...
                        if source == self.sourcehistory[-2] and source == self.sourcehistory[-1]:  # And they made the last two commands...
                            if source not in config['admins']:  # And the person is not an administrator...
                                return  # Ignore it
            except KeyError:
                pass
            finally:
                self.lastheardfrom[source] = time.time()
                self.sourcehistory.append(source)

            # Regular commands
            if command == "raise":
                await self.message(target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")
            elif command == "lower":
                await self.message(target, "┌༼ຈل͜ຈ༽┐ ʟᴏᴡᴇʀ ʏᴏᴜʀ ᴅᴏɴɢᴇʀs ┌༼ຈل͜ຈ༽┐")
            elif command == "help":
                await self.message(target, "PM'd you my commands.")
                await self.message(source, "  More commands available at http://bit.ly/1pG2Hay")
                await self.message(source, "Commands available only in {0}:".format(self.channel))
                await self.message(source, "  !fight <nickname> [othernicknames]: Challenge another player, or multiple players.")
                await self.message(source, "  !duel <nickname>: Same as fight, but only 1v1.")
                await self.message(source, "  !deathmatch <nickname>: Same as duel, but the loser is bant for 20 minutes.")
                await self.message(source, "  !ascii <text>: Turns any text 15 characters or less into ascii art")
                await self.message(source, "  !cancel: Cancels a !fight")
                await self.message(source, "  !reject <nick>: Rejects a !fight")
                await self.message(source, "  !stats [player]: Outputs player's game stats (or your own stats)")
                await self.message(source, "  !top, !shame: Lists the best, or the worst, players")
                await self.message(source, "Commands available everywhere:")
                for ch in self.cmdhelp.keys():  # Extended commands help
                    await self.message(source, "  !{}: {}".format(ch, self.cmdhelp[ch]))
            elif command == "version":
                try:
                    ver = subprocess.check_output(["git", "describe", "--tags"]).decode().strip()
                    await self.message(target, "I am running {} ({})".format(ver, 'http://bit.ly/1pG2Hay'))
                except:
                    await self.message(target, "I have no idea.")
            elif command == "part" and self.users[source]['account'] in config['admins']:
                if not args:
                    return await self.message(target, "You need to list the channel you want me to leave.")
                if args[0] not in self.currentchannels:
                    return await self.message(target, "I'm pretty sure I'm not currently in {0}.".format(args[0]))
                if args[0] == self.channel:
                    return await self.message(target, "I can't part my primary channel.")
                await self.message(target, "Attempting to part {}...".format(args[0]))
                try:
                    await self.part(args[0], "NOT ALL THOSE WHO DONGER ARE LOST")
                    self.currentchannels.remove(args[0])
                except:
                    pass
            elif command == "join" and self.users[source]['account'] in config['admins']:
                if not args:
                    return await self.message(target, "You need to list the channel you want me to join.")
                if args[0] in self.currentchannels:
                    return await self.message(target, "I'm pretty sure I'm already in {0}.".format(args[0]))
                await self.message(target, "Attempting to join {}...".format(args[0]))
                try:
                    await self.join(args[0])
                    self.currentchannels.append(args[0])
                except:
                    pass
            elif command in self.extcmds:  # Extended commands support
                try:
                    if self.cmds[command].adminonly and self.users[source]['account'] not in config['admins']:
                        return
                except AttributeError:
                    pass
                await self.cmds[command].doit(self, target, source)

    async def on_quit(self, user, message=None):
        if self.gameRunning:
            await self.cowardQuit(user)

    async def on_part(self, channel, user, message=None):
        if self.gameRunning and channel == self.channel:
            await self.cowardQuit(user)

    def top_dongers(self, bottom=False):
        players = PlayerStats.select().where((PlayerStats.matches + PlayerStats.deathmatches) >= 15)
        if bottom:
            players = players.order_by(PlayerStats.elo.asc())
        else:
            players = players.order_by(PlayerStats.elo.desc())

        return players

    async def cowardQuit(self, coward):
        # check if it's playing
        if coward not in self.turnlist:
            return
        if self.players[coward.lower()]['hp'] <= 0:  # check if it is alive
            return

        await self.ascii("COWARD")
        await self.message(self.channel, "The coward is dead!")

        self.players[coward.lower()]['hp'] = -1

        await self.kick(self.channel, coward, "COWARD")
        self.countStat(coward, "quits")

        if self.deathmatch:
            await self.akick(coward)

        if self.turnlist[self.currentTurn].lower() == coward.lower():
            await self.getTurn()
        else:
            aliveplayers = 0
            # TODO: Do this in a neater way
            for p in self.players:
                if self.players[p]['hp'] > 0:
                    aliveplayers += 1
                    survivor = p

            if aliveplayers == 1:
                await self.win(survivor, False)

    async def akick(self, user, time=20, message="FUCKING REKT"):
        # Resolve user account
        user = self.users[user]['account']
        await self.message("ChanServ", "AKICK {0} ADD {1} !T {2} {3}".format(self.channel, user, time, message))

    async def heal(self, target, critical=False):
        if not self.players[target.lower()]['heals'] and not critical:
            await self.message(self.channel, "You can't heal this turn (but it's still your turn)")
            return

        # The max amount of HP you can recover in a single turn depends on how many times you've
        # healed since !hitting. The max number goes down, until you're forced to hit.
        healing = random.randint(22, 44 - (5 - self.players[target.lower()]['heals']) * 4)

        if critical:  # If critical heal, override upper healing limit (re roll)
            healing = random.randint(44, 88)  # (regular healing*2)

        if (healing + self.players[target.lower()]['hp']) > 100:  # If healing would bring the player over 100 HP, just set it to 100 HP
            self.players[target.lower()]['hp'] = 100
        else:
            self.players[target.lower()]['hp'] += healing

        if not critical:
            self.players[target.lower()]['heals'] -= 1

        if not critical:
            self.countStat(target, "heals")

        self.countStat(target, "totheal", healing)

        if self.deathmatch or self.versusone:  # stats
            if target.lower() == self.currgamerecord.player1:
                self.currgamerecord.player1_heals += 1
                self.currgamerecord.player1_totheal += healing
                if critical:
                    self.currgamerecord.player1_praiseroll = healing
            else:
                self.currgamerecord.player2_heals += 1
                self.currgamerecord.player2_totheal += healing
                if critical:
                    self.currgamerecord.player2_praiseroll = +healing

        await self.message(self.channel, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002{2}HP\002".format(
            target, healing, self.players[target.lower()]['hp']))
        await self.getTurn()

    async def hit(self, source, target, critical=False):
        # Rolls.
        instaroll = random.randint(1, 75) if not self.versusone else 666
        critroll = random.randint(1, 12) if not critical else 1
        damage = random.randint(18, 35)

        if instaroll == 1:
            await self.ascii("INSTAKILL", lineformat="\00304")
            # remove player
            await self.death(target, source)
            await self.getTurn()
            return
        if critroll == 1:
            damage *= 2
            if not critical:  # If it's not a forced critical hit (via !praise), then announce the critical
                await self.ascii("CRITICAL")
                self.countStat(source, "crits")
        else:
            if not self.players[target.lower()]['gdr'] == 1:
                damage = int(damage / (self.players[target.lower()]['gdr'] * self.gdrmodifier))

        # In case player is hitting themselves
        sourcehealth = self.players[source.lower()]['hp']

        self.players[source.lower()]['heals'] = 5
        self.players[target.lower()]['hp'] -= damage
        self.players[target.lower()]['gdr'] += 1
        self.countStat(source, "hits")
        self.countStat(source, "totdmg", damage)

        if self.deathmatch or self.versusone:  # stats
            if source.lower() == self.currgamerecord.player1:
                self.currgamerecord.player1_hits += 1
                self.currgamerecord.player1_totdmg += damage
                if critroll == 1:
                    self.currgamerecord.player1_crits += 1
                if critical:
                    self.currgamerecord.player1_praiseroll = -damage
            else:
                self.currgamerecord.player2_hits += 1
                self.currgamerecord.player2_totdmg += damage
                if critroll == 1:
                    self.currgamerecord.player2_crits += 1
                if critical:
                    self.currgamerecord.player2_praiseroll = -damage

        await self.message(self.channel, "\002{0}\002 (\002{1}\002HP) deals \002{2}\002 damage to \002{3}\002 (\002{4}\002HP)".format(
            source, sourcehealth, damage, target, self.players[target.lower()]['hp']))

        if self.players[target.lower()]['hp'] <= 0:
            await self.death(target, source)

        await self.getTurn()

    async def death(self, victim, slayer):
        if self.deathmatch or self.versusone:
            if victim == self.currgamerecord.player1:
                self.currgamerecord.winner = 2
            else:
                self.currgamerecord.winner = 1
        await self.set_mode(self.channel, "-v", victim)

        if self.players[victim.lower()]['hp'] <= -50:
            await self.ascii("BRUTAL")
        if self.players[victim.lower()]['hp'] <= -40:
            await self.ascii("SAVAGE")

        await self.ascii("REKT" if random.randint(0, 39) else "RELT")  # Because 0 is false. The most beautiful line ever written.

        self.players[victim.lower()]['hp'] = -1
        await self.message(self.channel, "\002{0}\002 REKT {1}".format(slayer, victim))

        if slayer != config['nick']:
            self.countStat(victim, "losses")

        if self.deathmatch:
            await self.akick(victim)

        if victim != config['nick']:
            await self.kick(self.channel, victim, "REKT")

    async def start(self, pendingFight):
        self.gameRunning = True
        self.pendingFights = {}
        self.deathmatch = pendingFight['deathmatch']
        self.versusone = pendingFight['versusone']

        if self.deathmatch or self.versusone:
            self.currgamerecord = GameStats.create(player1=pendingFight['players'][0],
                                                   player2=pendingFight['players'][1])

        await self.set_mode(self.channel, "+m")
        if self.deathmatch:
            await self.ascii("DEATHMATCH", font="fire_font-s", lineformat="\00304")

        if len(pendingFight['players']) == 2:
            await self.ascii(" VS ".join(pendingFight['players']).upper(), "straight")

        await self.message(self.channel, "RULES:")
        await self.message(self.channel, "1. Wait your turn. One person at a time.")
        await self.message(self.channel, "2. Be a dick about it.")
        await self.message(self.channel, " ")
        await self.message(self.channel, "Use !hit [nick] to strike.")
        await self.message(self.channel, "Use !heal to heal yourself.")
        if not self.versusone:  # Users can't join a fight if it's versusone (duel or deathmatch)
            await self.message(self.channel, "Use '/msg {0} !join' to join a game mid-fight.".format(config['nick']))
        if not self.deathmatch:  # Users can't praise if it's a deathmatch
            if config['nick'] not in pendingFight['players'] or len(pendingFight['players']) > 2:
                await self.message(self.channel, "Use !praise [nick] to praise the donger gods (once per game).")

        await self.message(self.channel, " ")

        # Set up the fight
        for player in pendingFight['players']:
            if self.deathmatch:
                self.countStat(player, "deathmatches")
            elif self.versusone:
                self.countStat(player, "matches")
            self.accountlist.append(self.users[player.lower()]['account'])
            self.players[player.lower()] = {'hp': 100, 'heals': 5, 'zombie': False, 'nick': player, 'praised': False, 'gdr': 1}
            self.turnlist.append(player)

        random.shuffle(self.turnlist)
        await self.ascii("FIGHT")

        chunky = self.chunks(self.turnlist, 4)
        for chunk in chunky:
            await self.set_mode(self.channel, "+" + "v" * len(chunk), *chunk)

        # Get the first turn!
        await self.getTurn()

    async def getTurn(self):
        if self.deathmatch or self.versusone:
            self.currgamerecord.turns += 1

        # Step 1: Check for alive players.
        aliveplayers = 0
        # TODO: Do this in a neater way
        for p in self.players:
            if self.players[p]['hp'] > 0:
                aliveplayers += 1
                survivor = p

        if aliveplayers == 1:  # one survivor, end game.
            await self.win(survivor)
            return

        [self.countStat(pl, "turns") for pl in self.players]
        # Step 2: next turn
        self.currentTurn += 1
        # Check if that player exists.
        if len(self.turnlist) <= self.currentTurn:
            self.currentTurn = 0

        if self.players[self.turnlist[self.currentTurn].lower()]['hp'] > 0:  # it's alive!
            self.turnStart = time.time()
            self.poke = False
            await self.message(self.channel, "It's \002{0}\002's turn.".format(self.turnlist[self.currentTurn]))
            self.players[self.turnlist[self.currentTurn].lower()]['gdr'] = 1
            if self.turnlist[self.currentTurn] == config['nick']:
                await self.processAI()
        else:  # It's dead, try again.
            await self.getTurn()

    async def processAI(self):
        myself = self.players[config['nick'].lower()]
        # 1 - We will always hit a player with LESS than 25 HP.
        for i in self.players:
            if i == config['nick'].lower():
                continue
            if self.players[i]['hp'] > 0 and self.players[i]['hp'] < 25:
                await self.message(self.channel, "!hit {0}".format(self.players[i]['nick']))
                await self.hit(config['nick'], self.players[i]['nick'])
                return

        if myself['hp'] < 44 and myself['heals']:
            await self.message(self.channel, "!heal")
            await self.heal(config['nick'])
        else:
            players = self.turnlist[:]
            players.remove(config['nick'])
            victim = {}
            while not victim:  # !!!
                hitting = self.players[random.choice(players).lower()]
                if hitting['hp'] > 0:
                    victim = hitting
            await self.message(self.channel, "!hit {0}".format(victim['nick']))
            await self.hit(config['nick'], victim['nick'])

    async def win(self, winner, realwin=True):
        losers = [self.players[player]['nick'] for player in self.players if self.players[player]['hp'] <= 0]

        # Clean everything up.
        await self.set_mode(self.channel, "-mv", winner)

        if len(self.turnlist) > 2 and realwin:
            await self.message(self.channel, "{0} REKT {1}".format(self.players[winner]['nick'], ", ".join(losers)).upper())
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

        if self.deathmatch or self.versusone:
            self.currgamerecord.save()
            # calculate ELO
            player1 = PlayerStats.get(PlayerStats.name == self.users[winner]['account'])
            player2 = PlayerStats.get(PlayerStats.name == self.users[losers[0]]['account'])

            r1 = 10 ** (player1.elo / 400)
            r2 = 10 ** (player2.elo / 400)

            e1 = r1 / (r1 + r2)
            e2 = r2 / (r1 + r2)

            k1 = 30 if (player1.matches + player1.deathmatches) < 20 else 20
            k2 = 30 if (player2.matches + player2.deathmatches) < 20 else 20

            if self.deathmatch:
                k1 += 5
                k2 += 5

            player1.elo = int(round(player1.elo + k1 * (1 - e1), 0))
            player2.elo = int(round(player2.elo + k2 * (0 - e2), 0))
            player1.save()
            player2.save()

        # Reset fight-related variables
        self.deathmatch = False
        self.versusone = False
        self.gameRunning = False
        self.turnStart = 0
        self.players = {}
        self.turnlist = []
        self.accountlist = []
        self.currentTurn = -1

    async def ascii(self, key, font='smslant', lineformat=""):
        try:
            if not config['show-ascii-art-text']:
                await self.message(self.channel, key)
                return ''
        except KeyError:
            logging.warning("Plz set the show-ascii-art-text config. kthx")
        lines = [lineformat + name for name in Figlet(font).renderText(key).split("\n")[:-1] if name.strip()]
        await self.message(self.channel, "\n".join(lines))

    async def _rename_user(self, user, new):
        if user in self.users:
            self.users[new] = copy.copy(self.users[user])
            self.users[new]['nickname'] = new
            del self.users[user]
        else:
            await self._create_user(new)
            if new not in self.users:
                return

        for ch in self.channels.values():
            # Rename user in channel list.
            if user in ch['users']:
                ch['users'].discard(user)
                ch['users'].add(new)

    async def fight(self, players, deathmatch=False, versusone=False):
        # Check if those users are in the channel, if they're identified, etc
        accounts = []
        openSpots = 0
        for player in players[:]:
            if player == "*":
                openSpots += 1
                continue

            if player.lower() not in map(str.lower, self.channels[self.channel]['users']):
                await self.message(self.channel, "\002{0}\002 is not in the channel.".format(player))
                return

            if not self.users[player]['account']:
                await self.message(self.channel, "\002{0}\002 is not identified with NickServ.".format(player))
                return

            if self.users[player]['account'] in accounts:
                players.remove(player)
                continue

            accounts.append(self.users[player]['account'])  # This is kinda to prevent clones playing

        if len(players) <= 1:
            await self.message(self.channel, "You need more than one person to fight!")
            return

        self.pendingFights[players[0].lower()] = {
            'ts': time.time(),  # Used to calculate the expiry time for a fight
            'deathmatch': deathmatch,
            'versusone': versusone,
            'pendingaccept': [x.lower() for x in players[1:]],
            'players': [players[0]],
        }

        if config['nick'] in players:  # If a user is requesting the bot participate in a fight...
            if versusone:  # If it's a duel or deathmatch, refuse
                return await self.message(self.channel, "{0} is not available for duels or deathmatches".format(config['nick']))
            if (time.time() - self.lastbotfight < 30):  # Prevent the bot from fighting with someone within 30 seconds of its last fight with someone. Trying to stop people from taking over the channel
                return await self.message(self.channel, "{0} needs a 30 second break before participating in a fight.".format(config['nick']))
            await self.message(self.channel, "YOU WILL SEE")
            self.pendingFights[players[0].lower()]['pendingaccept'].remove(config['nick'].lower())
            self.pendingFights[players[0].lower()]['players'].append(config['nick'])
            if not self.pendingFights[players[0].lower()]['pendingaccept']:
                # Start the game!
                await self.start(self.pendingFights[players[0].lower()])
                return
            players.remove(config['nick'])

        players[:] = [x for x in players if x != '*']  # This magically makes it so you can issue a wildcard challenge to anyone. No one knows how this works but we stopped asking questions long ago.

        if len(players) > 1:
            if deathmatch:
                await self.message(self.channel, "{0}: \002{1}\002 challenged you to a deathmatch. The loser will be bant for 20 minutes. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
            else:
                await self.message(self.channel, "{0}: \002{1}\002 challenged you. To accept, use '!accept {1}'.".format(", ".join(players[1:]), players[0]))
        else:
            await self.message(self.channel, "\002{0}\002 has challenged anybody willing to fight{1}. To accept, use '!accept {0}'.".format(players[0], " to the death. The loser will be bant for 20 minutes" if deathmatch else ""))

        if openSpots == 1 and len(players) > 1:
            await self.message(self.channel, "This fight has an open spot for anybody to join.")
        elif openSpots > 1:
            await self.message(self.channel, "This fight has open spots for {0} players to join.".format(openSpots))

    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i + n]

    async def _timeout(self):
        while True:
            await asyncio.sleep(5)

            if not self.gameRunning or (self.turnStart == 0):
                for i in copy.copy(self.pendingFights):
                    if (time.time() - self.pendingFights[i]['ts'] > 300):
                        await self.message(self.channel, "\002{0}\002's challenge has expired.".format(self.pendingFights[i]['players'][0]))
                        del self.pendingFights[i]
                continue

            if (time.time() - self.turnStart > 60) and len(self.turnlist) >= (self.currentTurn + 1):
                await self.message(self.channel, "\002{0}\002 forfeits due to idle.".format(self.turnlist[self.currentTurn]))
                self.players[self.turnlist[self.currentTurn].lower()]['hp'] = -1
                self.countStat(self.turnlist[self.currentTurn], "idleouts")
                #self.kick(self.channel, self.turnlist[self.currentTurn], "WAKE UP SHEEPLE")
                try:
                    await self.akick(self.turnlist[self.currentTurn], "3", "3 MINUTES FOR IDLE OUT")
                except:
                    await self.kick(self.channel, self.turnlist[self.currentTurn], "WAKE UP SHEEPLE")
                    raise
                aliveplayers = 0
                # TODO: Do this in a neater way
                for p in self.players:
                    if self.players[p]['hp'] > 0:
                        aliveplayers += 1
                        survivor = p

                if aliveplayers >= 1:
                    await self.win(survivor, False)
                else:
                    await self.getTurn()
            elif (time.time() - self.turnStart > 30) and len(self.turnlist) >= (self.currentTurn + 1) and not self.poke:
                self.poke = True
                await self.message(self.channel, "Wake up, \002{0}\002!".format(self.turnlist[self.currentTurn]))

    async def _send(self, input):
        await super()._send(input)
        if not isinstance(input, str):
            input = input.decode(self.encoding)
        self.logger.debug('>> %s', input.replace('\r\n', ''))

    # Saves information in the stats database.
    # nick = case-sensitive nick.
    # stype = wins/losses/quits/idleouts/kills
    #         fights/accepts/joins
    #         praises
    def countStat(self, nick, stype, add=1):
        if not self.deathmatch and not self.versusone:
            return

        try:
            nick = self.users[nick]['account']
        except KeyError:  # User vanished from earth
            return
        try:
            stat = PlayerStats.get(PlayerStats.name == nick)
        except PlayerStats.DoesNotExist:
            stat = PlayerStats.create(name=nick)

        PlayerStats.update(**{stype: getattr(stat, stype) + add}).where(PlayerStats.name == nick).execute()

    def getStats(self, nick):
        try:
            return PlayerStats.get(PlayerStats.name ** nick)
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
            try:  # Let's test these on start...
                cmd = importlib.import_module('extcmd.{}'.format(command))
                logging.info('Loading extended command: {}'.format(command))

                try:  # Handling non-existent helptext
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


class PlayerStats(BaseModel):
    name = peewee.CharField()

    turns = peewee.IntegerField(default=0)
    hits = peewee.IntegerField(default=0)
    heals = peewee.IntegerField(default=0)
    praises = peewee.IntegerField(default=0)
    totdmg = peewee.IntegerField(default=0)
    totheal = peewee.IntegerField(default=0)
    crits = peewee.IntegerField(default=0)

    elo = peewee.IntegerField(default=1300)

    matches = peewee.IntegerField(default=0)
    deathmatches = peewee.IntegerField(default=0)

    wins = peewee.IntegerField(default=0)
    losses = peewee.IntegerField(default=0)
    quits = peewee.IntegerField(default=0)
    idleouts = peewee.IntegerField(default=0)

    firstplayed = peewee.DateTimeField(default=datetime.datetime.now)
    lastplayed = peewee.DateTimeField()

    def save(self, *args, **kwargs):
        self.lastplayed = datetime.datetime.now()
        return super(PlayerStats, self).save(*args, **kwargs)

    @classmethod
    def custom_init(cls):
        database.execute_sql('create unique index if not exists playerstats_unique '
                             'on playerstats(name collate nocase)', {})


class GameStats(BaseModel):
    time = peewee.DateTimeField(default=datetime.datetime.now)
    player1 = peewee.CharField()
    player2 = peewee.CharField()

    turns = peewee.IntegerField(default=0)
    winner = peewee.IntegerField(default=0)  # 1 if player1 won, 2 if player2.

    player1_hits = peewee.IntegerField(default=0)
    player2_hits = peewee.IntegerField(default=0)

    player1_heals = peewee.IntegerField(default=0)
    player2_heals = peewee.IntegerField(default=0)

    player1_praise = peewee.IntegerField(default=0)  # 0 if no praise, 1 if player on self, 2 if player on enemy
    player1_praiseroll = peewee.IntegerField(default=0)  # positive if heal, negative if hit.

    player2_praise = peewee.IntegerField(default=0)
    player2_praiseroll = peewee.IntegerField(default=0)

    player1_totdmg = peewee.IntegerField(default=0)
    player1_totheal = peewee.IntegerField(default=0)

    player2_totdmg = peewee.IntegerField(default=0)
    player2_totheal = peewee.IntegerField(default=0)

    player1_crits = peewee.IntegerField(default=0)
    player2_crits = peewee.IntegerField(default=0)

    @classmethod
    def custom_init(cls):
        database.execute_sql('create index if not exists gamestats_unique '
                             'on gamestats(player1 collate nocase, player2 collate nocase)', {})


PlayerStats.create_table(True)
GameStats.create_table(True)

try:
    PlayerStats.custom_init()
    GameStats.custom_init()
except:
    pass


client = Donger(config['nick'], sasl_username=config['nickserv_username'],
                sasl_password=config['nickserv_password'])
client.run(config['server'], config['port'], tls=config['tls'])
