# -*- coding: utf-8 -*-
import logging
import _thread
import socket
import re
import time
from . import numerics
from . import features

_rfc_1459_command_regexp = re.compile("^(:(?P<prefix>[^ ]+) +)?(?P<command>[" +
                                      "^ ]+)( *(?P<argument> .+))?")


class IRCClient:
    # Defaults..
    server = None    # IRC server
    port = 6667
    nickname = "Groo"    # Nick
    ident = nickname
    gecos = "-"
    ssl = False
    msgdelay = 0.5 
    reconnects = 10
    reconncount = 0
    localaddress = ''

    features = None
    ibuffer = None
    connected = False
    logger = None
    socket = None
    handlers = {}
    queue = []
    channels = {}
    users = {}

    def __init__(self, sid):
        self.logger = logging.getLogger('bearded-potato-' + sid)
        self.ibuffer = LineBuffer()
        self.features = features.FeatureSet()
        self.lastping = time.time()
        #self.addhandler("pubmsg", self._pubmsg)

        # Internal handlers used to get user/channel information
        self.addhandler("join", self._on_join)
        #self.addhandler("currenttopic", self._on_topic)
        #self.addhandler("topic", self._on_topic)
        #self.addhandler("topicinfo", self._on_topicinfo)
        self.addhandler("whospcrpl", self._on_whox)
        self.addhandler("whoreply", self._on_who)
        self.addhandler("whoisloggedin", self._on_whoisaccount)
        #self.addhandler("mode", self._on_mode)
        self.addhandler("quit", self._on_quit)
        self.addhandler("part", self._on_part)
        self.addhandler("kick", self._on_kick)
        #self.addhandler("banlist", self._on_banlist)
        self.addhandler("kick", self._on_kick)
        self.addhandler("nick", self._on_nick)

    def configure(self, server=server, port=port, nick=nickname, ident=nickname,
                gecos=gecos, ssl=ssl, msgdelay=msgdelay, reconnects=reconnects):
        self.server = server
        self.port = port
        self.nickname = nick
        self.ident = nick
        self.gecos = gecos
        self.ssl = ssl
        self.msgdelay = msgdelay
        self.imayreconnect = True
        
    def connect(self):
        """ Connects to the IRC server. """
        self.logger.info("Connecting to {0}:{1}".format(self.server, self.port))
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server, self.port))
        except socket.error as err:
            self.logger.error("Couldn't connect to {0}:{1}: {2}"
                .format(self.server, self.port, err))

            if self.reconncount <= self.reconnects:
                self.reconncount += 1
                self.connect()
            return False

        self.connected = True

        _thread.start_new_thread(self._cookie_monster, ())
        _thread.start_new_thread(self._process_queue, ())

        _thread.start_new_thread(self._process_forever, ())

        self._fire_event(Event("connect", None, None))
        time.sleep(2) # v3 ftw
        self.user(self.ident, self.gecos)
        self.nick(self.nickname)

    def _cookie_monster(self):
        while self.connected:
            time.sleep(60)
            if (time.time() - self.lastping) > 300:
                self.disconnect("", False) # We're dead
            
    def _process_forever(self):
        while self.connected:
            self._process_data()
            time.sleep(0.1)
        if self.reconncount <= self.reconnects:
            self.reconncount += 1
            self.connect()
        else:
            self.imayreconnect = False

    def _processline(self, line):
        prefix = None
        command = None
        arguments = None
        self._fire_event(Event("all_raw_messages",
                                 self.server,
                                 None,
                                 [line]))

        m = _rfc_1459_command_regexp.match(line)
        if m.group("prefix"):
            prefix = m.group("prefix")

        if m.group("command"):
            command = m.group("command").lower()

        if m.group("argument"):
            a = m.group("argument").split(" :", 1)
            arguments = a[0].split()
            if len(a) == 2:
                arguments.append(a[1])

        # Translate numerics into more readable strings.
        command = numerics.numerics.get(command, command)

        if command == "nick":
            if NickMask(prefix).nick == self.nickname:
                self.nickname = arguments[0]
        elif command == "welcome":

            # Record the nickname in case the client changed nick
            # in a nicknameinuse callback.
            self.nickname = arguments[0]
        elif command == "isupport":
            self.features.load(arguments)

        if command in ["privmsg", "notice"]:
            target, message = arguments[0], arguments[1]
            messages = _ctcp_dequote(message)

            if command == "privmsg":
                if is_channel(target):
                    command = "pubmsg"
            else:
                if is_channel(target):
                    command = "pubnotice"
                else:
                    command = "privnotice"

            for m in messages:
                if isinstance(m, tuple):
                    if command in ["privmsg", "pubmsg"]:
                        command = "ctcp"
                    else:
                        command = "ctcpreply"

                    m = list(m)
                    self.logger.debug("command: %s, source: %s, target: %s, "
                        "arguments: %s", command, prefix, target, m)
                    self._fire_event(Event(command, NickMask(prefix), target,
                         m))
                    if command == "ctcp" and m[0] == "ACTION":
                        self._fire_event(Event("action", prefix, target,
                             m[1:]))
                else:
                    self.logger.debug("command: %s, source: %s, target: %s, "
                        "arguments: %s", command, prefix, target, [m])
                    self._fire_event(Event(command, NickMask(prefix), target,
                        [m]))
        else:
            target = None

            if command == "quit":
                arguments = [arguments[0]]
            elif command == "ping":
                # Hardcoded pong :D
                self.lastping = time.time()
                self.pong(arguments[0])
                target = arguments[0]
            else:
                target = arguments[0]
                arguments = arguments[1:]

            if command == "mode":
                if not is_channel(target):
                    command = "umode"

            self.logger.debug("command: %s, source: %s, target: %s, "
                "arguments: %s", command, prefix, target, arguments)
            self._fire_event(Event(command, NickMask(prefix), target,
                arguments))

    def _process_data(self):
        if not self.connected:
            return 1
        try:
            reader = getattr(self.socket, 'read', self.socket.recv)
            new_data = reader(2 ** 14)
        except socket.error:
            # The server hung up.
            self.disconnect("Connection reset by peer", False)
            return False
        if not new_data:
            # Read nothing: connection must be down.
            self.disconnect("Connection reset by peer", False)
            return False

        self.ibuffer.feed(new_data)
        pline = []
        for line in self.ibuffer._lines():
            pline.append(line)
        for line in pline:
            try:
                line = line.decode('utf-8')
            except:
                line = line.decode('latin1')
            if not line:
                continue
            self.logger.debug(line)
            self._processline(line)

    def _process_queue(self):
        while True:
            if self.connected is False:
                return 0
            for stuff in self.queue:
                time.sleep(self.msgdelay)
                self.send_stuff(stuff)
            self.queue = []
            time.sleep(self.msgdelay)

    def _fire_event(self, event):
        try:
            self.handlers[event.type]
            for i in self.handlers[event.type]:
                try:
                    if i['blocking']:
                        i['callback'](self, event)
                    else:
                        _thread.start_new_thread(i['callback'], (self, event))
                except BaseException as e:
                    self.logger.error("Calling {0} handler raised exception:"
                                    "{1}".format(event.type, e))
        except KeyError:
            pass

    def addhandler(self, action, callback, blocking=False):
        try:
            self.handlers[action]
        except:
            self.handlers[action] = []
        self.handlers[action].append({'blocking': blocking,
                                      'action': action,
                                      'callback': callback})
        
        seen = set()
        new_l = []
        for d in self.handlers[action]:
            t = tuple(d.items())
            if t not in seen:
                seen.add(t)
                new_l.append(d)

        self.handlers[action] = new_l
    
    def send(self, raw, urgent=False):
        if urgent is False:
            self.queue.append(raw)
        else:
            self.send_stuff(raw)

    def send_stuff(self, stuff):
        bytes_ = stuff.encode('utf-8') + b'\r\n'
        if len(bytes_) > 512:
            self.logger.warning("Se ha intentado enviar un mensaje muy largo!")
        try:
            self.socket.send(bytes_)
            self.logger.debug("TO SERVER: {0}".format(stuff))
        except socket.error:
            # Ouch!
            self.disconnect("Connection reset by peer.", False)

    def disconnect(self, message, noreconn=True):
        if noreconn:
            self.reconncount = 100000  # :D
            self.imayreconnect = False
        if not self.connected:
            return

        self.connected = False

        self.quit(message)

        try:
            self.socket.shutdown(socket.SHUT_WR)
            self.socket.close()
        except socket.error:
            pass
        self.logger.info("Disconnected from server: {0}".format(message))
        self._fire_event(Event("disconnect", None, None))
        del self.socket

    ### IRC Commands ###

    def user(self, user, realname):
        self.send("USER {0} * * :{1}".format(user, realname), True)

    def nick(self, nick):
        self.send("NICK {0}".format(nick), True)

    def quit(self, reason):
        self.send("QUIT :{0}".format(reason), True)

    def pong(self, param):
        self.send("PONG :{0}".format(param))

    def join(self, channels):
        self.send("JOIN {0}".format(channels))
    
    def part(self, channels, message=""):
        self.send("PART {0} :{1}".format(channels, message))

    def who(self, target="", op=""):
        self.send("WHO%s%s" % (target and (" " + target), op and (" " + op)))
    
    def mode(self, target, modes):
        self.send("MODE {0} {1}".format(target, modes))
    
    def privmsg(self, target, message):
        self.lastping = time.time()
        if "\n" in message:
            m = message.split("\n")
            for l in m:
                self.send("PRIVMSG {0} :{1}".format(target, l))
        else:
            self.send("PRIVMSG {0} :{1}".format(target, message))
    
    def notice(self, target, modes):
        self.send("NOTICE {0} :{1}".format(target, modes))

    def whois(self, targets):
        self.send("WHOIS " + targets)
        
    def kick(self, channel, target, reason=""):
        self.send("KICK {0} {1} :{2}".format(channel, target, reason))
    
    def multimode(self, channel, mode, users):
        if type(users) == str:
            self.mode(channel, mode + " " + users)
        elif type(users) == list:
            f1 = ""
            
            while users != []:
                if len(users[:self.features.modes]) == self.features.modes:
                    self.mode(channel, "{0}{1} {2}".format(mode[0], mode[1] * self.features.modes, " ".join(users[:self.features.modes])))
                    users = users[self.features.modes:]
                else:
                    self.mode(channel, "{0}{1} {2}".format(mode[0], mode[1] * len(users[:self.features.modes]), " ".join(users[:self.features.modes])))
                    users = []
        else:
            raise
    
    def voice(self, channel, users):
        self.multimode(channel, "+v", users)
        
    def devoice(self, channel, users):
        self.multimode(channel, "-v", users)
        
    # Internal handlers

    def _on_join(self, this, event):
        if event.source.nick == self.nickname:
            # We just joined a channel, let's add it to the list
            self.channels[event.target] = Channel(self, event.target)
        else:
            #print(self.channels)
            try:
                account = event.arguments[0]
            except:
                account = None
                
            self.channels[event.target].users[event.source.nick.lower()] = User(
                event.source.nick, event.source.user, event.source.host,
                "", "", account)

    def _on_topic(self, myself, event):
        self.channels[event.arguments[0]].topicChange(event.source,
                                                event.arguments[1])

    def _on_topicinfo(self, myself, event):
        self.channels[event.arguments[0]].topicsetter = NickMask(
                                                             event.arguments[1])
        self.channels[event.arguments[0]].topicsetterts = event.arguments[2]

    def _on_who(self, myself, event):
        # o_O IT IS A WHO!!
        # THE FOOKING SERVER DOESN'T SUPPORT WHOX >:O
        # Let's send a whois to get the goddamn account name
        self.whois(event.arguments[4])
        self.channels[event.arguments[0]].addUser(event)

    def _on_whoisaccount(self, myself, event):
        self.users[event.arguments[0].lower()].account = event.arguments[1]
        for i in self.channels:
            try:
                self.channels[i].users[event.arguments[1].lower()].account = \
                                                             event.arguments[1]
            except:
                pass

    def _on_whox(self, myself, e):
        if e.arguments[0] == "08":
            self.channels[e.arguments[1]].users[e.arguments[4].lower()] = User(
                    e.arguments[4],
                    e.arguments[2],
                    e.arguments[3],
                    e.arguments[7],
                    e.arguments[5],
                    e.arguments[6]
                )

    def _on_mode(self, myself, event):
        status = ""
        number = 1
        prefixes = "".join("{!s}".format(k) for (k, v) in
                            self.features.prefix.items())
        prefixes = prefixes.replace("+", "")
        for i in event.arguments[0]:
            if i in prefixes:
                number += 1
            elif i in self.features.chanmodes[0]:
                number += 1
            elif i in self.features.chanmodes[1] and status=="+":
                number += 1
            elif i in self.features.chanmodes[2] and status=="+":
                number += 1
            if i == "+":
                status = "+"
            elif i == "-":
                status = "-"
            elif i == "v":
                if status == "-":
                    self.channels[event.target].users[event.arguments[number].lower()] \
                    .voice = False
                else:
                    self.channels[event.target].users[event.arguments[number].lower()] \
                    .voice = True
            elif i == "b":
                if status == "+":
                    ban = Ban(event.arguments[number], time.time())
                    self.channels[event.target].bans.append(ban)
                else:
                    self.channels[event.target].bans.remove(ban)
            elif i == "q":
                if status == "+":
                    ban = Ban(event.arguments[number], time.time())
                    self.channels[event.target].quiets.append(ban)
                else:
                    self.channels[event.target].quiets.remove(ban)
            elif i in prefixes:
                if status == "-":
                    self.channels[event.target].users[event.arguments[number].lower()] \
                    .op = False
                else:
                    self.channels[event.target].users[event.arguments[number].lower()] \
                    .op = True
    
    def _on_part(self, myself, event):
        if event.source.nick == self.nickname:
            del self.channels[event.target]
        else:
            del self.channels[event.target].users[event.source.nick.lower()]
        
    def _on_quit(self, myself, event):
        #del self.users[event.source.nick]
        for i in self.channels:
            try:
                del self.channels[i].users[event.source.nick.lower()]
                self._fire_event(Event("cquit", event.source, i, event.arguments))
            except:
                pass
    
    def _on_nick(self, myself, event):
        for i in self.channels:
            try:
                self.channels[i].users[event.target.lower()] = self.channels[i].users[event.source.nick.lower()]
                self.channels[i].users[event.target.lower()].nick = event.target
                del self.channels[i].users[event.source.nick.lower()]
            except:
                try:
                    self.features.whox
                    self.who(i, "%tcuhnfar,08")
                except:
                    self.who(i)

    def _on_kick(self, myself, event):
        if event.arguments[0] != self.nickname:
            del self.channels[event.target].users[event.arguments[0].lower()]
    
    def _on_banlist(self, myself, event):
        ban = Ban(event.arguments[1], event.arguments[3])
        self.channels[event.arguments[0]].bans.append(ban)
    
    def _on_quietlist(self, myself, event):
        ban = Ban(event.arguments[1], event.arguments[3])
        self.channels[event.arguments[0]].quiets.append(ban)


