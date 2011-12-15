pstorytime
----------

pstorytime is an audiobook API/console player written in python that uses
gstreamer as backend. It stores all events like play, pause and seek together
with walltime, filename and position in file. It also autosaves the position
while playing to recover from crashes without loosing the position. This allows
the user to retrace his/her steps and minimizes the risk of getting lost.

Furthermore, it treats all files as a continuous stream so that seeking can be
made seemlessly between different files.

Dependencies
------------
argparse  - Included in python >=2.7 and >=3.1.
pygst     - Python gstreamer bindings.
gstreamer - Including any codecs which you wish to be able to use.

Installation
------------

Hold on for a while, this is a work in progress.

Testing if GStreamer is setup properly
--------------------------------------

Try to run:
gst-launch-0.10 playbin2 uri=file://<path to file>

For example:
gst-launch-0.10 playbin2 uri=file:///usr/share/sounds/alsa/Front_Center.wav

This will use the same playback system as the audiobook player. Also try this out with some audiobook file to make sure the codecs you need are set up properly.

License
-------

[GNU General Public License](https://github.com/ankaan/pstorytime/blob/master/LICENSE)
