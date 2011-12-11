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
    self.log_prefix = "~/.pstorytime/logs"  # Place all logs relative to this directory.
    self.playlog_file = None                # Becomes: ".playlogfile"
    self.autolog_file = None                # Becomes self.playlogfile + ".auto"
    self.core_extensions = ["m4b"]          # Basically same as "m4a"
    self.extra_extensions = []
    self.autolog_interval = 60              # In seconds
    self.backtrack = None                   # In seconds

class AudioBook(gobject.GObject):
  SECOND = pstorytime.player.Player.SECOND

  __gsignals__ = {
    'error' : ( gobject.SIGNAL_RUN_LAST,
                gobject.TYPE_NONE,
                (gobject.TYPE_STRING,)),
    'position' : (gobject.SIGNAL_RUN_LAST,
                  gobject.TYPE_NONE,
                  tuple())
  }

  @gobject.property
  def playing(self):
    with self._lock:
      return self._playing

  @gobject.property
  def eob(self):
    with self._lock:
      return self._eob

  @gobject.property
  def filename(self):
    with self._lock:
      return self._filename

  @gobject.property
  def playlog(self):
    with self._lock:
      return self._log.playlog

  def __init__(self,conf,directory):
    gobject.GObject.__init__(self)
    self._lock = threading.RLock()
    with self._lock:
      self._playing = False
      self.notify("playing")

      self._conf = conf
      self._directory = normcase(expanduser(directory))
      
      self._player = pstorytime.player.Player(self,self._directory)
      self._player.connect("notify::eos",self._on_eos)

      self._log = Log(self,
                      self._player,
                      self._directory,
                      self._conf.log_prefix,
                      self._conf.playlog_file,
                      self._conf.autolog_file,
                      self._conf.autolog_interval)
      self._log.connect("notify::playlog",self._on_playlog)

      self._filename = None

      # Try to load last entry from play log.
      if len(self._log.playlog)>0:
        start_file = self._log.playlog[-1].filename
        start_pos = self._log.playlog[-1].position
        self._play(start_file, start_pos, log=False, seek=True)
      else:
        # Otherwise use first file in directory.
        dirlist = self.list_files()
        if len(dirlist)>0:
          start_file = dirlist[0]
          self._play(start_file, log=False, seek=True)
        else:
          # Nothing to play!
          self.emit("error","No valid files in audiobook directory.")

  def _on_playlog(self,log,property):
    with self._lock:
      self.notify("playlog")

  def _on_eos(self,player,property):
    with self._lock:
      if player.eos:
        # The player reported an end of stream, go to next file.
        next_file = self.get_file(1)
        if next_file != None:
          self._play(next_file)
        else:
          # No next file, we are at the end of the book.
          self._eob = True
          self.notify("eob")
          self._playing = False
          self.notify("playing")
          self._log.stop(custom="eob")

  def _play(self, start_file=None, start_pos=None, pos_relative_end=False, log=False, seek=False):
    with self._lock:
      self._eob = False
      self.notify("eob")

      # Is this a seek while the player is paused?
      paused_seek = seek and (not self._playing)

      # Make sure we are not playing anything.
      self._pause(log=log, seek=seek)

      if start_file != None and start_file != self._filename:
        # Try to load new file.
        self._filename = start_file
        self.notify("filename")
        if not self._player.load(start_file):
          # Failed to load file.
          self._log.stop(custom="loadfail")
          self._playing = False
          self.notify("playing")
          return False

      if start_pos != None:
        duration = self.duration()
        if pos_relative_end:
          start_pos += duration
        if start_pos < 0:
          # Position in an earlier file.
          prev_file = self.get_file(-1)
          if prev_file == None:
            # Already in first book!
            start_pos = 0
            pos_relative_end = False
            self._player.seek(start_pos)
          else:
            self._play(prev_file, start_pos, pos_relative_end=True, seek=True)
        elif start_pos < duration:
          # Position in this file.
          self._player.seek(start_pos)
        else:
          # Position in a later file.
          next_file = self.get_file(1)
          if next_file == None:
            # Already in last book!
            self._player.seek(duration)
          else:
            self._play(next_file, start_pos-duration, seek=True)

      if log:
        # Log "destination", don't start autologging if this is a paused seek.
        self._log.start(seek=seek, autolog=(not paused_seek))

      if not paused_seek:
        self._playing = True
        self._player.play()
        self.notify("playing")

      self.emit("position")
      return True

  def _pause(self, log=False, seek=False):
    with self._lock: 
      if self._playing:
        self._playing = False
        self.notify("playing")
        self._player.pause()
        if log:
          self._log.stop(seek=seek)
        self.emit("position")

  def play(self, start_file=None, start_pos=None):
    with self._lock:
      if (not self._playing) or start_file != None or start_pos != None:
        return self._play(start_file, start_pos, log=True)

  def seek(self, start_file=None, start_pos=None):
    with self._lock:
      return self._play(start_file, start_pos, log=True, seek=True)

  def dseek(self, delta):
    with self._lock:
      (filename,pos,_) = self.position()
      return self._play(filename, pos+delta, log=True, seek=True)

  def pause(self):
    with self._lock:
      if self._playing:
        self._pause(log=True)
        backtrack = self._conf.backtrack
        if backtrack!=None and backtrack>0:
          self.dseek(-backtrack*self.SECOND)

  def play_pause(self):
    with self._lock:
      if self._playing:
        self.pause()
      else:
        self.play()

  def position(self):
    with self._lock:
      return self._player.position()

  def duration(self):
    with self._lock:
      return self._player.duration()

  def list_files(self):
    with self._lock:
      entries = os.listdir(self._directory)
      entries.sort()
      return filter(self._is_audio_file, entries)
  
  def _is_audio_file(self,filename):
    with self._lock:
      if not isfile(join(self._directory,filename)):
        return False

      exts = self._conf.core_extensions + self._conf.extra_extensions
      exts = tuple(map(lambda e: '.'+e, exts))
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
      i = files.index(self._filename)
      if 0 <= i+delta < len(files):
        return files[i+delta]
      else:
        return None
    except ValueError:
      return None

  def gst(self):
    return self._player.gst

  def quit(self):
    with self._lock:
      self._log.quit()
      self._player.quit()