class Channel(object):
    def __init__(self, client, channelname):
        self.name = None
        self.topic = None
        self.topicsetter = None
        self.topicsetterts = None
        self.users = {}
        self.cli = None
        self.bans = []
        self.quiets = []
        self.cli = client
        self.name = channelname
        try:
            client.features.whox
            client.who(channelname, "%tcuhnfar,08")
        except:
            client.who(channelname)
        
        #client.mode(channelname, "b")
        #if "q" in client.features.chanmodes[0]:
        #    client.mode(channelname, "q")

    def topicChange(self, source, topic):
        self.topic = topic
        self.topicsetter = source
        self.topicsetterts = time.time()

    def addUser(self, e):
        if e.arguments[0] == "08":
            self.users[e.arguments[4].lower()] = User(
                    e.arguments[4],
                    e.arguments[2],
                    e.arguments[3],
                    e.arguments[7],
                    e.arguments[5],
                    e.arguments[6]
                )
        else:
            self.users[e.arguments[4].lower()] = User(
                    e.arguments[4],
                    e.arguments[1],
                    e.arguments[2],
                    e.arguments[6][2:],
                    e.arguments[5]
                )
        #self.cli.users[e.arguments[4]] = self.users[e.arguments[4]]

    def __repr__(self):
        return "<Channel topic:'{0}', topicsetter:'{1}', topicsetterts:'{2}'" \
               ", users: '{3}'>".format(self.topic, self.topicsetter,
                self.topicsetterts, self.users)


