# -*- coding: utf-8 -*-
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
import gst
import os.path
import threading
import gobject

class Player(gobject.GObject):
  SECOND = gst.SECOND

  eos = gobject.property(type=bool,default=False)

  def __init__(self,bus,directory):
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
    with self._lock:
      t = message.type
      if t == gst.MESSAGE_ERROR:
        self.gst.set_state(gst.STATE_NULL)
        err, _ = message.parse_error()
        errormsg = "GStreamer: {0} (File: {1})".format(err,self._filename)
        self._bus.emit("error",errormsg)

  def _on_eos(self, bus, message, clear_eos_count):
    with self._lock:
      t = message.type
      if t == gst.MESSAGE_EOS and clear_eos_count == self._clear_eos_count:
        self.gst.set_state(gst.STATE_NULL)
        self.eos = True

  def _clear_eos(self):
    with self._lock:
      self.eos = False
      self._gstbus.disconnect(self._on_eos_id)
      self._clear_eos_count += 1
      self._on_eos_id = self._gstbus.connect( "message"
                                            , self._on_eos
                                            , self._clear_eos_count
                                            )

  def load(self,filename):
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
      except:
        self._duration = 0
        return False
      self._duration = dur
      return True

  def play(self):
    with self._lock:
      if self.eos:
        self.eos = True
      else:
        self._hasplayed = True
        self.gst.set_state(gst.STATE_PLAYING)
        self.gst.get_state()

  def pause(self):
    with self._lock:
      self._clear_eos()
      self.gst.set_state(gst.STATE_PAUSED)
      self.gst.get_state()

  def seek(self,time_ns):
    with self._lock:
      self._clear_eos()
      self.gst.seek_simple(gst.FORMAT_TIME, gst.SEEK_FLAG_FLUSH, time_ns)
      self.gst.get_state()

  def position(self):
    with self._lock:
      try:
        pos = self.gst.query_position(gst.FORMAT_TIME,None)[0]
      except:
        if self._hasplayed:
          pos = self._duration
        else:
          pos = 0
      return (self._filename, pos, self._duration)

  def duration(self):
    with self._lock:
      return self._duration

  def filename(self):
    with self._lock:
      return self._filename
