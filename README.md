DongerDong
=================
What started as *"A simple IRC bot for fighting, written in Python"* has grown to become the most comprehensive and flexible collection of code ever written.

Official IRC Channel: **#donger** on Freenode  
Development Channel: **#donger-dev** on Freenode

How to install
==============

 * Install Python 3
 * Install requirements pyfiglet, peewee, pydle and pure-sasl (via `pip install -r requirements.txt` if you want, you're an adult it's your call)
 * Rename config.example to config.json and edit it
 * Configure the IRC user and channel:
   * Register the username and nickname the bot will be using with NickServ (the ones you set in config.json)
   * Register the primary channel the bot will be using, and ensure the bot has flags of at least +Oefr in that channel's access list. It needs to receive channel op when joining the channel, and must be able to set AKICKs with ChanServ (for deathmatches)
 * Run the bot (with Python 3)
 * ???
 * Profit!

Configuration Notes
=============
 * `server` is the server you're connecting to
 * `nick` is the nickname the bot will request when connecting to the server
 * `channel` is the bot's "primary channel" - the one where all the fighting happens
 * `port` is the port to connect over, default is `6697`
 * `tls` defines whether we're doing the connection securely (default is `true`)
 * `nickserv_username` and `nickserv_password` specify the credentials the bot will send to nickserv to identify
 * `auxchans` are additional, non-fighting channels the bot joins on connect. These channels have access to fewer commands, and messages to them are limited by a (basic) flood control system. Enter channels in the format `["#channel1","#channel2"]`, etc.
 * `extendedcommands` references files of the same name in the "extcmd" folder. Try adding `"update"` to enable the update.py extended command.
 * `topmodifier` changes the way players are ranked depending on how many fights they've participated in. Defaults to 0.05.
 * `admins` specifies the usernames of people with additional permissions - like !join, !part, and (if enabled through extended commands) !update.
 * `stats-url` is optional and can be removed entirely if you don't have a URL where statistics are displayed (the Supreme Dongerdong's statistics page is set as default, but will *not* display statistics from your instance).
 * `show-ascii-art-text` is an accessibility feature. When set to false, it does not send ASCII text art to channels, instead printing the text normally.

Wisdom
======

>All that is gold does not glitter,  
>Not all those who donger are lost;  
>The old that do dong do not wither,  
>Deep dongs are not reached by the frost.  
>From the ashes the donger shall be woken,  
>A light from the shadows shall spring;  
>Renewed shall be blade that was broken,  
>The donger again shall be king  
-J.R.R. Tolkien

"He who learns but does not think, is lost! He who dongs dongs, dongs dongs!" - Confucius
