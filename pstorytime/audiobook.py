# -*- coding: utf-8 -*-
"""Audiobook playing abstraction that uses gstreamer as backend.
"""

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

__all__ = [
  'Config',
  'AudioBook',
  ]

import os
from os.path import normcase, expanduser, isfile, join
import threading
import mimetypes
import gobject

from pstorytime.log import Log
import pstorytime.player
from pstorytime.misc import withdoc

class AudioBook(gobject.GObject):
  """Audiobook-playing abstraction for gstreamer.

  The same callback system as in gstreamer (and also GTK) is used.  Read up on
  python gobject (or GTK if appropriate) bindings if unsure on how to use them.
  
  Signals:
    error             Contains error messages as strings.

    position          Contains no additional information, but signals that it
                      is appropriate to update position information. This is
                      done when playing, pausing and seeking (also when
                      paused.)

    notify::eob       eob property updated.

    notify::filename  filename property updated.

    notify::playing   playing property updated.

    notify::playlog   playlog property updated.

  """

  SECOND = pstorytime.player.Player.SECOND
  """Time unit of a second according to gstreamer.
  """

  __gsignals__ = {
    'error' : ( gobject.SIGNAL_RUN_LAST,
                gobject.TYPE_NONE,
                (gobject.TYPE_STRING,)),
    'position' : (gobject.SIGNAL_RUN_LAST,
                  gobject.TYPE_NONE,
                  tuple())
  }

  core_extensions = ["m4b"]
  """Extensions to treat as audio files in addition to those registered as such in the system mime type database."""

  @withdoc(gobject.property)
  def playing(self):
    """True if the audiobook is playing. """
    with self._lock:
      return self._playing

  @withdoc(gobject.property)
  def eob(self):
    """True if the audiobook player is currently at the end of the book. """
    with self._lock:
      return self._eob

  @withdoc(gobject.property)
  def filename(self):
    """The currently loaded filename. """
    with self._lock:
      return self._filename

  @withdoc(gobject.property)
  def playlog(self):
    """The current playlog containing walltime, event type, filename and
    position. """
    with self._lock:
      return self._log.playlog

  def __init__(self,conf,directory):
    """ Create the audiobook playing abstraction.
    
    Arguments:
      conf        A configuration object like that from the result of the
                  parser in pstorytime.coreparser.
      directory   Directory of the audiobook to play.
    """

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
                      self._conf)
      self._log.connect("notify::playlog",self._on_playlog)

      self._filename = None
      self._eob = False

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
    """The playlog was updated.
    
    Arguments:
      log       The logger object.
      property  The property object that was updated.
    """
    with self._lock:
      self.notify("playlog")

  def _on_eos(self,player,property):
    """Gstreamer reached the end of a file.
    
    Arguments:
      player    The player that reached the end of a stream.
      property  The property that was updated.
    """
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
          self.emit("position")
          self._log.lognow("eob")
          self._log.stop()

  def mark(self, name):
    """Manually add an event in the playlog.
    
    Arguments:
      name  Name of the event.
    """
    with self._lock:
      self._log.lognow(name)

  def _play(self, start_file=None, start_pos=None, pos_relative_end=False, log=False, seek=False):
    """Internal general play abstraction.
    
    Arguments:
      start_file        The file to start playing at, use None to use the
                        current file. (Optional, defaults to None.)

      start_pos         The position to start playing at in ns, use None to use
                        the current position. (Or beginning of file if
                        start_file was given.) (Optional, defaults to None.)

      pos_relative_end  True if the length of the track should be added to
                        start_pos.  (Optional, defaults to False.)

      log               True if this should be logged as an event. (Optional,
                        defaults to False.)

      seek              True if this is a seeking operation. (Optional,
                        defaults to False.)

    Returns:  True if successfull.
    """
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
          self._log.lognow("loadfail")
          self._log.stop()
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
        if seek:
          self._log.lognow("seekto")
        else:
          self._log.lognow("start")

        if not paused_seek:
          self._log.start()

      if not paused_seek:
        self._playing = True
        self._player.play()
        self.notify("playing")

      self.emit("position")
      return True

  def _pause(self, log=False, seek=False):
    """Internal general pause abstraction.
    
    Arguments:
      log   True if this should be logged as an event.
      seek  True if this is part of a seek operation.
    """
    with self._lock: 
      if self._playing:
        self._playing = False
        self.notify("playing")
        self._player.pause()
        if log:
          if seek:
            self._log.lognow("seekfrom")
          else:
            self._log.lognow("stop")
          self._log.stop()
        self.emit("position")

  def play(self, start_file=None, start_pos=None):
    """Start playing the audiobook at current location, unless given another
    location.

    Arguments:
      start_file  The file to start playing at, use None to use the current
                  file. (Optional, defaults to None.)

      start_pos   The position to start playing at in ns, use None to use the
                  current position. (Or beginning of file if start_file was
                  given.) (Optional, defaults to None.)
    """
    with self._lock:
      # Only propagate if we are not playing, or we have given a position to
      # start playing at.
      if (not self._playing) or start_file != None or start_pos != None:
        return self._play(start_file, start_pos, log=True)

  def seek(self, start_file=None, start_pos=None):
    """Seek to the given position, otherwise works the same as play.

    Arguments:
      start_file  The file to seek to, use None to indicate the current file.
                  (Optional, defaults to None.)

      start_pos   The position to seek to in ns, use None to indicatethe
                  current position. (Or beginning of file if start_file was
                  given.) (Optional, defaults to None.)
    """
    with self._lock:
      if start_file!=None or start_pos!=None:
        return self._play(start_file, start_pos, log=True, seek=True)

  def dseek(self, delta):
    """Seek relative to the current position.

    Arguments:
      delta   Positive or negative distance to seek in ns.
    """
    with self._lock:
      (filename,pos,_) = self.position()
      return self._play(filename, pos+delta, log=True, seek=True)

  def pause(self):
    """Pause audiobook now. """
    with self._lock:
      if self._playing:
        self._pause(log=True)
        backtrack = self._conf.backtrack
        if backtrack!=None and backtrack>0:
          self.dseek(-backtrack*self.SECOND)

  def play_pause(self):
    """Toggle play/pause. """
    with self._lock:
      if self._playing:
        self.pause()
      else:
        self.play()

  def position(self):
    """Get current filename, position and duration (in ns) as a tuple.
    
    Returns: (filename,position,duration)
    """
    with self._lock:
      return self._player.position()

  def duration(self):
    """Get the duration of the current file.

    Returns:  Duration in ns.
    """
    with self._lock:
      return self._player.duration()

  def list_files(self):
    """List all audio files in audiobook directory.

    Returns:  List of filenames as strings.
    """
    with self._lock:
      entries = os.listdir(self._directory)
      entries.sort()
      return filter(self._is_audio_file, entries)
  
  def _is_audio_file(self,filename):
    """Internal function to check if a file is to be considered an audiobook.

    Returns: True if so.
    """
    with self._lock:
      if not isfile(join(self._directory,filename)):
        return False

      # Check if the filename ends with any of the given extensions.
      exts = AudioBook.core_extensions + self._conf.extensions
      exts = tuple(map(lambda e: '.'+e, exts))
      if filename.endswith(exts):
        return True

      # Check if the mimetype database indicates sais the extension
      # corresponds to an audio file.
      (mime, _) = mimetypes.guess_type(filename)
      if mime != None:
        data = mime.split("/",1)
        return len(data)==2 and data[0] == "audio"
      else:
        return False

  def get_file(self,delta):
    """Get a file relative to the current one.

    Argements:
      delta   Adds this number to the position of the current file in the
              audiobook directory, to get the new file.

    Returns:  New filename.
    """
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
    """Get the gstreamer playbin2 object.

    Please do not touch play/pause/seek functionality, or it will seriously
    mess things up. Though feel free to adjust volume/playback speed etc.

    Returns:  Gstreamer playbin2 object.
    """
    return self._player.gst

  def quit(self):
    """Shut down the audiobook player.
    """
    with self._lock:
      self.pause()
      self._log.quit()
      self._player.quit()
