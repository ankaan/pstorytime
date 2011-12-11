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

from threading import Thread, RLock
from time import strftime, time
from datetime import timedelta

from pstorytime.repeatingtimer import RepeatingTimer

class PosWriter(object):
  def __init__(self,audiobook,handler,interval=1):
    self._lock = RLock()
    self._audiobook = audiobook
    self._handler = handler
    self._gst = audiobook.gst()
    self._audiobook.connect("notify::playing",self._on_playing)
    self._audiobook.connect("position",self._on_position)
    self._gst.connect("notify::volume",self._on_volume)
    self._timer = RepeatingTimer(interval, self._poll)
    self._poll()

  def _on_playing(self,ab,property):
    with self._lock:
      if ab.playing and (not self._timer.started()):
        self._timer.start()
      if (not ab.playing) and self._timer.started():
        self._timer.stop()

  def _on_position(self,ab):
    with self._lock:
      self._poll()
      if self._timer.started():
        self._timer.start()

  def _on_volume(self,gst,property):
    with self._lock:
      self._poll()
      if self._timer.started():
        self._timer.start()

  def quit(self):
    with self._lock:
      self._poll()
      self._timer.destroy()
        
  def _poll(self):
    with self._lock:
      (filename,position,duration) = self._audiobook.position()
      walltime = strftime("%Y-%m-%d %H:%M:%S")

      position = timedelta(microseconds=position/1000)
      position = position - timedelta(microseconds=position.microseconds)

      duration = timedelta(microseconds=duration/1000)
      duration = duration - timedelta(microseconds=duration.microseconds)

      volume = self._gst.get_property("volume")

      self._handler.write("{walltime}: {filename} {position}/{duration} (vol: {volume})\n".format(
        walltime = walltime,
        filename = filename,
        position = str(position),
        duration = str(duration),
        volume = volume
        ))
      self._handler.flush()
