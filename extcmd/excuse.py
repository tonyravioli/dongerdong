#!/usr/bin/env python3
import json
import random
helptext = "Outputs a random BOFH excuse."

excuselist = json.load(open("wisdom/excuses.json"))
async def doit(irc, target, source):
  await irc.message(target, random.choice(excuselist))
