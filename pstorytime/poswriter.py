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

from threading import Thread, Event
from time import strftime
from datetime import timedelta

class PosWriter(object):
  def __init__(self,audiobook,handler=None,filename=None,timeout=1):
    self._audiobook = audiobook
    self._timeout = timeout
    self._quit = Event()
    self._running = Event()
    Thread(target=self._writer,kwargs={"handler":handler, "filename":filename}).start()
    self._audiobook.connect("notify::playing",self._on_playing)

  def _on_playing(self,ab,property):
    if ab.playing:
      self._running.set()
    else:
      self._running.clear()

  def quit(self):
    self._quit.set()
    self._running.set()

  def _writer(self,handler=None,filename=None):
    if handler!=None:
      self._poller(handler)
    elif filename!=None:
      with open(filename,"w") as f:
        self._poller(f)


  def _poller(self,f):
    self._poll_now(f)
    while not self._quit.is_set():
      self._running.wait()
      self._quit.wait(timeout=self._timeout)
      self._poll_now(f)
        
  def _poll_now(self,f):
    (filename,position,duration) = self._audiobook.position()
    walltime = strftime("%Y-%m-%d %H:%M:%S")

    position = timedelta(microseconds=position/1000)
    position = position - timedelta(microseconds=position.microseconds)

    duration = timedelta(microseconds=duration/1000)
    duration = duration - timedelta(microseconds=duration.microseconds)

    f.write("{walltime}: {filename} {position}/{duration}\n".format(
      walltime = walltime,
      filename = filename,
      position = str(position),
      duration = str(duration)
      ))
    f.flush()
