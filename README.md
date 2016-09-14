DongerDong
=================
What started as *"A simple IRC bot for fighting, written in Python"*, has grown to become the most comprehensive and flexible collection of code ever written.

Official IRC Channel: **#donger** on Freenode  
Development Channel: **#donger-dev** on Freenode

How to install
==============

 * Install pyfiglet, peewee, pydle and pure-sasl (via `pip install -r requirements.txt` if you want, you're an adult it's your call)
 * Rename config.example to config.json and edit it
 * Run the bot (with Python 3)
 * ???
 * Profit!

Configuration Notes
=============
 * `auxchans` are channels the bot joins on connect, with fewer usable commands and with a (basic) flood control system. Enter channels in the format `["#channel1","#channel2"]`, etc.
 * `extendedcommands` references files of the same name in the "extcmd" folder
 * `topmodifier` changes the way players are ranked depending on how many fights they've participated in
 * `admins` specifies people with additional permissions - to be used in future extended commands and in the `!update` extended command (disabled by default - enable by adding it to `extendedcommands`)
 * `stats-url` is optional and can be removed entirely if you don't have a URL where statistics are displayed (the Supreme Dongerdong's statistics page is set as default, but will *not* display statistics from your instance).

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
