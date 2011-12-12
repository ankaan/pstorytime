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

__all__ = [
  'PathGen',
  'withdoc',
  ]

class PathGen(object):
  """Generate filepaths from given components. """
  def __init__(self,directory,prefix):
    """Create a filepath generater with given directory and prefix.

    Arguments:
      directory   Directory to place files in.
      prefix      After generating a filepath, replace the first /
                  with this prefix.
    """
    self._directory = directory
    self._prefix = prefix

  def gen(self,custom,default):
    """Generate a filepath for the given file.
    
    Arguments:
      custom    The custom file to use, or None to use the default.
      default   The default file to use if custom is None.
    """
    if custom == None:
      filepath = default
    else:
      filepath = custom
    filepath = abspath(expanduser(join(self._directory, filepath)))
    filepath = abspath(expanduser(join(self._prefix, filepath[1:])))
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
    if self._acquired:
      return True
    else:
      try:
        dirpath = dirname(self._filepath)
        if not isdir(dirpath) and dirpath!='':
          os.makedirs(dirpath,mode=0700)
        self._handler = open(expanduser(self._filepath),'w')
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
