#!/usr/bin/env python3
import json
import random
helptext = "Produces a genuine, authentic donger"

dongerlist = json.load(open("wisdom/dongers.json", 'r', encoding='utf-8'))
async def doit(irc, target, source):
  await irc.message(target, random.choice(dongerlist))