class User(object):
    def __init__(self, nick, ident, host, gecos, status, account=None):
        self.nick = None
        self.ident = None
        self.host = None
        self.gecos = None
        self.op = False
        self.voiced = False
        self.account = None
        self.update(nick, ident, host, gecos, status, account)

    def update(self, nick, ident, host, gecos, status, account=None):
        self.nick = nick
        self.ident = ident
        self.host = host
        self.gecos = gecos
        if account == "0" or account == "" or account == "*":
            self.account = None
        else:
            self.account = account

        if "@" in status or "&" in status or "%" in status or "~" in status or \
                                                                  "!" in status:
            self.op = True

        if "+" in status:
            self.voiced = True

    def __repr__(self):
        return "<User nick:'{0}', ident:'{1}', host:'{2}', gecos: '{3}'" \
               ", op: '{4}', voiced: '{5}', account: '{6}'>" \
                .format(self.nick, self.ident, self.host, self.gecos,
                str(self.op), str(self.voiced), str(self.account))


class Event(object):
    def __init__(self, type, source, target, arguments=None):
        self.type = type
        self.source = source
        self.target = target
        if arguments is None:
            arguments = []
        self.arguments = arguments
        if type == "privmsg" or type == "pubmsg" or type == "ctcpreply" or type\
        == "ctcp" or type == "pubnotice" or type == "privnotice":
            if not is_channel(target):
                self.target = source.nick
            if not is_channel(source):
                self.source = source.nick
            self.splitd = arguments[0].split()
        self.source2 = source


