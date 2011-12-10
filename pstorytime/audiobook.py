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

import os
from os.path import normcase, expanduser, isfile, join
import threading
import mimetypes
import gobject

from pstorytime.log import Log
import pstorytime.player

class Config(object):
  def __init__(self):
    self.playlog_file = None         # Becomes: ".playlogfile"
    self.autolog_file = None         # Becomes self.playlogfile + ".auto"
    self.extra_extensions = ["m4b"] # Not so uncommon audiobook format that is essentially a renamed m4a
    self.autolog_interval = 60      # In seconds

class AudioBook(gobject.GObject):
  SECOND = pstorytime.player.Player.SECOND

  __gsignals__ = {
    'error' : ( gobject.SIGNAL_RUN_LAST,
                gobject.TYPE_NONE,
                (gobject.TYPE_STRING,))
  }

  playing = gobject.property(type=bool,default=False)
  eob = gobject.property(type=bool,default=False)
  filename = gobject.property(type=str)
  playlog = gobject.property(type=object)

  def __init__(self,conf,directory):
    gobject.GObject.__init__(self)
    self._lock = threading.RLock()
    self.playing = False

    self._conf = conf
    self._directory = normcase(expanduser(directory))
    
    self._player = pstorytime.player.Player(self,self._directory)
    self._player.connect("notify::eos",self._on_eos)

    self._log = Log(self,
                    self._player,
                    self._directory,
                    self._conf.playlog_file,
                    self._conf.autolog_file,
                    self._conf.autolog_interval)
    self.playlog = self._log.playlog
    self._log.connect("notify::playlog",self._on_playlog)

    self.filename = ""

  def _on_playlog(self,log,property):
    with self._lock:
      self.playlog = log.playlog

  def _on_eos(self,player,property):
    with self._lock:
      if player.eos:
        # The player reported an end of stream, go to next file.
        next_file = self.get_file(1)
        if next_file != None:
          self._play(next_file)
        else:
          # No next file, we are at the end of the book.
          self.eob = True

  def _play(self, startfile=None, startpos=None, log=False, seek=False):
    with self._lock:
      self.eob = False

      # Is this a seek while the player is paused?
      paused_seek = seek and (not self.playing)

      # Make sure we are not playing anything.
      self._pause(log=log, seek=seek)

      if self.filename == "":
        old_file = None
      else:
        old_file = self.filename

      if old_file == None and startfile == None:
        # First play, and no file given.
        # Try to load last entry from play log.
        if len(self.playlog)>0:
          startfile = self.playlog[-1].filename
          if startpos==None:
            startpos = self.playlog[-1].position
        else:
          # Otherwise use first file in directory.
          dirlist = self.list_files()
          if len(dirlist)>0:
            startfile = dirlist[0]
          else:
            # Nothing to play!
            self.emit("error","No valid files in audiobook directory.")

      if startfile != None and startfile != old_file:
        # Try to load new file.
        self.filename = startfile
        if not self._player.load(startfile):
          # Failed to load file.
          self._log.stop(seek=seek, loadfail=True)
          self.playing = False
          return False

      if startpos != None:
        self._player.seek(startpos)

      if log:
        # Log "destination", don't start autologging if this is a paused seek.
        self._log.start(seek=seek, autolog=(not paused_seek))

      if not paused_seek:
        self._player.play()
        self.playing = True

      return True

  def _pause(self, log=False, seek=False):
    with self._lock: 
      if self.playing:
        self.playing = False
        self._player.pause()
        if log:
          self._log.stop(seek=seek)

  def play(self, startfile=None, startpos=None):
    with self._lock:
      if (not self.playing) or startfile != None or startpos != None:
        return self._play(startfile, startpos, log=True)

  def seek(self, startfile=None, startpos=None):
    with self._lock:
      return self._play(startfile, startpos, log=True, seek=True)

  def pause(self):
    with self._lock:
      self._pause(log=True)

  def play_pause(self):
    with self._lock:
      if self.playing:
        self.pause()
      else:
        self.play()

  def position(self):
    with self._lock:
      return self._player.position()

  def list_files(self):
    with self._lock:
      entries = os.listdir(self._directory)
      entries.sort()
      return filter(self._is_audio_file, entries)
  
  def _is_audio_file(self,filename):
    with self._lock:
      if not isfile(join(self._directory,filename)):
        return False

      exts = tuple(map(lambda e: '.'+e, self._conf.extra_extensions))
      if filename.endswith(exts):
        return True

      (mime, _) = mimetypes.guess_type(filename)
      if mime != None:
        data = mime.split("/",1)
        return len(data)==2 and data[0] == "audio"
      else:
        return False

  def get_file(self,delta):
    try:
      files = self.list_files()
      i = files.index(self.filename)
      if 0 < i+delta <= len(files):
        return files[i+delta]
      else:
        return None
    except ValueError:
      return None

  def gst(self):
    return self._player.gst

  def destroy(self):
    with self._lock:
      self._log.destroy()
