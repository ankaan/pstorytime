# -*- coding: utf-8 -*-
"""Simple gstreamer playing abstraction. """

#
# Copyright (C) 2011 Anders Engström <ankan@ankan.eu>
#
# This file is part of pstorytime.
#
# pstorytime is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pstorytime is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pstorytime.  If not, see <http://www.gnu.org/licenses/>.

import pygst
pygst.require("0.10")
import os.path
import threading
import gobject
import sys

# Don't touch my arguments!
argv = sys.argv
sys.argv = []
import gst
sys.argv = argv

from pstorytime.misc import withdoc

__all__ = [
  'Player',
  ]

class Player(gobject.GObject):
  """Simple gstreamer playing abstraction. """
  SECOND = gst.SECOND
  """A second according to gstreamer. """

  @withdoc(gobject.property)
  def eos(self):
    """If the player is currently at the end of a stream."""
    with self._lock:
      return self._eos

  def __init__(self,bus,directory):
    """Create the gstreamer player abstraction.

    Arguments:
      bus         A gobject to emit error signals to.
      directory   The directory where the audio files are located.
    """
    gobject.GObject.__init__(self)
    self._lock = threading.RLock()

    self._directory = directory
    self._bus = bus

    self._filename = None
    self._hasplayed = False
    self._duration = 0

    self.gst = gst.element_factory_make("playbin2", "audioplayer")
    fakesink = gst.element_factory_make("fakesink", "fakesink")
    self.gst.set_property("video-sink", fakesink)

    self._gstbus = self.gst.get_bus()
    self._gstbus.add_signal_watch()
    self._gstbus.connect("message", self._on_message)

    self._clear_eos_count = 0
    self._on_eos_id = self._gstbus.connect( "message", 
                                            self._on_eos,
                                            self._clear_eos_count)

  def _on_message(self, bus, message):
    """A message was received from gstreamer.
    
    Arguments:
      bus       The gstreamer bus.
      message   The message gstreamer sent to us.
    """
    with self._lock:
      t = message.type
      if t == gst.MESSAGE_ERROR:
        self.gst.set_state(gst.STATE_NULL)
        err, _ = message.parse_error()
        errormsg = "GStreamer: {0} (File: {1})".format(err,self._filename)
        self._bus.emit("error",errormsg)

  def _on_eos(self, bus, message, clear_eos_count):
    """A message was received from gstreamer. This second handler also takes a
    number that this player itself included when the handler was registered.
    This variable indicates how many times the eos state have been cleared.
    This is done everytime something is done that would move the player away
    from eos.
    
    Arguments:
      bus               The gstreamer bus.
      message           The message gstreamer sent to us.
      clear_eos_count   The number of times the eos has been cleared.
    """
    with self._lock:
      t = message.type
      if t == gst.MESSAGE_EOS and clear_eos_count == self._clear_eos_count:
        self.gst.set_state(gst.STATE_NULL)
        self._eos = True
        self.notify("eos")

  def _clear_eos(self):
    """Forget all pending eos events."""
    with self._lock:
      # We are no longer at the end of a stream.
      self._eos = False
      self.notify("eos")
      # Increase the clear_eos_count sent with new events.
      self._gstbus.disconnect(self._on_eos_id)
      self._clear_eos_count += 1
      self._on_eos_id = self._gstbus.connect( "message"
                                            , self._on_eos
                                            , self._clear_eos_count
                                            )

  def load(self,filename):
    """Load the given file.

    Arguments:
      filename  The file to load.

    Returns:    True if the load was successfull, otherwise False.
    """
    with self._lock:
      self._clear_eos()
      filepath = os.path.expanduser(os.path.join(self._directory,filename))
      filepath = os.path.abspath(filepath)
      self._filename = filename
      self._hasplayed = False
      self.gst.set_state(gst.STATE_NULL)
      self.gst.set_property("uri", "file://" + filepath)
      self.gst.set_state(gst.STATE_PAUSED)
      self.gst.get_state()
      try:
        dur = self.gst.query_duration(gst.FORMAT_TIME,None)[0]
      except gst.QueryError:
        self._duration = 0
        return False
      self._duration = dur
      return True

  def play(self):
    """Start playing at the current position."""
    with self._lock:
      if self._eos:
        self._eos = True
        self.notify("eos")
      else:
        self._hasplayed = True
        self.gst.set_state(gst.STATE_PLAYING)
        self.gst.get_state()

  def pause(self):
    """Pause playback."""
    with self._lock:
      self._clear_eos()
      self.gst.set_state(gst.STATE_PAUSED)
      self.gst.get_state()

  def seek(self,time_ns):
    """Seek to the given position in the current file.
    
    Arguments:
      time_ns   The position to seek to in nanoseconds.
    """
    with self._lock:
      self._clear_eos()
      self.gst.seek_simple(gst.FORMAT_TIME, gst.SEEK_FLAG_FLUSH, time_ns)
      self.gst.get_state()

  def position(self):
    """Get the current playback position.

    Returns:  (filename,position,duration)
    """
    with self._lock:
      try:
        pos = self.gst.query_position(gst.FORMAT_TIME,None)[0]
      except gst.QueryError:
        if self._hasplayed:
          pos = self._duration
        else:
          pos = 0
      return (self._filename, pos, self._duration)

  def duration(self):
    """Duration of the current file.

    Returns: Duration
    """
    with self._lock:
      return self._duration

  def filename(self):
    """Get the current file that is loaded.
    
    Returns: Filename as string.
    """
    with self._lock:
      return self._filename

  def quit(self):
    """Shut down the player."""
    with self._lock:
      self.gst.set_state(gst.STATE_NULL)