class LineBuffer(object):
    line_sep_exp = re.compile(b'\r?\n')

    def __init__(self):
        self.buffer = b''

    def feed(self, byte):
        self.buffer += byte

    def lines(self):
        try:
            x = (line.decode('utf-8')
                for line in self._lines())
        except UnicodeDecodeError:
            x = (line.decode('latin1')
                for line in self._lines())
        return x

    def _lines(self):
        lines = self.line_sep_exp.split(self.buffer)
        # save the last, unfinished, possibly empty line
        self.buffer = lines.pop()
        return iter(lines)

    def __iter__(self):
        return self.lines()

    def __len__(self):
        return len(self.buffer)


def is_channel(string):
    """Check if a string is a channel name.

    Returns true if the argument is a channel name, otherwise false.
    """
    return string and string[0] in "#&+!"


def parse_nick(name):
    """ parse a nickname and return a tuple of (nick, mode, user, host)

    <nick> [ '!' [<mode> = ] <user> ] [ '@' <host> ]
    """

    try:
        nick, rest = name.split('!')
    except ValueError:
        return (name, None, None, None)
    try:
        mode, rest = rest.split('=')
    except ValueError:
        mode, rest = None, rest
    try:
        user, host = rest.split('@')
    except ValueError:
        return (name, mode, rest, None)

    return (name, nick, mode, user, host)

