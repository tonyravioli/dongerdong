import subprocess
import os
import sys
import time

helptext = "Updates and restarts the bot"
adminonly = True

async def doit(irc, target, source):
    commands = ["git fetch",
                "git rebase --stat --preserve-merges"]
    
    for command in commands:
        child = subprocess.Popen(command.split(),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        (out, err) = child.communicate()
        ret = child.returncode
        
        await irc.message(source, "{0} returned code {1}".format(command, ret))
        for line in (out + err).splitlines():
            async irc.message(source, line.decode("utf-8"))
    
    irc.eventloop.schedule(irc.quit, "Updating...")
    irc.eventloop.schedule(os.execl, sys.executable, sys.executable, *sys.argv)
