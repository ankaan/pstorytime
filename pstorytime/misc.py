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

from os.path import abspath, expanduser, join

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
      filename = default
    else:
      filename = custom
    filepath = abspath(expanduser(join(self._directory, filename)))
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
