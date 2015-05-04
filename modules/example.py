# Example module :D

# On this chapter: HOW TO OVERRIDE A FUNCTION!1

originaljoin = None

def fakeJoin(cli, fighter, ev):
    global originaljoin
    global donger
    cli.privmsg(ev.source, "fuck you :D")
    originaljoin(cli, fighter, ev) # <-- we continue executing the original function

def loadModule(dongerdong):
    global originaljoin
    originaljoin = dongerdong.join # the original join function
    
    # Override the core's join function
    dongerdong.join = fakeJoin