_LOW_LEVEL_QUOTE = "\020"
_CTCP_LEVEL_QUOTE = "\134"
_CTCP_DELIMITER = "\001"
_low_level_mapping = {
    "0": "\000",
    "n": "\n",
    "r": "\r",
    _LOW_LEVEL_QUOTE: _LOW_LEVEL_QUOTE
}

_low_level_regexp = re.compile(_LOW_LEVEL_QUOTE + "(.)")


def _ctcp_dequote(message):
    """[Internal] Dequote a message according to CTCP specifications.

    The function returns a list where each element can be either a
    string (normal message) or a tuple of one or two strings (tagged
    messages).  If a tuple has only one element (ie is a singleton),
    that element is the tag; otherwise the tuple has two elements: the
    tag and the data.

    Arguments:

        message -- The message to be decoded.
    """

    def _low_level_replace(match_obj):
        ch = match_obj.group(1)

        # If low_level_mapping doesn't have the character as key, we
        # should just return the character.
        return _low_level_mapping.get(ch, ch)

    if _LOW_LEVEL_QUOTE in message:
        # Yup, there was a quote.  Release the dequoter, man!
        message = _low_level_regexp.sub(_low_level_replace, message)

    if _CTCP_DELIMITER not in message:
        return [message]
    else:
        # Split it into parts.  (Does any IRC client actually *use*
        # CTCP stacking like this?)
        chunks = message.split(_CTCP_DELIMITER)

        messages = []
        i = 0
        while i < len(chunks) - 1:
            # Add message if it's non-empty.
            if len(chunks[i]) > 0:
                messages.append(chunks[i])

            if i < len(chunks) - 2:
                # Aye!  CTCP tagged data ahead!
                messages.append(tuple(chunks[i + 1].split(" ", 1)))

            i = i + 2

        if len(chunks) % 2 == 0:
            # Hey, a lonely _CTCP_DELIMITER at the end!  This means
            # that the last chunk, including the delimiter, is a
            # normal message!  (This is according to the CTCP
            # specification.)
            messages.append(_CTCP_DELIMITER + chunks[-1])

        return messages


class NickMask(str):
    @classmethod
    def from_params(cls, nick, user, host):
        return cls('{nick}!{user}@{host}'.format(**vars()))

    @property
    def nick(self):
        return self.split("!")[0]

    @property
    def userhost(self):
        return self.split("!")[1]

    @property
    def host(self):
        return self.split("@")[1]

    @property
    def user(self):
        return self.userhost.split("@")[0]

class Ban:
    def __init__(self, mask, pts):
        self.ban = mask
        self.ts = pts
    
    @property
    def nick(self):
        return self.ban.split("!")[0]

    @property
    def userhost(self):
        return self.ban.split("!")[1]

    @property
    def host(self):
        return self.ban.split("@")[1]

    @property
    def user(self):
        return self.ban.userhost.split("@")[0]
        
    def banmatches(self, nickmask):
        ban = self.ban.replace("*", ".*").replace("?", ".?")
        banregex = re.compile(ban)
        if banregex.match(nickmask):
            return True
        else:
            return False
