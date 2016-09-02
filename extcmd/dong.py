#!/usr/bin/env python3
import json
import random
helptext = "Produces a genuine, authentic donger"

dongerlist = json.load(open("wisdom/dongers.json"))
def doit(irc, target, source):
  irc.message(target, random.choice(dongerlist))
