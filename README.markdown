pstorytime
----------

pstorytime is an audiobook API/console player written in python that uses
gstreamer as backend. It stores all events like play, pause and seek together
with walltime, filename and position in file. It also autosaves the position
while playing to recover from crashes without loosing the position. This allows
the user to retrace his/her steps and minimizes the risk of getting lost.

Furthermore, it treats all files as a continuous stream so that seeking can be
made seemlessly between different files.

Installation
------------

Hold on for a while, this is a work in progress.

License
-------

[GNU General Public License](https://github.com/ankaan/pstorytime/blob/master/LICENSE)
