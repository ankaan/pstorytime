# -*- coding: utf-8 -*-
"""Miscelanious helper stuff for the audiobook player."""

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

from os.path import abspath, expanduser, join, dirname, isdir, isfile
import os
import fcntl
from datetime import timedelta
from gst import SECOND

__all__ = [
  'PathGen',
  'withdoc',
  ]

class PathGen(object):
  """Generate filepaths from given components. """
  def __init__(self,confdir,abdir):
    """Create a filepath generater using the given replacements.

    Arguments:
    replace     Dictionary with keys that should be replaced with values.
    """
    self._replace = {
      "conf" : abspath(expanduser(confdir)),
      "audiobook" : abspath(expanduser(abdir)) }

  def gen(self,filepath):
    """Generate a filepath for the given file.
    
    Arguments:
      filepath    The file to use.
    """
    if filepath!=None:
      filepath = filepath.format(**self._replace)
    return filepath

def withdoc(origdeco):
  """Transforms a decorator so that pydoc is preserved.
  """
  def newdeco(oldfun):
    newfun = origdeco(oldfun)
    newfun.__name__ = oldfun.__name__
    newfun.__doc__ = oldfun.__doc__
    newfun.__module__ = oldfun.__module__
    return newfun
  return newdeco

class LockedException(Exception):
  pass

class FileLock(object):
  """File lock handler.
  """
  def __init__(self,filepath):
    """Create a lock for the given file.

    Argements:
      filepath    The file to lock.
    """
    self._filepath = filepath
    self._acquired = False
    self._handler = None

  def acquire(self):
    """Acquire the lock. (Non-blocking.)

    Exceptions:
      LockedException   Is raised when it is not possible to acquire the lock.
    """
    if not self._acquired:
      self._filepath = expanduser(self._filepath)
      try:
        dirpath = dirname(self._filepath)
        if not isdir(dirpath) and dirpath!='':
          os.makedirs(dirpath,mode=0700)
        self._handler = open(self._filepath,'w')
      except IOError:
        raise LockedException()

      try:
        fcntl.lockf(self._handler, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self._acquired = True
      except IOError:
        self._handler.close()
        raise LockedException()

  def release(self):
    """Release the lock.
    """
    if self._acquired:
      fcntl.lockf(self._handler, fcntl.LOCK_UN)
      self._handler.close()
      if isfile(self._filepath):
        os.remove(self._filepath)
      self._acquired = False

  def __enter__(self):
    """Acquire the lock. (Non-blocking.)

    Exceptions:
      LockedException   Is raised when it is not possible to acquire the lock.
    """
    self.acquire()

  def __exit__(self, exc_type, exc_value, traceback):
    """Release the lock.
    """
    self.release()
    return False

class DummyLock(object):
  """A dummy lock or anything else that is placed within a with-statement.
  """
  def __init__(self):
    """Create a dummy lock.
    """

  def acquire(self):
    """Acquire the lock.
    """
    pass

  def release(self):
    """Release the lock.
    """
    pass

  def __enter__(self):
    """Acquire the lock.
    """
    pass

  def __exit__(self, exc_type, exc_value, traceback):
    """Release the lock.
    """
    return False

def ns_to_str(time_ns):
  dtime = timedelta(microseconds=time_ns/1000)
  dtime = dtime - timedelta(microseconds=dtime.microseconds)
  return str(dtime)

def parse_pos(raw):
  """Parse position from given string.
  
  Arguments:
    raw     raw data that is parsed to a position.

  Returns:  Position of file in nanoseconds, or None
            if parsing failed.
  """

  # Take care of negative positions
  if raw[0] == "-":
    sign = -1
    raw = raw[1:]
    rel = True
  elif raw[0] == "+":
    sign = 1
    raw = raw[1:]
    rel = True
  else:
    sign = 1
    rel = False

  for c in raw:
    if c not in ":0123456789":
      return (None,None)

  parts = raw.split(":")

  if '' in parts:
    return (None,None)

  seconds = 0
  minutes = 0
  hours = 0

  if len(parts) >= 1:
    seconds = int(parts[-1])
  if len(parts) >= 2:
    minutes = int(parts[-2])
  if len(parts) >= 3:
    hours = int(parts[-3])
  if len(parts) > 3:
    return (None,None)

  pos = sign * ((hours*60 + minutes)*60 + seconds) * SECOND
  return (rel, pos)
